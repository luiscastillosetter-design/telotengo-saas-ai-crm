from flask import Flask, request, jsonify
import requests
import json
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)

# --- CARGAR CONFIGURACIÓN ---
def cargar_config():
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# --- GESTIÓN DE BASE DE DATOS (LEADS Y EMPRESAS SAAS) ---
def obtener_o_crear_lead(telefono, nombre="Sin Nombre"):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT telefono, historial_chat FROM leads WHERE telefono = ?", (telefono,))
    lead = cursor.fetchone()
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not lead:
        historial_inicial = json.dumps([f"Bot: Inicio de conversación el {now}."], ensure_ascii=False)
        cursor.execute("""
            INSERT INTO leads (telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion, historial_chat)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (telefono, nombre, "Nuevo Prospecto", now, now, historial_inicial))
        conn.commit()
        historial = []
    else:
        historial = json.loads(lead[1]) if lead[1] else []
        
    conn.close()
    return historial

def guardar_historial_lead(telefono, nuevo_mensaje_cliente, nuevo_mensaje_bot):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    row = cursor.fetchone()
    
    if row:
        historial = json.loads(row[0]) if row[0] else []
        historial.append(f"Cliente: {nuevo_mensaje_cliente}")
        historial.append(f"Bot: {nuevo_mensaje_bot}")
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?
        """, (json.dumps(historial, ensure_ascii=False), now, telefono))
        conn.commit()
    conn.close()

# --- LÓGICA DE EMPRESAS SAAS Y KIOSCO DE CRÉDITOS ---
def verificar_empresa_saas(telefono_bot_receptor):
    """
    Verifica si el número de WhatsApp que recibe el mensaje es de una empresa SaaS de un cliente.
    Retorna: (es_saas: bool, empresa_id: int, saldo: int, prompt_maestro: str)
    """
    if not os.path.exists('crm_telotengo.db'):
        return False, None, 0, ""
        
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    
    # Intentamos buscar por el teléfono del bot o si está asignado como cliente
    cursor.execute("SELECT id, saldo_creditos, prompt_maestro FROM empresas_saas WHERE telefono_bot = ? OR telefono_bot = ?", 
                   (telefono_bot_receptor, f"+{telefono_bot_receptor.replace('+', '')}"))
    empresa = cursor.fetchone()
    conn.close()
    
    if empresa:
        return True, empresa[0], int(empresa[1]), empresa[2]
    return False, None, 0, ""

def descontar_credito_saas(empresa_id):
    """Resta 1 crédito de Inteligencia Artificial a la empresa en SQLite."""
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET saldo_creditos = saldo_creditos - 1 WHERE id = ?", (empresa_id,))
    conn.commit()
    conn.close()

# --- ENVÍO DE MENSAJES META GRAPH API ---
def enviar_mensaje_whatsapp(telefono_destino, mensaje_texto):
    config = cargar_config()
    meta_cfg = config.get("meta", {})
    token = meta_cfg.get("token", "")
    phone_number_id = meta_cfg.get("phone_number_id", "")
    
    if not token or not phone_number_id:
        print("❌ Error: Faltan credenciales de Meta en config.json")
        return False
        
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "text",
        "text": {"body": mensaje_texto}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error enviando a WhatsApp: {e}")
        return False

# --- CEREBRO IA CON PROMPT DINÁMICO ---
def generar_respuesta_ia(mensaje_usuario, historial, prompt_maestro):
    config = cargar_config()
    
    # Preparamos el contexto conversacional para el modelo
    mensajes_chat = [{"role": "system", "content": prompt_maestro}]
    
    # Agregamos hasta los últimos 6 mensajes del historial para mantener contexto rápido
    for msg in historial[-6:]:
        if msg.startswith("Cliente:"):
            mensajes_chat.append({"role": "user", "content": msg.replace("Cliente:", "").strip()})
        elif msg.startswith("Bot:") or msg.startswith("Agente:"):
            mensajes_chat.append({"role": "assistant", "content": msg.replace("Bot:", "").replace("Agente:", "").strip()})
            
    mensajes_chat.append({"role": "user", "content": mensaje_usuario})
    
    # Intentamos conectar con la API configurada (OpenAI por defecto en este bloque)
    openai_key = config.get("openai", {}).get("api_key", "")
    if openai_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": config.get("openai", {}).get("model", "gpt-3.5-turbo"),
                "messages": mensajes_chat,
                "temperature": 0.7
            }
            res = requests.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"⚠️ Error en IA: {e}")

    # Fallback o respuesta por defecto si no hay API externa activa en el momento
    return "¡Hola! He recibido tu mensaje. En un momento uno de nuestros asesores de Telotengo Solutions te atenderá de forma personalizada. 🚀"

# --- RUTAS DEL WEBHOOK (META WHATSAPP) ---
@app.route('/webhook', methods=['GET'])
def verificar_webhook():
    config = cargar_config()
    token_verificacion = config.get("meta", {}).get("verify_token", "telotengo_token_2026")
    
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode and token:
        if mode == "subscribe" and token == token_verificacion:
            print("✅ Webhook verificado correctamente por Meta.")
            return challenge, 200
        else:
            return "Token inválido", 403
    return "Faltan parámetros", 400

@app.route('/webhook', methods=['POST'])
def recibir_mensaje():
    body = request.get_json()
    
    try:
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    # Identificamos el número del bot que recibe (Para detectar si es un cliente SaaS)
                    metadata = value.get("metadata", {})
                    telefono_bot_receptor = metadata.get("display_phone_number", "")
                    
                    if "messages" in value:
                        for mensaje in value["messages"]:
                            if mensaje.get("type") == "text":
                                telefono_cliente = mensaje["from"]
                                texto_cliente = mensaje["text"]["body"]
                                nombre_cliente = value.get("contacts", [{}])[0].get("profile", {}).get("name", "Prospecto")
                                
                                print(f"\n📩 Mensaje recibido de {nombre_cliente} ({telefono_cliente}): {texto_cliente}")
                                
                                # 1. VERIFICAMOS SI ES UN CLIENTE SAAS O LA AGENCIA PRINCIPAL
                                es_saas, emp_id, saldo, prompt_saas = verificar_empresa_saas(telefono_bot_receptor)
                                config = cargar_config()
                                
                                if es_saas:
                                    print(f"🏢 Cliente SaaS detectado (ID: {emp_id}). Saldo actual: {saldo} créditos.")
                                    if saldo <= 0:
                                        print("🚨 Alerta: Saldo agotado para esta empresa. Bloqueando respuesta IA.")
                                        msg_alerta = "⚠️ El Asistente de Inteligencia Artificial está pausado temporalmente debido a que el saldo de créditos se ha agotado. Por favor, contacta al administrador para recargar tu plan."
                                        enviar_mensaje_whatsapp(telefono_cliente, msg_alerta)
                                        return jsonify({"status": "sin_saldo"}), 200
                                    
                                    # Si hay saldo, usamos el prompt del cliente SaaS
                                    prompt_a_usar = prompt_saas
                                else:
                                    # Si no es SaaS, es el Bot Principal de tu Agencia
                                    prompt_default = "Eres el Consultor IA de Telotengo Solutions. Asesoras sobre soluciones 360: Webs, CRMs, Redes y Avatares IA."
                                    prompt_a_usar = config.get("negocio", {}).get("prompt_maestro", prompt_default)
                                
                                # 2. OBTENEMOS HISTORIAL EN SQLITE
                                historial = obtener_o_crear_lead(telefono_cliente, nombre_cliente)
                                
                                # 3. GENERAMOS RESPUESTA IA CON EL PROMPT EN VIVO
                                respuesta_bot = generar_respuesta_ia(texto_cliente, historial, prompt_a_usar)
                                
                                # 4. ENVIAMOS RESPUESTA A WHATSAPP
                                enviado = enviar_mensaje_whatsapp(telefono_cliente, respuesta_bot)
                                
                                # 5. SI SE ENVIÓ CON ÉXITO Y ES SAAS, DESCONTAMOS 1 CRÉDITO
                                if enviado and es_saas:
                                    descontar_credito_saas(emp_id)
                                    print(f"💳 1 Crédito descontado a la empresa ID {emp_id}. Nuevo saldo: {saldo - 1}")
                                
                                # 6. GUARDAMOS EN EL HISTORIAL DEL CRM
                                guardar_historial_lead(telefono_cliente, texto_cliente, respuesta_bot)
                                print(f"🤖 Respuesta enviada y guardada: {respuesta_bot}")
                                
    except Exception as e:
        print(f"❌ Error procesando el webhook: {e}")
        
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    print("🚀 Servidor Telotengo SaaS iniciado en puerto 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
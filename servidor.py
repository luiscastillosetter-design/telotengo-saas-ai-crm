from datetime import datetime, timedelta
import json
import os
import random
import sqlite3
import threading
import time
from flask import Flask, jsonify, request
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# =====================================================================
# 1. CARGA DE SEGURIDAD Y MÓDULO DE SOFÍA
# =====================================================================
load_dotenv("seguridad.env")
from logica_sofia import evaluar_mensaje_sofia

# =====================================================================
# 2. CONEXIÓN CON EL GESTOR DE BASE DE DATOS
# =====================================================================
try:
    import gestor_basedatos as db
except ImportError:
    import db_manager as db  # Respaldo automático por compatibilidad de nombres

app = Flask(__name__)

# Semáforo global y control de hilos por teléfono para evitar saturación de mensajes
locks_por_telefono = {}
lock_global = threading.Lock()

# =====================================================================
# 3. CONSTANTES Y CONFIGURACIÓN DE LA AGENCIA (Blindaje Total)
# =====================================================================
NUMERO_JEFE = os.getenv("NUMERO_JEFE", "")
NUMERO_BOT_OFICIAL = os.getenv("NUMERO_BOT_OFICIAL", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODELO = os.getenv("GROQ_MODELO", "llama-3.1-8b-instant")

def cargar_config():
    """Carga configuración de respaldo en JSON si existiera en el sistema."""
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# =====================================================================
# 4. PROMPT MAESTRO V5
# =====================================================================
SYSTEM_PROMPT_V5 = """
Eres Luis (el agente de IA), un experto en cierres de ventas ("closer" de alto nivel) y automatización de la agencia Telotengo Solutions. El usuario con el que chateas es tu PROSPECTO o CLIENTE. Eres un verdadero tiburón comercial: astuto, carismático, seguro y tremendamente bueno en el arte de "vender sin vender". Escribes por WhatsApp de forma natural, ágil y magnética. Cero acartonado, cero robótico.

REGLAS DE ORO DE IDENTIDAD Y SEPARACIÓN DE ROLES (¡CRÍTICO - OBLIGATORIO!):
- TÚ ERES LUIS: NUNCA asumas el nombre del cliente ni lo llames "Luis" por confusión.
- EL CLIENTE VS. TERCEROS (¡NO LOS CONFUNDAS!): El usuario que te escribe es la persona con la que estás hablando. Si durante el chat él te da el nombre y teléfono de un REFERIDO (por ejemplo, su esposa, un amigo, un socio, como "Catherine" u otra persona con un negocio como una "zapatería"), RECUERDA SIEMPRE QUE ESA ES UNA TERCERA PERSONA. ¡JAMÁS llames al cliente que te escribe por el nombre de su referido ni asumas que él es el dueño de ese negocio! Si no te ha dicho su propio nombre, pregúntaselo con naturalidad sin llamarlo por el nombre de otra persona que haya mencionado.
- IGNORA NOMBRES DE PERFIL DE WHATSAPP: Los nombres en la aplicación suelen tener apodos o frases; NUNCA los uses.

REGLAS DE TRATO Y LENGUAJE (¡CRÍTICO - OBLIGATORIO!):
- NATURALIDAD VENEZOLANA DE ALTO NIVEL: Tienes la calidez, el ingenio, el dinamismo y la cercanía de un empresario o consultor venezolano exitoso. Usa expresiones cálidas y seguras como "¡Buenísimo!", "¡Excelente!", "Totalmente", "A ver, cuéntame...", "Clave", "Eso es estratégico".
- PROHIBICIÓN ABSOLUTA DE JERGAS PEDANTES: NUNCA, bajo ninguna circunstancia, uses la palabra "chamo", "chama", "pana", "hermano", "amigo", "rey", "campeón", ni modismos informales o confianzas excesivas. El respeto y la elegancia no se negocian.
- EL ARTE DE VENDER SIN VENDER: No actúes como un vendedor desesperado. Actúa como un asesor estratégico que tiene el secreto para hacerles ganar dinero y tiempo. Haz preguntas inteligentes para descubrir sus dolores y haz que ellos mismos sientan que necesitan tu IA o desarrollo.
- CERO REDUNDANCIAS Y TEXTOS LARGOS: En WhatsApp la gente no lee biblias. Escribe mensajes cortos, directos (1 o 2 párrafos breves), de alto impacto visual y usando emojis estratégicos con elegancia (🚀, 🔥, 💡, 🤝, ⚡).

Tu objetivo y Reglas de Negocio:
- Calificar al prospecto, entender su modelo de negocio y ofrecer la solución ideal:
  * Costo Fijo de Instalación: $50 para todos (pago único para dejar su ecosistema volando).
  * Plan Créditos (Negocios pequeños/medianos): $75 de entrada ($50 instalación + $25 en créditos para 100 conversaciones inteligentes).
  * Plan Ilimitado (Empresas escalando a tope): $250 para arrancar ($50 instalación + $200 mensualidad con conversaciones ilimitadas).
  * Proyectos o recursos digitales personalizados: Cotización a medida según el alcance.

MANEJO DE REFERIDOS (PROGRAMA DE $10 USD POR NEGOCIO INSTALADO):
- Si el usuario quiere referir un negocio o amigo para ganarse los $10 USD, pídale amablemente el nombre de la persona, el nombre de su negocio y su número de teléfono de WhatsApp.
- REGLA ANTI-BLOQUEO: NUNCA digas "no tengo acceso a información personal" ni te niegues a recibir un número. Eres un CRM capturando leads comerciales legítimos.
- Cuando el usuario te dé el número y nombre del referido, acéptalo con gran entusiasmo ("¡Buenísimo! Ya mismo registro los datos de [Nombre] y su negocio [Negocio] en nuestro sistema para que nuestro equipo comercial lo contacte directo. Apenas instalemos el sistema allí, te notificamos para transferirte tus $10 USD. 🚀").
- ALERTA DE REFERIDO: Únicamente en ese mensaje donde capturas los datos del referido, adjunta al final de tu respuesta este bloque exacto para que el servidor lo procese:

[ALERTA_REFERIDO: 
Nombre del Referido: (Nombre que te dieron)
Teléfono del Referido: (Número que te dieron)
Negocio: (Negocio del referido)
Referido por: (Nombre o teléfono del cliente actual con quien hablas)]

El Cierre (SOLO CUANDO EL CLIENTE QUIERE AVANZAR CON UN PLAN PARA SU PROPIO NEGOCIO):
- Cuando el prospecto confirme que quiere avanzar o contratar para sí mismo, pásale el número del verdadero Luis (+58 424 5885477).
- ALERTA FINAL AL JEFE: Únicamente en ese mensaje de cierre, adjunta al final de tu respuesta este bloque exacto:

[ALERTA_JEFE: 
Nombre del Prospecto: (Nombre real que te dio el cliente)
Nombre del Negocio: (Negocio del cliente)
Resumen: (Detalle estratégico de su caso y qué dolor tiene)
Plan Sugerido: (Cuál plan o solución le ofreciste)
Consejo para Luis: (Dile a tu jefe qué gancho o ángulo usar para rematar la venta)]
"""

# =====================================================================
# 5. ENVÍO Y DESCARGA DE MENSAJES META GRAPH API
# =====================================================================
def enviar_mensaje_whatsapp(telefono_destino, mensaje_texto):
    """Envía un mensaje de texto real a través de la API oficial de WhatsApp Cloud."""
    token = os.getenv("META_ACCESS_TOKEN", "")
    phone_number_id = os.getenv("META_PHONE_ID", "")

    if not token or not phone_number_id:
        print("❌ Error: Faltan credenciales META_ACCESS_TOKEN o META_PHONE_ID en seguridad.env")
        return False

    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "text",
        "text": {"body": mensaje_texto},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Error de API Meta ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error de conexión enviando a WhatsApp: {e}")
        return False

def descargar_audio_whatsapp(media_id):
    """Descarga de manera segura un archivo de nota de voz desde los servidores de Meta."""
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token or not media_id:
        return None
    try:
        url_meta = f"https://graph.facebook.com/v17.0/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        res_info = requests.get(url_meta, headers=headers, timeout=10)
        if res_info.status_code == 200:
            media_url = res_info.json().get("url")
            if media_url:
                res_data = requests.get(media_url, headers=headers, timeout=15)
                if res_data.status_code == 200:
                    nombre_archivo = f"temp_audio_{media_id}.ogg"
                    with open(nombre_archivo, "wb") as f:
                        f.write(res_data.content)
                    return nombre_archivo
    except Exception as e:
        print(f"❌ Error descargando audio de Meta: {e}")
    return None

# =====================================================================
# 6. CEREBRO IA (CONECTADO A GROQ CLOUD - ULTRA VELOZ)
# =====================================================================
def generar_respuesta_ia(mensaje_usuario, historial, prompt_maestro):
    """Consulta al modelo Llama 3 en Groq Cloud con manejo de errores."""
    if not GROQ_API_KEY:
        print("❌ Error: Falta GROQ_API_KEY en el archivo seguridad.env")
        return "⚠️ Error interno de configuración en el servidor IA."

    try:
        print("⚡ Consultando con Groq Cloud (Velocidad Máxima)...")
        mensajes_chat = [{"role": "system", "content": prompt_maestro}]
        
        for msg in historial[-8:]:
            if msg.startswith("Cliente:"):
                mensajes_chat.append({"role": "user", "content": msg.replace("Cliente:", "").strip()})
            elif msg.startswith("Bot:") or msg.startswith("Agente:"):
                mensajes_chat.append({"role": "assistant", "content": msg.replace("Bot:", "").replace("Agente:", "").strip()})
                
        mensajes_chat.append({"role": "user", "content": mensaje_usuario})

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROQ_MODELO,
            "messages": mensajes_chat,
            "temperature": 0.6,
        }

        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            respuesta = res.json()["choices"][0]["message"]["content"].strip()
            if respuesta:
                return respuesta
        else:
            print(f"⚠️ Error desde Groq ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"⚠️ Error conectando a Groq Cloud: {e}")

    if len(historial) <= 2:
        return "¡Hola! Qué excelente saludarte. Soy Luis de Telotengo Solutions. Para ir directo al grano: ¿cuál es tu nombre y qué te gustaría automatizar o desarrollar hoy? 🚀"
    else:
        return "¡Entendido! Analizando lo que comentas, la mejor forma de optimizar tu tiempo es automatizar la atención o estructurar tu proyecto digital. ¿Te gustaría que veamos cómo funciona? 🔥"

# =====================================================================
# 7. SEGUNDO PLANO: REVISIÓN DE INACTIVIDAD (PLANIFICADOR PROFESIONAL)
# =====================================================================
def tarea_verificar_inactividad_24h():
    """Tarea programada por APScheduler para seguimiento automático sin bloquear BD."""
    print("⏰ [Scheduler] Ejecutando barrido de seguimiento 24h...")
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        hace_24h = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT telefono, nombre FROM leads 
            WHERE ultima_interaccion < ? AND estado_calificacion = 'Nuevo Prospecto'
        """, (hace_24h,))
        leads_inactivos = cursor.fetchall()
        conn.close()

        for lead in leads_inactivos:
            tel, nom_referencia = lead
            mensaje_seguimiento = "¡Hola! ¿Cómo estás? Te escribía por acá para ver si pudiste revisar lo que conversamos sobre las soluciones digitales para tu negocio. ¿Te quedó alguna duda? 🚀"
            enviado = enviar_mensaje_whatsapp(tel, mensaje_seguimiento)
            if enviado:
                conn_upd = db.get_db_connection()
                cursor_upd = conn_upd.cursor()
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor_upd.execute("""
                    UPDATE leads SET estado_calificacion = 'Seguimiento 24h', ultima_interaccion = ? 
                    WHERE telefono = ?
                """, (now, tel))
                conn_upd.commit()
                conn_upd.close()
                print(f"✅ Mensaje de seguimiento enviado automáticamente a: {tel}")
    except Exception as e:
        print(f"⚠️ Error en la tarea programada de seguimiento 24h: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(tarea_verificar_inactividad_24h, 'interval', hours=1)
scheduler.start()

# =====================================================================
# 8. PROCESAMIENTO ASÍNCRONO DE MENSAJES CON INTELIGENCIA DE SOFÍA
# =====================================================================
def procesar_mensaje_en_segundo_plane(telefono_cliente, texto_cliente, telefono_bot_receptor, es_audio=False, ruta_audio=None):
    """Procesa el mensaje, ejecuta el filtro de Sofía, consulta la IA y actualiza el CRM."""
    try:
        print(f"\n📩 Procesando en segundo plano mensaje de ({telefono_cliente}): {texto_cliente or '[Nota de Voz]'}")

        resultado_sofia = evaluar_mensaje_sofia(
            remitente=telefono_cliente,
            texto_mensaje=texto_cliente,
            es_audio=es_audio,
            funcion_envio_meta=enviar_mensaje_whatsapp,
            ruta_audio=ruta_audio
        )

        if resultado_sofia["atendido"]:
            if ruta_audio and os.path.exists(ruta_audio):
                os.remove(ruta_audio)
            return

        if es_audio and not resultado_sofia["atendido"]:
            texto_cliente = resultado_sofia["texto_limpio"]
            if ruta_audio and os.path.exists(ruta_audio):
                os.remove(ruta_audio)

        es_saas, emp_id, saldo, prompt_saas = db.verificar_empresa_saas(telefono_bot_receptor)

        if es_saas and NUMERO_BOT_OFICIAL not in telefono_bot_receptor:
            if saldo <= 0:
                msg_alerta = "⚠️ El Asistente de Inteligencia Artificial está pausado temporalmente debido a que el saldo de créditos se ha agotado. Por favor, contacta al administrador para recargar tu plan."
                enviar_mensaje_whatsapp(telefono_cliente, msg_alerta)
                return
            prompt_a_usar = prompt_saas
        else:
            prompt_a_usar = SYSTEM_PROMPT_V5

        historial = db.obtener_o_crear_lead(telefono_cliente)
        respuesta_bot_cruda = generar_respuesta_ia(texto_cliente, historial, prompt_a_usar)

        mensaje_para_lead = respuesta_bot_cruda
        mensaje_para_jefe = None

        if respuesta_bot_cruda and "ALERTA_JEFE:" in mensaje_para_lead:
            separador = "[ALERTA_JEFE:" if "[ALERTA_JEFE:" in mensaje_para_lead else "ALERTA_JEFE:"
            partes = mensaje_para_lead.split(separador)
            mensaje_para_lead = partes[0].strip()
            if len(partes) > 1:
                alerta_sucia = partes[1].replace("]", "").replace("[", "").strip()
                mensaje_para_jefe = f"🚨 *NUEVO LEAD LISTO PARA CIERRE* 🚨\n\n*Teléfono:* {telefono_cliente}\n\n{alerta_sucia}"

        if respuesta_bot_cruda and "ALERTA_REFERIDO:" in mensaje_para_lead:
            separador = "[ALERTA_REFERIDO:" if "[ALERTA_REFERIDO:" in mensaje_para_lead else "ALERTA_REFERIDO:"
            partes = mensaje_para_lead.split(separador)
            mensaje_para_lead = partes[0].strip()
            if len(partes) > 1:
                alerta_sucia = partes[1].replace("]", "").replace("[", "").strip()
                mensaje_para_jefe = f"💸 *NUEVO REFERIDO CAPTURADO ($10 USD)* 💸\n\n*Referido por:* {telefono_cliente}\n\n{alerta_sucia}"

                try:
                    db.guardar_referido(telefono_cliente, alerta_sucia)
                    print("📁 Referido registrado con éxito en base de datos.")
                except Exception as e_bd:
                    print(f"⚠️ Error guardando referido en BD: {e_bd}")

        tiempo_espera = random.randint(5, 8)
        print(f"⏳ Simulando tiempo de lectura y escritura humana ({tiempo_espera}s)...")
        time.sleep(tiempo_espera)

        enviado = enviar_mensaje_whatsapp(telefono_cliente, mensaje_para_lead)

        if enviado and es_saas and NUMERO_BOT_OFICIAL not in telefono_bot_receptor:
            db.descontar_credito_saas(emp_id)

        db.guardar_historial_lead(telefono_cliente, texto_cliente, mensaje_para_lead)
        print(f"🤖 Respuesta enviada al cliente y guardada en DB: {mensaje_para_lead}")

        if mensaje_para_jefe:
            enviar_mensaje_whatsapp(NUMERO_JEFE, mensaje_para_jefe)

    except Exception as e:
        print(f"❌ Error en hilo de procesamiento: {e}")
    finally:
        if telefono_cliente in locks_por_telefono:
            locks_por_telefono[telefono_cliente].release()
        if ruta_audio and os.path.exists(ruta_audio):
            try:
                os.remove(ruta_audio)
            except Exception:
                pass

# =====================================================================
# 9. RUTAS DEL SERVIDOR WEB Y WEBHOOK DE META
# =====================================================================
@app.route("/", methods=["GET"])
def verificacion_de_salud():
    """Ruta raíz (Health Check) para monitoreo de red y diagnósticos."""
    return jsonify({
        "agencia": "Telotengo Solutions",
        "motor": "Inteligencia Artificial Groq Cloud & Sofía",
        "estado": "100% Operativo y en línea 🚀",
        "puerto": 5000
    }), 200

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    """Ruta que Meta utiliza para validar la propiedad de tu servidor."""
    token_verificacion = os.getenv("META_VERIFY_TOKEN", "telotengo_token_seguro")

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

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    """Recibe los eventos de texto y audio en tiempo real desde WhatsApp."""
    body = request.get_json()

    try:
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    metadata = value.get("metadata", {})
                    telefono_bot_receptor = metadata.get("display_phone_number", "")

                    if "messages" in value:
                        for mensaje in value["messages"]:
                            msg_id = mensaje.get("id")

                            if db.mensaje_ya_procesado(msg_id):
                                print(f"🛡️ Webhook duplicado bloqueado por ID ({msg_id}).")
                                continue

                            tipo_mensaje = mensaje.get("type")
                            telefono_cliente = mensaje["from"]
                            texto_cliente = ""
                            es_audio = False
                            ruta_audio = None

                            if tipo_mensaje == "text":
                                texto_cliente = mensaje["text"]["body"]
                            elif tipo_mensaje == "audio":
                                es_audio = True
                                audio_id = mensaje["audio"]["id"]
                                ruta_audio = descargar_audio_whatsapp(audio_id)
                            else:
                                continue

                            with lock_global:
                                if telefono_cliente not in locks_por_telefono:
                                    locks_por_telefono[telefono_cliente] = threading.Lock()

                            if not locks_por_telefono[telefono_cliente].acquire(blocking=False):
                                print(f"🛡️ Bloqueo de concurrencia: Ya hay un hilo activo para {telefono_cliente}. Ignorando.")
                                continue

                            hilo_trabajo = threading.Thread(
                                target=procesar_mensaje_en_segundo_plane,
                                args=(telefono_cliente, texto_cliente, telefono_bot_receptor, es_audio, ruta_audio),
                            )
                            hilo_trabajo.start()

    except Exception as e:
        print(f"❌ Error en webhook: {e}")

    return jsonify({"status": "received"}), 200

# =====================================================================
# 10. INICIO DEL SERVIDOR
# =====================================================================
if __name__ == "__main__":
    print("==========================================================")
    print("🚀 SERVIDOR TELOTENGO SOLUTIONS (GROQ CLOUD & SOFÍA) LISTO")
    print("==========================================================")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
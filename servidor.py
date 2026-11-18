from datetime import datetime, timedelta
import json
import os
import random
import sqlite3
import threading
import time
import logging
import re  # NUEVO: Para extraer el número de teléfono del cliente
from flask import Flask, jsonify, request
import requests
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# =====================================================================
# 1. CARGA DE SEGURIDAD Y MÓDULO DE SOFÍA
# =====================================================================
load_dotenv("seguridad.env")
from logica_sofia import evaluar_mensaje_sofia
from anti_spam import respuesta_anti_spam, limite_ia_alcanzado, MENSAJE_LIMITE
from catalogo_todomax import bloque_catalogo_vivo
from rutas import EN_VERCEL, ruta_escribible

# =====================================================================
# 2. CONEXIÓN CON EL GESTOR DE BASE DE DATOS
# =====================================================================
import gestor_basedatos as db

app = Flask(__name__)

# Semáforo global y control de hilos por teléfono
locks_por_telefono = {}
lock_global = threading.Lock()

# =====================================================================
# 3. CONSTANTES Y CONFIGURACIÓN DE LA AGENCIA 
# =====================================================================
NUMERO_JEFE = os.getenv("NUMERO_JEFE", "")
NUMERO_BOT_OFICIAL = os.getenv("NUMERO_BOT_OFICIAL", "")
JARVIS_AUTH_TOKEN = os.getenv("JARVIS_AUTH_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Anthropic (conexión directa, único proveedor de IA)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")

# =====================================================================
# 3.1 RESOLUCIÓN DINÁMICA DE META TOKENS (NUEVO MOTOR SAAS)
# =====================================================================
CREDENCIALES_META_BOTS_FALLBACK = {
    "1279776661877439": {  
        "token": os.getenv("META_ACCESS_TOKEN", ""),
        "phone_id": "1279776661877439",
        "display_phone": NUMERO_BOT_OFICIAL or "17543411559"
    }
}

def obtener_credenciales_meta(phone_number_id_recibido):
    """Resuelve el token exacto basándose dinámicamente en la base de datos."""
    if not phone_number_id_recibido:
        return os.getenv("META_ACCESS_TOKEN", ""), os.getenv("META_PHONE_ID", "")

    try:
        conn = db.get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT meta_token, telefono_bot FROM empresas_saas WHERE meta_phone_id = ?", (str(phone_number_id_recibido),))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado and resultado["meta_token"]:
            return resultado["meta_token"], str(phone_number_id_recibido)
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error buscando credenciales dinámicas en BD: {e}")
    
    if str(phone_number_id_recibido) in CREDENCIALES_META_BOTS_FALLBACK:
        creds = CREDENCIALES_META_BOTS_FALLBACK[str(phone_number_id_recibido)]
        return creds["token"], creds["phone_id"]
    
    return os.getenv("META_ACCESS_TOKEN", ""), os.getenv("META_PHONE_ID", "")

def obtener_telefono_display_saas(phone_number_id_recibido):
    """Mapea el ID de Meta al número real del bot buscando en BD."""
    try:
        conn = db.get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT telefono_bot FROM empresas_saas WHERE meta_phone_id = ?", (str(phone_number_id_recibido),))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado and resultado["telefono_bot"]:
            return resultado["telefono_bot"]
    except Exception:
        pass
        
    if str(phone_number_id_recibido) in CREDENCIALES_META_BOTS_FALLBACK:
        return CREDENCIALES_META_BOTS_FALLBACK[str(phone_number_id_recibido)]["display_phone"]
        
    return phone_number_id_recibido

# =====================================================================
# 4. CONFIGURACIÓN DE LOGGING (sofia_system.log)
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()] if EN_VERCEL else [
        logging.FileHandler("sofia_system.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sofia")

def registrar_log_sistema(tipo, mensaje):
    log_method = getattr(logger, tipo.lower(), logger.info)
    log_method(mensaje)

def cargar_config():
    if os.path.exists("config.json"):
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# =====================================================================
# 5. PROMPT MAESTRO V5
# =====================================================================
SYSTEM_PROMPT_SOFIA = """ROL E IDENTIDAD
Eres Sofía, asesora de ventas de Importadora TodoMax (https://www.importadoratodomax.com), tienda en línea de Venezuela. Conoces ÚNICA Y EXCLUSIVAMENTE el entorno de importadoratodomax.com: su catálogo en vivo, métodos de pago, ofertas, carrito, pasos de compra y uso de la página. Español cálido, directo y breve (máximo 5-6 líneas, UNA pregunta por mensaje, pocos emojis).

REGLAS OBLIGATORIAS (CERO ALUCINACIONES)
- Nunca inventes productos, precios, descuentos, stock ni respuestas fuera de importadoratodomax.com. Usa SOLO el CATÁLOGO EN VIVO que aparece al final de este mensaje. Si algo no está ahí, dilo con honestidad y sugiere lo más parecido del catálogo o la web.
- Si el tema no es de importadoratodomax.com, di amablemente que solo puedes ayudar con la tienda.
- Si preguntan por un producto: da la info breve (nombre, precio en USD, oferta si aplica, disponibilidad) y envía SIEMPRE el enlace directo exacto "Enlace" del catálogo (formato https://www.importadoratodomax.com/product/{id}). Máximo 3 productos por respuesta.
- Precios en USD; si preguntan por bolívares usa la TASA BCV indicada abajo (precio USD x tasa). Si no hay tasa, dilo y di que la ven en la barra superior de la web.
- Ofertas: solo las marcadas como OFERTA en el catálogo (precio anterior vs. actual). Nunca inventes cupones ni promociones.
- Si preguntan cómo pagar o cómo usar la página: da la ruta clara paso a paso y CIERRA SIEMPRE enviando el enlace https://www.importadoratodomax.com para llevar el tráfico a la web.

CÓMO COMPRAR (pasos)
1) Entra a https://www.importadoratodomax.com y busca o abre el producto. 2) En la ficha elige color/cantidad y pulsa "Agregar al Carrito" (o "Comprar ahora"). 3) Abre el carrito y revisa tu pedido. 4) Ve al checkout, completa tus datos de envío y elige el método de pago. 5) Realiza el pago, escribe el número de referencia y adjunta el comprobante. 6) Confirma el pedido: al final se abre WhatsApp para finalizar la atención con el equipo.

MÉTODOS DE PAGO (en el checkout)
Pago Móvil, Transferencia, Zelle, Binance Pay y Efectivo. Cada producto indica en su ficha cuáles acepta. Los datos de la cuenta (banco, teléfono, correo, Pay ID) se muestran en el checkout al elegir el método: NO los inventes ni los des tú. Excepto Efectivo, todos requieren referencia y comprobante.
Envío gratis en compras desde $50. Empresas de envío: MRW, Zoom, Tealca, Delivery Local y Retiro en Tienda.

ESCALAMIENTO A UN ASESOR HUMANO
Si el cliente tiene un reclamo, pide hablar con una persona o confirmar un pago, responde primero con un mensaje amable y al final adjunta este bloque exacto (oculto para el cliente):

[ALERTA_JEFE:
Cliente: (nombre o teléfono)
Motivo: (resumen breve del caso)]
"""

REGLAS_SISTEMA_CRM = """
[IMPORTANTE PARA LA IA: NUNCA anuncies la alerta en el texto al cliente. El bloque ALERTA_JEFE va oculto y pegado al final de tu mensaje. Nunca envíes solo la alerta.]
"""

# =====================================================================
# 5.5 INTEGRACIONES DE BASE DE DATOS LOCAL Y TELEGRAM
# =====================================================================
def notificar_telegram(mensaje, ruta_imagen=None):
    """Envía notificaciones logísticas y comprobantes visuales al chat del Jefe en Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        registrar_log_sistema("WARNING", "Credenciales de Telegram no configuradas.")
        return False
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        if ruta_imagen and os.path.exists(ruta_imagen):
            with open(ruta_imagen, 'rb') as foto:
                requests.post(
                    f"{url_base}/sendPhoto",
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": mensaje, "parse_mode": "Markdown"},
                    files={"photo": foto},
                    timeout=15
                )
        else:
            requests.post(
                f"{url_base}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
                timeout=10
            )
        return True
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error enviando a Telegram: {e}")
        return False

# 🔥 NUEVO: RADAR BIDIRECCIONAL DE TELEGRAM 🔥
TELEGRAM_OFFSET = 0

def hilo_escuchar_telegram():
    global TELEGRAM_OFFSET
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    print("📡 Radar Bidireccional de Telegram ACTIVADO.")
    url_base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    while True:
        try:
            res = requests.get(f"{url_base}/getUpdates?offset={TELEGRAM_OFFSET}&timeout=20", timeout=25)
            if res.status_code == 200:
                data = res.json()
                for result in data.get("result", []):
                    TELEGRAM_OFFSET = result["update_id"] + 1
                    mensaje = result.get("message", {})
                    
                    # Verificar si es el jefe escribiendo en el chat autorizado
                    if str(mensaje.get("chat", {}).get("id")) == TELEGRAM_CHAT_ID:
                        # Verificar si está respondiendo a una alerta
                        if "reply_to_message" in mensaje and "text" in mensaje:
                            texto_respuesta_jefe = mensaje["text"]
                            # Telegram puede tener el texto en 'text' o en 'caption' si fue una alerta con foto
                            msg_original = mensaje["reply_to_message"]
                            texto_original = msg_original.get("text", "") or msg_original.get("caption", "")
                            
                            # Buscar el número de teléfono con Expresiones Regulares
                            match = re.search(r"\+(\d{10,15})", texto_original)
                            if match:
                                telefono_destino = match.group(1)
                                
                                # Extraer el bot receptor si está en tu BD, si no, usa default
                                id_bot_meta = os.getenv("META_PHONE_ID", "")
                                
                                # Enviamos el mensaje del Jefe por WhatsApp
                                exito = enviar_mensaje_whatsapp(telefono_destino, texto_respuesta_jefe, id_bot_meta)
                                
                                if exito:
                                    notificar_telegram(f"✅ *Respuesta enviada al cliente (+{telefono_destino}):*\n_{texto_respuesta_jefe}_")
                                else:
                                    notificar_telegram(f"❌ Error intentando enviar mensaje a +{telefono_destino}")
        except Exception:
            pass # Ignoramos errores de red temporales para que el hilo no muera
        time.sleep(2)

# =====================================================================
# 6. ENVÍO Y DESCARGA DE MENSAJES META GRAPH API
# =====================================================================
def enviar_mensaje_whatsapp(telefono_destino, mensaje_texto, telefono_bot=None):
    token, phone_number_id = obtener_credenciales_meta(telefono_bot)

    if not token or not phone_number_id:
        msg_err = f"Faltan credenciales META_ACCESS_TOKEN o META_PHONE_ID para el bot: {telefono_bot}"
        print(f"❌ Error: {msg_err}")
        registrar_log_sistema("ERROR", msg_err)
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
            msg_err = f"Error de API Meta ({response.status_code}): {response.text}"
            print(f"❌ {msg_err}")
            registrar_log_sistema("ERROR", msg_err)
            return False
    except Exception as e:
        msg_err = f"Error de conexión enviando a WhatsApp: {e}"
        print(f"❌ {msg_err}")
        registrar_log_sistema("ERROR", msg_err)
        return False

def descargar_multimedia_whatsapp(media_id, telefono_bot=None, extension=".ogg"):
    """Descarga de forma segura audios y comprobantes de pago fotográficos de Meta."""
    token, _ = obtener_credenciales_meta(telefono_bot)
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
                    nombre_archivo = ruta_escribible(f"temp_media_{media_id}{extension}")
                    with open(nombre_archivo, "wb") as f:
                        f.write(res_data.content)
                    return nombre_archivo
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error descargando multimedia de Meta: {e}")
    return None

# =====================================================================
# 7. CEREBRO IA - CONEXIÓN DIRECTA A ANTHROPIC (Haiku)
# =====================================================================
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

def _llamar_anthropic(system_prompt, mensajes_chat):
    if not ANTHROPIC_API_KEY:
        registrar_log_sistema("ERROR", "ANTHROPIC_API_KEY no está configurada en seguridad.env")
        return "Estoy teniendo un inconveniente técnico. Un asesor de Todomax te atenderá en breve."

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 400,
        "temperature": 0.5,
        "system": system_prompt,
        "messages": mensajes_chat,
    }
    try:
        res = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            texto = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            if texto:
                return texto
            registrar_log_sistema("ERROR", f"Anthropic devolvió respuesta vacía: {str(data)[:150]}")
        else:
            registrar_log_sistema("ERROR", f"Anthropic HTTP {res.status_code}: {res.text[:200]}")
    except Exception as e:
        registrar_log_sistema("ERROR", f"Fallo al contactar Anthropic: {e}")
    return "Tuve un pequeño inconveniente técnico. ¿Podrías repetirme eso último?"

def generar_respuesta_ia(mensaje_usuario, historial, prompt_maestro, telefono_cliente):
    """Arma el historial (roles alternados, empezando por 'user') y consulta a Haiku."""
    turnos = []
    for msg in historial[-8:]:
        if msg.startswith("Cliente:"):
            turnos.append(("user", msg.replace("Cliente:", "", 1).strip()))
        elif msg.startswith("Bot:") or msg.startswith("Agente:"):
            turnos.append(("assistant", msg.split(":", 1)[1].strip()))
    turnos.append(("user", mensaje_usuario))

    mensajes_chat = []
    for rol, contenido in turnos:
        if not contenido:
            continue
        if mensajes_chat and mensajes_chat[-1]["role"] == rol:
            mensajes_chat[-1]["content"] += "\n" + contenido
        else:
            mensajes_chat.append({"role": rol, "content": contenido})
    while mensajes_chat and mensajes_chat[0]["role"] != "user":
        mensajes_chat.pop(0)

    return _llamar_anthropic(prompt_maestro, mensajes_chat).strip()

# =====================================================================
# 8. SEGUNDO PLANO: REVISIÓN DE INACTIVIDAD Y REPORTES TELEGRAM
# =====================================================================
def tarea_verificar_inactividad_24h():
    print("⏰ [Scheduler] Ejecutando barrido de seguimiento 24h...")
    try:
        conn = db.get_db_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
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
                conn_upd.execute("PRAGMA journal_mode=WAL;")
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
        registrar_log_sistema("ERROR", f"Error en la tarea programada de seguimiento 24h: {e}")

def tarea_asistente_ventas_telegram():
    """Genera un reporte diario de métricas y consejos de remarketing vía Telegram."""
    print("⏰ [Scheduler] Analizando métricas para el reporte de Telegram...")
    try:
        conn = sqlite3.connect(db.DB_PATH)
        cursor = conn.cursor()
        
        hace_24h = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT COUNT(*) FROM leads WHERE ultima_interaccion < ? AND estado_calificacion = 'Nuevo Prospecto'", (hace_24h,))
        res = cursor.fetchone()
        abandonos = res[0] if res else 0
        
        cursor.execute("CREATE TABLE IF NOT EXISTS ventas_cerradas (id INTEGER PRIMARY KEY, telefono TEXT, detalles TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("SELECT COUNT(*) FROM ventas_cerradas WHERE fecha > ?", (hace_24h,))
        res2 = cursor.fetchone()
        ventas_hoy = res2[0] if res2 else 0
        conn.close()
        
        if abandonos > 0 or ventas_hoy > 0:
            mensaje = f"🦈 *REPORTE DE VENTAS Y ESTRATEGIA (CRM)* 🦈\n\n"
            mensaje += f"📦 *Ventas Cerradas (24h):* {ventas_hoy}\n"
            mensaje += f"⚠️ *Carritos Abandonados:* {abandonos}\n\n"
            mensaje += "💡 *Consejo Tiburón:* Revisa los prospectos inactivos en tu CRM y ofréceles atención directa para cerrar la venta."
            notificar_telegram(mensaje)
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error en reporte Telegram: {e}")

if not EN_VERCEL:  # Serverless: no hay procesos en segundo plano persistentes
    scheduler = BackgroundScheduler()
    scheduler.add_job(tarea_verificar_inactividad_24h, 'interval', hours=1)
    scheduler.add_job(tarea_asistente_ventas_telegram, 'cron', hour=18, minute=30)
    scheduler.start()

# =====================================================================
# 9. PROCESAMIENTO ASÍNCRONO DE MENSAJES
# =====================================================================
def verificar_y_cobrar_conversacion_saas(empresa_id, telefono_cliente):
    try:
        conn = db.get_db_connection()
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        
        cursor.execute("SELECT creditos FROM empresas_saas WHERE id = ?", (empresa_id,))
        empresa = cursor.fetchone()
        if not empresa or empresa["creditos"] <= 0:
            conn.close()
            return False
            
        cursor.execute("SELECT ultima_interaccion FROM leads WHERE telefono = ?", (telefono_cliente,))
        lead = cursor.fetchone()
        
        ahora = datetime.now()
        es_nueva_conversacion = True
        
        if lead and lead["ultima_interaccion"]:
            try:
                ultima = datetime.strptime(lead["ultima_interaccion"], "%Y-%m-%d %H:%M:%S")
                if (ahora - ultima).total_seconds() < 86400:
                    es_nueva_conversacion = False
            except Exception:
                pass
                
        if es_nueva_conversacion:
            cursor.execute("""
                UPDATE empresas_saas 
                SET creditos = creditos - 1 
                WHERE id = ? AND creditos > 0
            """, (empresa_id,))
            conn.commit()
            print(f"💳 [SaaS] Nueva conversación iniciada ($0.25 / 1 crédito descontado) para empresa ID: {empresa_id}")
            
        conn.close()
        return True
    except sqlite3.OperationalError:
        return True
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error validando crédito por conversación SaaS: {e}")
        return True

def procesar_mensaje_en_segundo_plane(telefono_cliente, texto_cliente, telefono_bot_receptor, es_audio=False, ruta_media=None, es_imagen=False, id_imagen=None):
    try:
        print(f"\n📩 Procesando en segundo plano mensaje de ({telefono_cliente}) para bot ID Meta ({telefono_bot_receptor}): {texto_cliente or '[Nota de Voz / Imagen]'}")

        # 🔥 NUEVA LÓGICA: ENVÍO INMEDIATO DE LA IMAGEN A TELEGRAM 🔥
        if es_imagen and ruta_media and os.path.exists(ruta_media):
            print("📸 Imagen detectada. Disparando comprobante a Telegram de inmediato...")
            mensaje_foto = f"📸 *NUEVO COMPROBANTE RECIBIDO*\n*WhatsApp Cliente:* +{telefono_cliente}\n\n_El cliente acaba de enviar esta imagen. Sofía continuará conversando si faltan datos del pedido._\n[Responder en WhatsApp](https://wa.me/{telefono_cliente})"
            notificar_telegram(mensaje_foto, ruta_media)
            
            # Eliminamos la foto de la memoria para que no se envíe duplicada
            try:
                os.remove(ruta_media)
            except Exception:
                pass
            ruta_media = None

        resultado_sofia = evaluar_mensaje_sofia(
            remitente=telefono_cliente,
            texto_mensaje=texto_cliente,
            es_audio=es_audio,
            funcion_envio_meta=lambda dest, msg: enviar_mensaje_whatsapp(dest, msg, telefono_bot_receptor),
            ruta_audio=ruta_media
        )

        if resultado_sofia["atendido"]:
            if ruta_media and os.path.exists(ruta_media):
                os.remove(ruta_media)
            return

        if es_audio and not resultado_sofia["atendido"]:
            texto_cliente = resultado_sofia["texto_limpio"]
            if ruta_media and os.path.exists(ruta_media):
                os.remove(ruta_media)

        # 🛡️ CAPA ANTI-SPAM: texto estático, cero tokens de IA
        historial = db.obtener_o_crear_lead(telefono_cliente, telefono_bot_receptor)
        respuesta_estatica = respuesta_anti_spam(texto_cliente)
        if respuesta_estatica:
            enviar_mensaje_whatsapp(telefono_cliente, respuesta_estatica, telefono_bot_receptor)
            db.guardar_historial_lead(telefono_cliente, texto_cliente, respuesta_estatica)
            print(f"🛡️ Anti-spam: respuesta estática enviada a {telefono_cliente} (sin IA).")
            return

        # LIMITE: maximo 6 mensajes con IA por usuario cada 24h (cero tokens al superarlo)
        if limite_ia_alcanzado(telefono_cliente):
            enviar_mensaje_whatsapp(telefono_cliente, MENSAJE_LIMITE, telefono_bot_receptor)
            print(f"Limite de IA alcanzado para {telefono_cliente}: mensaje fijo (sin IA).")
            return

        prompt_definitivo = f"{SYSTEM_PROMPT_SOFIA}\n\n{REGLAS_SISTEMA_CRM}\n\n{bloque_catalogo_vivo()}"

        # LOMITO SÚPER IMPORTANTE: Se inyecta el ID del bot receptor para aislar el Lead
        respuesta_bot_cruda = generar_respuesta_ia(texto_cliente, historial, prompt_definitivo, telefono_cliente)

        mensaje_para_lead = respuesta_bot_cruda
        mensaje_telegram_alerta = None

        # -----------------------------------------------------
        # 🧩 ENRUTAMIENTO DE ALERTAS (AHORA A TELEGRAM Y CRM)
        # -----------------------------------------------------
        if respuesta_bot_cruda and "ALERTA_JEFE:" in respuesta_bot_cruda:
            separador = "[ALERTA_JEFE:" if "[ALERTA_JEFE:" in respuesta_bot_cruda else "ALERTA_JEFE:"
            partes = respuesta_bot_cruda.split(separador)
            mensaje_para_lead = partes[0].strip()
            
            if not mensaje_para_lead:
                mensaje_para_lead = "¡Perfecto! Ya tengo todos tus datos y la disponibilidad. Le paso la información al equipo de inmediato y se comunicarán contigo para confirmar. 🚀"
                
            if len(partes) > 1:
                alerta_sucia = partes[1].replace("]", "").replace("[", "").strip()
                mensaje_telegram_alerta = f"🚨 *CLIENTE REQUIERE ASESOR (TODOMAX)*\n*WhatsApp Cliente:* +{telefono_cliente}\n\n{alerta_sucia}\n\n[Responder en WhatsApp](https://wa.me/{telefono_cliente})"


        # 🔥 LÓGICA DE LIMPIEZA TOTAL DE MULETILLAS Y BASURA FINAL 🔥
        muletillas_borrar = [
            "aquí tienes los detalles:", "aqui tienes los detalles:",
            "aquí está tu nota", "aqui esta tu nota", 
            "nota de entrega generada:", "detalles de tu pedido:",
            "los detalles de tu orden:", "aquí te dejo los datos"
        ]
        texto_minuscula = mensaje_para_lead.lower()
        for muletilla in muletillas_borrar:
            if muletilla in texto_minuscula:
                idx = texto_minuscula.rfind(muletilla)
                mensaje_para_lead = mensaje_para_lead[:idx].strip()

        # Eliminar asteriscos, guiones o dos puntos que quedan sueltos antes del bloque borrado
        mensaje_para_lead = mensaje_para_lead.rstrip("*: \n-")

        if not EN_VERCEL:
            tiempo_espera = random.randint(5, 8)
            print(f"⏳ Simulando tiempo de lectura humana ({tiempo_espera}s)...")
            time.sleep(tiempo_espera)

        enviado = enviar_mensaje_whatsapp(telefono_cliente, mensaje_para_lead, telefono_bot_receptor)

        db.guardar_historial_lead(telefono_cliente, texto_cliente, mensaje_para_lead)
        print(f"🤖 Respuesta enviada y guardada: {mensaje_para_lead}")

        if mensaje_telegram_alerta:
            print(f"📲 Notificando a TELEGRAM sobre el escalamiento a asesor...")
            exito_telegram = notificar_telegram(mensaje_telegram_alerta, ruta_media)
            if exito_telegram:
                print("✅ Notificación enviada a Telegram con éxito.")
            else:
                print("❌ ERROR enviando la alerta a Telegram.")

    except Exception as e:
        registrar_log_sistema("ERROR", f"Error en hilo de procesamiento: {e}")
    finally:
        if telefono_cliente in locks_por_telefono:
            locks_por_telefono[telefono_cliente].release()
            try:
                if not locks_por_telefono[telefono_cliente].locked():
                    del locks_por_telefono[telefono_cliente]
            except Exception:
                pass
                
        if ruta_media and os.path.exists(ruta_media):
            try:
                os.remove(ruta_media)
            except Exception:
                pass

# =====================================================================
# 10. RUTAS DEL SERVIDOR WEB Y WEBHOOK DE META
# =====================================================================
@app.route("/", methods=["GET"])
def verificacion_de_salud():
    return jsonify({
        "agencia": "Todomax",
        "motor": "Inteligencia Artificial - Sofía (Todomax) · Anthropic Haiku",
        "estado": "100% Operativo y en línea 🚀",
        "puerto": 5000
    }), 200

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
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
    body = request.get_json()

    try:
        if body.get("object") == "whatsapp_business_account":
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    metadata = value.get("metadata", {})
                    telefono_bot_receptor = metadata.get("phone_number_id", "")

                    if "messages" in value:
                        for mensaje in value["messages"]:
                            msg_id = mensaje.get("id")

                            if db.mensaje_yaml_procesado(msg_id) if hasattr(db, 'mensaje_yaml_procesado') else db.mensaje_ya_procesado(msg_id):
                                print(f"🛡️ Webhook duplicado bloqueado por ID ({msg_id}).")
                                continue

                            tipo_mensaje = mensaje.get("type")
                            telefono_cliente = mensaje["from"]
                            texto_cliente = ""
                            es_audio = False
                            ruta_media = None
                            es_imagen = False
                            id_imagen = None

                            if tipo_mensaje == "text":
                                texto_cliente = mensaje["text"]["body"]
                            elif tipo_mensaje == "audio":
                                es_audio = True
                                audio_id = mensaje["audio"]["id"]
                                ruta_media = descargar_multimedia_whatsapp(audio_id, telefono_bot_receptor, ".ogg")
                            elif tipo_mensaje == "image":
                                es_imagen = True
                                id_imagen = mensaje["image"]["id"]
                                texto_caption = mensaje.get("image", {}).get("caption", "")
                                texto_cliente = f"[El cliente adjuntó una IMAGEN/COMPROBANTE] {texto_caption}"
                                ruta_media = descargar_multimedia_whatsapp(id_imagen, telefono_bot_receptor, ".jpg")
                            else:
                                continue

                            with lock_global:
                                if telefono_cliente not in locks_por_telefono:
                                    locks_por_telefono[telefono_cliente] = threading.Lock()

                            if not locks_por_telefono[telefono_cliente].acquire(blocking=False):
                                print(f"🛡️ Bloqueo de concurrencia para {telefono_cliente}. Ignorando.")
                                continue

                            args_trabajo = (telefono_cliente, texto_cliente, telefono_bot_receptor, es_audio, ruta_media, es_imagen, id_imagen)
                            if EN_VERCEL:
                                # Serverless: el proceso se congela al responder, se procesa en linea
                                procesar_mensaje_en_segundo_plane(*args_trabajo)
                            else:
                                threading.Thread(target=procesar_mensaje_en_segundo_plane, args=args_trabajo).start()

    except Exception as e:
        registrar_log_sistema("ERROR", f"Error en webhook: {e}")

    return jsonify({"status": "received"}), 200

# =====================================================================
# 11. ENDPOINTS DE LA APLICACIÓN CLIENTE (APP CRM FRONTEND)
# =====================================================================
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    
    try:
        conn = db.get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre_empresa, meta_phone_id FROM empresas_saas WHERE email = ? AND password = ?", (email, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return jsonify({"exito": True, "empresa_id": user["id"], "nombre": user["nombre_empresa"], "meta_phone_id": user["meta_phone_id"]}), 200
        else:
            return jsonify({"exito": False, "mensaje": "Credenciales inválidas"}), 401
    except Exception as e:
        return jsonify({"exito": False, "error": str(e)}), 500

@app.route("/api/crm/leads", methods=["GET"])
def api_obtener_leads():
    empresa_id = request.args.get("empresa_id")
    return jsonify({"exito": True, "mensaje": "Aquí se devolverán los leads asociados a esta empresa."}), 200

@app.route("/api/crm/bot_config", methods=["POST"])
def api_configurar_bot():
    data = request.get_json()
    empresa_id = data.get("empresa_id")
    nuevo_prompt = data.get("prompt_maestro")
    
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE empresas_saas SET prompt_maestro = ? WHERE id = ?", (nuevo_prompt, empresa_id))
        conn.commit()
        conn.close()
        return jsonify({"exito": True, "mensaje": "Identidad del agente actualizada exitosamente."}), 200
    except Exception as e:
        return jsonify({"exito": False, "error": str(e)}), 500

# =====================================================================
# 12. PUENTE DE MANDO PARA JARVIS - Endpoint de Control Operativo
# =====================================================================
@app.route("/api/orden_jarvis", methods=["POST"])
def orden_jarvis():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "exito": False,
                "mensaje": "JSON inválido o vacío",
                "detalle": {}
            }), 400
        
        token_recibido = data.get("token_autenticacion", "")
        if not JARVIS_AUTH_TOKEN or token_recibido != JARVIS_AUTH_TOKEN:
            registrar_log_sistema("WARNING", f"Intento de acceso no autorizado a /api/orden_jarvis desde IP: {request.remote_addr}")
            return jsonify({
                "exito": False,
                "mensaje": "Token de autenticación inválido",
                "detalle": {}
            }), 401
        
        accion = data.get("accion", "")
        
        if accion == "enviar_mensaje":
            numero_destino = data.get("numero_destino", "")
            mensaje = data.get("mensaje", "")
            
            if not numero_destino or not mensaje:
                return jsonify({
                    "exito": False,
                    "mensaje": "Faltan parámetros requeridos: numero_destino y mensaje",
                    "detalle": {}
                }), 400
            
            exito = enviar_mensaje_whatsapp(numero_destino, mensaje)
            
            if exito:
                registrar_log_sistema("INFO", f"[JARVIS] Mensaje enviado a {numero_destino}: {mensaje[:50]}...")
                return jsonify({
                    "exito": True,
                    "mensaje": "Mensaje enviado correctamente",
                    "detalle": {
                        "numero_destino": numero_destino,
                        "longitud_mensaje": len(mensaje)
                    }
                }), 200
            else:
                registrar_log_sistema("ERROR", f"[JARVIS] Fallo al enviar mensaje a {numero_destino}")
                return jsonify({
                    "exito": False,
                    "mensaje": "Error al enviar mensaje vía Meta Graph API",
                    "detalle": {}
                }), 500
        
        else:
            return jsonify({
                "exito": False,
                "mensaje": f"Acción no soportada: {accion}. Acciones válidas: enviar_mensaje",
                "detalle": {}
            }), 400
            
    except Exception as e:
        registrar_log_sistema("ERROR", f"Error en endpoint /api/orden_jarvis: {e}")
        return jsonify({
            "exito": False,
            "mensaje": "Error interno del servidor",
            "detalle": {"error": str(e)}
        }), 500

# =====================================================================
# 13. INICIO DEL SERVIDOR
# =====================================================================
if __name__ == "__main__":
    # 🔥 INICIAMOS EL RADAR DE TELEGRAM 🔥
    threading.Thread(target=hilo_escuchar_telegram, daemon=True).start()

    print("==========================================================")
    print("🚀 SERVIDOR TELOTENGO SOLUTIONS (CASCADA 7 NIVELES & SOFÍA) LISTO")
    print("==========================================================")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
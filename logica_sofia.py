# =====================================================================
# ARCHIVO: logica_sofia.py (100% COMPLETO Y LIBRE DE ERRORES)
# MÓDULO DE INTELIGENCIA LÓGICA, TRANSCRIPCIÓN LOCAL Y COMANDOS
# =====================================================================
import sqlite3
import os
import speech_recognition as sr
from pydub import AudioSegment

# =====================================================================
# CONFIGURACIÓN DE CONSTANTES DEL SISTEMA
# =====================================================================
NUMERO_JEFE = os.getenv("NUMERO_JEFE", "584245885477")

DATOS_NEGOCIO = {
    "nombre": "Telotengo Solutions",
    "promesa": "Automatización con IA 24/7 para WhatsApp que atiende, califica y remata ventas por ti, más desarrollo de cualquier ecosistema o proyecto digital a medida. ¡Una inversión que se paga sola desde el primer mes! 🚀",
    "agendamento_whatsapp": "https://wa.me/584245885477",
    "calendario_reuniones": "https://api.leadconnectorhq.com/widget/booking/cHgLoMCk71bch2PmxVee"
}

# =====================================================================
# MÓDULO DE ESCUCHA GRATUITA Y LOCAL (SIN PLATAFORMAS DE TERCEROS)
# =====================================================================
def transcribir_audio_local_gratis(ruta_archivo_audio):
    """Convierte una nota de voz de WhatsApp en texto plano usando recursos locales de tu PC."""
    if not ruta_archivo_audio or not os.path.exists(ruta_archivo_audio):
        print("⚠️ No se encontró el archivo de audio en disco para transcribir.")
        return ""

    try:
        print(f"🎙️ [Sofía Escuchando] Procesando audio local gratuito: {ruta_archivo_audio}...")
        
        archivo_wav = f"{ruta_archivo_audio}_temp.wav"
        audio = AudioSegment.from_file(ruta_archivo_audio)
        audio.export(archivo_wav, format="wav")

        reconocedor = sr.Recognizer()
        with sr.AudioFile(archivo_wav) as fuente:
            datos_audio = reconocedor.record(fuente)
            texto_transcrito = reconocedor.recognize_google(datos_audio, language="es-ES")
            print(f"✅ [Voz convertida a texto exitosamente]: '{texto_transcrito}'")
            
            if os.path.exists(archivo_wav):
                os.remove(archivo_wav)
            return texto_transcrito
            
    except sr.UnknownValueError:
        print("⚠️ El motor gratuito no pudo entender las palabras en el audio (habla incomprensible).")
        return ""
    except Exception as error:
        print(f"❌ Error técnico en la transcripción local gratuita: {error}")
        return ""

# =====================================================================
# FUNCIÓN PRINCIPAL DE FILTRADO Y ENRUTAMIENTO LÓGICO
# =====================================================================
def evaluar_mensaje_sofia(remitente, texto_mensaje, es_audio, funcion_envio_meta, ruta_audio=None):
    """Evaluador lógico que decide si Sofía responde o si pasa a Groq Cloud."""
    texto_limpio = str(texto_mensaje).strip() if texto_mensaje else ""

    # 1. ESCUCHA ACTIVA DE NOTAS DE VOZ
    if es_audio and ruta_audio:
        texto_escuchado = transcribir_audio_local_gratis(ruta_audio)
        if texto_escuchado != "":
            texto_limpio = texto_escuchado.strip()
        else:
            respuesta_inaudible = "¡Hola! Recibí tu nota de voz 🎙️, pero se escuchaba un poco interferida y no logré entenderla bien. ¿Podrías repetirla o escribírmela brevemente por favor?"
            funcion_envio_meta(remitente, respuesta_inaudible)
            return {"atendido": True, "texto_limpio": ""}

    texto_mayusc = texto_limpio.upper()
    texto_minusc = texto_limpio.lower()

    # 2. MÓDULO EXCLUSIVO PARA EL ADMINISTRADOR ("EL JEFE")
    if remitente == NUMERO_JEFE:
        
        if texto_mayusc == "REPORTE":
            try:
                conexion = sqlite3.connect("crm_telotengo.db")
                cursor = conexion.cursor()
                cursor.execute("SELECT nombre, apellido, tipo_contacto, etapa FROM leads")
                filas = cursor.fetchall()
                conexion.close()

                total_leads = len(filas)
                reporte = f"📊 *REPORTE EJECUTIVO DEL DÍA (SOFÍA)*\n\n"
                reporte += f"👥 Total de leads en base de datos: {total_leads}\n\n"
                
                ultimos_cinco = filas[-5:] if total_leads >= 5 else filas
                for indice, lead in enumerate(ultimos_cinco, start=1):
                    nombre = lead[0] or "Sin nombre"
                    apellido = lead[1] or ""
                    origen = lead[2] or "Directo"
                    etapa = lead[3] or "Nuevo"
                    reporte += f"{indice}. *{nombre} {apellido}*\n   Origen: {origen} | Etapa: {etapa}\n"

                funcion_envio_meta(remitente, reporte)
            except Exception as error:
                print(f"❌ Error al consultar SQLite para el reporte: {error}")
                funcion_envio_meta(remitente, "❌ Error técnico al intentar leer la base de datos crm_telotengo.db.")
            return {"atendido": True, "texto_limpio": texto_limpio}

        if texto_minusc.startswith("lead:"):
            nombre_busqueda = texto_limpio[5:].strip()
            try:
                conexion = sqlite3.connect("crm_telotengo.db")
                cursor = conexion.cursor()
                cursor.execute("SELECT nombre, apellido, telefono, tipo_contacto, referido_por, etapa FROM leads WHERE nombre LIKE ?", (f"%{nombre_busqueda}%",))
                row = cursor.fetchone()
                conexion.close()

                if not row:
                    funcion_envio_meta(remitente, f'❌ No se encontró ningún lead que coincida con: "{nombre_busqueda}"')
                else:
                    info_lead = f"👤 *INFORMACIÓN DETALLADA DEL LEAD*\n\n"
                    info_lead += f"• *Nombre:* {row[0]} {row[1] or ''}\n"
                    info_lead += f"• *Teléfono:* {row[2] or 'No registrado'}\n"
                    info_lead += f"• *Tipo:* {row[3] or 'Prospecto'}\n"
                    info_lead += f"• *Referido por:* {row[4] or 'N/A'}\n"
                    info_lead += f"• *Etapa:* {row[5] or 'Seguimiento'}\n"
                    funcion_envio_meta(remitente, info_lead)
            except Exception as error:
                print(f"❌ Error en búsqueda de lead: {error}")
                funcion_envio_meta(remitente, "❌ Error al buscar en la base de datos.")
            return {"atendido": True, "texto_limpio": texto_limpio}

        respuesta_jefe = "¡Hola, Jefe! 🫡 Le reconozco perfectamente. Sofía a sus órdenes.\n\n"
        respuesta_jefe += "📌 *SUS COMANDOS EJECUTIVOS DISPONIBLES (POR TEXTO O VOZ):*\n"
        respuesta_jefe += "• Escriba o diga *REPORTE* para ver el resumen general de leads.\n"
        respuesta_jefe += "• Escriba o diga *lead: Nombre* para buscar datos de un cliente (ej: lead: Juan).\n\n"
        respuesta_jefe += "*(Flujo de IA de ventas pausado en este chat para proteger su CRM y saldo)*. ¡Quedo atenta a sus instrucciones! 🚀"

        funcion_envio_meta(remitente, respuesta_jefe)
        return {"atendido": True, "texto_limpio": texto_limpio}

    # 3. MÓDULO COMERCIAL PARA CLIENTES NORMALES (IMPULSO A LA COMPRA)
    palabras_clave_compra = ["agendar", "reunión", "reunion", "precio", "comprar", "información", "informacion", "contacto", "cita"]
    if any(palabra in texto_minusc for palabra in palabras_clave_compra):
        respuesta_comercial = f"¡Excelente decisión! {DATOS_NEGOCIO['promesa']}\n\n"
        respuesta_comercial += f"Puedes agendar tu reunión directamente aquí:\n📅 {DATOS_NEGOCIO['calendario_reuniones']}\n\n"
        respuesta_comercial += f"O escribirnos por WhatsApp directo:\n💬 {DATOS_NEGOCIO['agendamento_whatsapp']}"

        funcion_envio_meta(remitente, respuesta_comercial)
        return {"atendido": True, "texto_limpio": texto_limpio}

    # 4. RETORNO PARA GROQ CLOUD
    return {"atendido": False, "texto_limpio": texto_limpio}
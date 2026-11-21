# =====================================================================
# ANTI-SPAM: filtro previo a la IA. Si devuelve texto, NO se llama a Anthropic.
# =====================================================================
import re
import unicodedata

URL_TIENDA = "https://www.importadoratodomax.com"
URL_WHATSAPP_ADMIN = "https://wa.me/584225160056"  # WhatsApp oficial de administración (+58 422-5160056)

# Respuestas fijas (cero IA, cero productos inventados). NUNCA piden "número de referencia".
MSG_SALUDO = (
    "¡Hola! 😊 Qué gusto saludarte, soy Sofía de Importadora TodoMax. ¿En qué te puedo ayudar hoy? "
    f"Si quieres ver todo lo que tenemos, entra a nuestro catálogo: {URL_TIENDA}"
)
MSG_CATALOGO = (
    "¡Claro que sí! 😊 Aquí puedes ver todo nuestro catálogo con precios y disponibilidad al día: "
    f"{URL_TIENDA}\n"
    "Si algún producto te llama la atención, dime cuál y con gusto te doy los detalles."
)
MSG_ESTATUS_PEDIDO = (
    "¡Con mucho gusto! 😊 Para consultar el estatus de tu pedido, por favor comunícate directamente con "
    f"nuestro equipo de administración, ellos te darán información al instante: {URL_WHATSAPP_ADMIN}"
)
# Si la IA falla o da timeout (se usa desde servidor.py)
MSG_FALLO_IA = (
    "¡Ay, disculpa! 🙏 Tuve un breve inconveniente y no pude responderte bien. Mientras tanto, puedes ver "
    f"nuestro catálogo aquí: {URL_TIENDA}\n"
    f"Y si prefieres atención directa, escríbele a administración: {URL_WHATSAPP_ADMIN}"
)

SALUDOS_GENERICOS = {
    "hola", "holaa", "holaaa", "ola", "ok", "okay", "oka", "okey", "listo", "vale", "dale",
    "buenas", "buenos dias", "buen dia", "buenas tardes", "buenas noches",
    "hey", "hi", "hello", "gracias", "saludos", "buenass",
}

_RE_NO_ALFANUM = re.compile(r"[^\w\s]", re.UNICODE)

# Cliente pide ver el catálogo / qué se vende (texto ya normalizado: minúsculas, sin tildes)
_RE_CATALOGO = re.compile(
    r"\bcatalogo\b|\bver (los )?productos\b|\bque (venden|vendes|vende|tienen|tienes|manejan|manejas)\b|"
    r"\bque productos\b|\bproductos disponibles\b|\blista de productos\b|\bque ofrecen\b"
)
# Cliente pregunta por el estatus/trámite de un pedido
_RE_ESTATUS_PEDIDO = re.compile(
    r"\b(estatus|estado|status|seguimiento|tracking|rastreo|rastrear)\b.*\b(pedido|orden|compra|envio|paquete)\b|"
    r"\b(pedido|orden|compra|envio|paquete)\b.*\b(estatus|estado|status|seguimiento|tracking|rastreo|llega|"
    r"llegado|tramite|procesando|donde esta|cuando)\b|"
    r"\bdonde (esta|va|anda) mi (pedido|compra|orden|paquete|envio)\b"
)


LIMITE_MENSAJES_IA = 6
VENTANA_HORAS = 24

# Mensaje cuando el cliente ya superó el cupo (cero tokens de IA)
MENSAJE_LIMITE = (
    "¡Gracias por escribirnos! 🙌 Ya alcanzamos el límite de mensajes automáticos por hoy. A partir de "
    f"este momento puedes seguir hablando directamente con nuestro equipo de administración: {URL_WHATSAPP_ADMIN}\n"
    f"Y recuerda que también puedes completar tu pedido en {URL_TIENDA}"
)
# Aviso que se agrega al ÚLTIMO mensaje permitido
AVISO_ULTIMO_MENSAJE = (
    "\n\n💛 Por cierto, con este mensaje llegamos al límite de mensajes por hoy. Desde ahora puedes seguir "
    f"hablando directamente con administración aquí: {URL_WHATSAPP_ADMIN}"
)


def limite_ia_alcanzado(telefono):
    """Consume 1 uso de IA del usuario (ventana 24h). True si ya superó el límite (no se debe llamar a la IA)."""
    import gestor_basedatos as db
    return not db.consumir_cupo_ia(telefono, LIMITE_MENSAJES_IA, VENTANA_HORAS)


def es_ultimo_mensaje_permitido(telefono):
    """True si el uso de IA recién consumido es el último permitido en la ventana."""
    import time
    import gestor_basedatos as db
    desde = time.time() - VENTANA_HORAS * 3600
    conn = db.get_db_connection()
    try:
        usados = conn.execute(
            "SELECT COUNT(*) FROM uso_ia WHERE telefono = ? AND ts >= ?", (telefono, desde)
        ).fetchone()[0]
    finally:
        conn.close()
    return usados >= LIMITE_MENSAJES_IA


def _normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _RE_NO_ALFANUM.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def respuesta_anti_spam(texto):
    """Devuelve un texto fijo (sin IA) para saludos, catálogo y consultas de pedido; si no, None.

    Nunca nombra productos ni pide referencias. Los mensajes con dígitos (posible referencia/producto)
    pasan a la IA salvo que sean consulta de estatus de pedido o de catálogo.
    """
    if not texto or not texto.strip():
        return MSG_SALUDO

    limpio = _normalizar(texto)
    if not limpio:  # solo emojis / símbolos
        return MSG_SALUDO

    if _RE_ESTATUS_PEDIDO.search(limpio):
        return MSG_ESTATUS_PEDIDO
    if _RE_CATALOGO.search(limpio):
        return MSG_CATALOGO
    if re.search(r"\d", texto):
        return None
    if limpio in SALUDOS_GENERICOS:
        return MSG_SALUDO
    return None


# =====================================================================
# COMPRAS DEL CHECKOUT (importadoratodomax.com): texto fijo, cero IA, sin límite
# Marcas exactas generadas por checkout/page.tsx:
#   *NUEVO PEDIDO: TMX-123456*, *CLIENTE:*, *📦 PRODUCTOS:*, *TOTAL:*,
#   *ENVÍO:* <GRATIS|Cobro en Destino> vía <courier>, *DIRECCIÓN:*, *💳 PAGO:*
# =====================================================================
_MSG_COMPRA_BASE = (
    "¡Gracias por tu compra en Importadora TodoMax! Ya hemos recibido tu compra. "
    "En los próximos minutos alguien de nuestro personal administrativo se comunicará "
    "contigo para coordinar la entrega o envío."
)
MSG_COMPRA_RETIRO = (
    "¡Gracias por tu compra en Importadora TodoMax! Ya hemos recibido tu compra. "
    "En los próximos minutos alguien de nuestro personal administrativo se comunicará "
    "contigo para agendar el momento de la entrega."
)
MSG_COMPRA_ENVIO = (
    "¡Gracias por tu compra en Importadora TodoMax! Ya hemos recibido tu compra. "
    "En los próximos minutos alguien de nuestro personal administrativo se comunicará "
    "contigo para indicarte exactamente el momento en que será realizado el envío y "
    "posteriormente tu código o ruta de envío."
)

_RE_PEDIDO = re.compile(r"NUEVO PEDIDO:\s*TMX-\d+", re.IGNORECASE)
_RE_LINEA_ENVIO = re.compile(r"\*ENV[ÍI]O:\*[^\n]*?\bv[íi]a\s+([^\n]+)", re.IGNORECASE)
_RE_LINEA_DIRECCION = re.compile(r"\*DIRECCI[ÓO]N:\*([^\n]*)", re.IGNORECASE)
_RE_RETIRO = re.compile(r"retiro|retirar|retira|pick\s*-?up|oficina|en tienda|personal", re.IGNORECASE)
_RE_ENVIO = re.compile(r"mrw|zoom|tealca|delivery|domicilio|nacional|env[ií]o|courier|encomienda", re.IGNORECASE)


def es_mensaje_compra_checkout(texto):
    if not texto:
        return False
    return bool(
        _RE_PEDIDO.search(texto)
        and "*CLIENTE:*" in texto
        and "PRODUCTOS:*" in texto
        and "*TOTAL:*" in texto
    )


def respuesta_compra_checkout(texto):
    """Si el texto es un resumen de compra del checkout devuelve el texto fijo
    (retiro / envío / base); si no, None. Nunca usa IA."""
    if not es_mensaje_compra_checkout(texto):
        return None
    m_envio = _RE_LINEA_ENVIO.search(texto)
    courier = m_envio.group(1).strip() if m_envio else ""
    m_dir = _RE_LINEA_DIRECCION.search(texto)
    direccion = m_dir.group(1) if m_dir else ""
    if _RE_RETIRO.search(courier) or re.search(r"retiro", direccion, re.IGNORECASE):
        return MSG_COMPRA_RETIRO
    if courier and _RE_ENVIO.search(courier):
        return MSG_COMPRA_ENVIO
    return _MSG_COMPRA_BASE

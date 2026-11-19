# =====================================================================
# ANTI-SPAM: filtro previo a la IA. Si devuelve texto, NO se llama a Anthropic.
# =====================================================================
import re
import unicodedata

RESPUESTA_ESTATICA = (
    "¡Hola! Soy Sofía de Todomax. Para procesar tu compra, por favor indícame "
    "tu número de referencia o detalles del pedido."
)

SALUDOS_GENERICOS = {
    "hola", "holaa", "holaaa", "ola", "ok", "okay", "oka", "okey", "listo", "vale", "dale",
    "precio", "precios", "buenas", "buenos dias", "buen dia", "buenas tardes", "buenas noches",
    "hey", "hi", "hello", "gracias", "saludos", "info", "informacion", "buenass",
}

_RE_NO_ALFANUM = re.compile(r"[^\w\s]", re.UNICODE)


LIMITE_MENSAJES_IA = 6
VENTANA_HORAS = 24

MENSAJE_LIMITE = (
    "¡Gracias por escribirnos! 🙌 Para seguir con tu compra o resolver tus dudas de forma "
    "inmediata, continúa directamente en nuestra tienda: https://www.importadoratodomax.com"
)


def limite_ia_alcanzado(telefono):
    """Consume 1 uso de IA del usuario (ventana 24h). True si ya superó el límite (no se debe llamar a la IA)."""
    import gestor_basedatos as db
    return not db.consumir_cupo_ia(telefono, LIMITE_MENSAJES_IA, VENTANA_HORAS)


def _normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _RE_NO_ALFANUM.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def respuesta_anti_spam(texto):
    """Devuelve RESPUESTA_ESTATICA si el mensaje no merece gastar tokens; si no, None.

    Excepción: un mensaje que contiene dígitos (posible referencia bancaria) siempre pasa.
    """
    if not texto or not texto.strip():
        return RESPUESTA_ESTATICA

    if re.search(r"\d", texto):
        return None

    limpio = _normalizar(texto)
    if not limpio:  # solo emojis / símbolos
        return RESPUESTA_ESTATICA
    if limpio in SALUDOS_GENERICOS:
        return RESPUESTA_ESTATICA
    if len(limpio.split()) < 3:
        return RESPUESTA_ESTATICA
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

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

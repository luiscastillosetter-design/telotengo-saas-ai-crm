"""Catálogo en vivo de importadoratodomax.com (caché en memoria de 10 min) y tasa BCV."""
import threading
import time

import requests

URL_TIENDA = "https://www.importadoratodomax.com"
URL_API_PRODUCTOS = f"{URL_TIENDA}/api/products"
TTL_CATALOGO = 600  # 10 minutos
TTL_BCV = 900

_lock = threading.Lock()
_cache = {"ts": 0.0, "productos": []}
_cache_bcv = {"ts": 0.0, "dato": None}

_FUENTES_BCV = [
    ("https://ve.dolarapi.com/v1/dolares/oficial", lambda j: float(j.get("promedio") or j.get("venta"))),
    ("https://pydolarve.org/api/v1/dollar?page=bcv&monitor=usd", lambda j: float(j.get("price"))),
]


def enlace_producto(pid):
    return f"{URL_TIENDA}/product/{pid}"


def obtener_productos():
    """Productos con stock. Usa caché 10 min; si la API falla devuelve el último caché válido."""
    with _lock:
        if _cache["productos"] and time.time() - _cache["ts"] < TTL_CATALOGO:
            return _cache["productos"]
        try:
            r = requests.get(URL_API_PRODUCTOS, timeout=8)
            r.raise_for_status()
            datos = r.json()
            if isinstance(datos, list):
                _cache["productos"] = [p for p in datos if isinstance(p, dict) and p.get("id") and (p.get("stock") or 0) > 0]
                _cache["ts"] = time.time()
        except Exception as e:
            print(f"⚠️ No se pudo consultar el catálogo en vivo: {e}")
        return _cache["productos"]


def obtener_tasa_bcv():
    """Tasa BCV (Bs por USD) con caché de 15 min, o None si no hay fuente disponible."""
    if _cache_bcv["dato"] and time.time() - _cache_bcv["ts"] < TTL_BCV:
        return _cache_bcv["dato"]
    for url, extraer in _FUENTES_BCV:
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                tasa = extraer(r.json())
                if tasa > 0:
                    _cache_bcv.update(ts=time.time(), dato=tasa)
                    return tasa
        except Exception:
            continue
    return _cache_bcv["dato"]


def _resumen(texto, n=120):
    s = " ".join(str(texto or "").split())
    # quita imágenes markdown del texto
    while "![" in s and "](" in s:
        a = s.index("![")
        b = s.find(")", a)
        if b == -1:
            break
        s = (s[:a] + s[b + 1:]).strip()
    return s if len(s) <= n else s[:n] + "…"


def bloque_catalogo_vivo():
    """Texto con el catálogo actual y enlaces exactos, listo para inyectar al prompt."""
    productos = obtener_productos()
    tasa = obtener_tasa_bcv()
    if tasa:
        txt_tasa = f"Tasa oficial BCV actual: Bs. {tasa:.2f} por USD. Equivalente en Bs. = precio USD × tasa (2 decimales)."
    else:
        txt_tasa = "La tasa BCV no está disponible ahora; si la piden, di que no pudiste consultarla y que la ven en la barra superior de la web."

    if not productos:
        lista = "(Catálogo no disponible en este momento: NO menciones productos ni precios; envía a " + URL_TIENDA + ")"
    else:
        filas = []
        for p in productos:
            pa = p.get("originalPrice")
            precio = p.get("price")
            oferta = ""
            if pa and precio and pa > precio:
                oferta = f" | OFERTA: antes ${pa} (-{round((1 - precio / pa) * 100)}%)"
            stock = p.get("stock", 0)
            disp = "Disponible" if stock > 5 else f"Últimas {stock} unidades"
            filas.append(
                f"- {p.get('title', '').strip()} | ${precio} USD{oferta} | {p.get('category', '')} | {disp} | "
                f"{_resumen(p.get('description'))} | Enlace: {enlace_producto(p['id'])}"
            )
        lista = "\n".join(filas)
    return f"{txt_tasa}\n\nCATÁLOGO EN VIVO (solo productos con stock):\n{lista}"

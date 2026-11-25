"""Catálogo en vivo de importadoratodomax.com (lectura en tiempo real, sin caché) y tasa BCV."""
import threading
import time

import requests

URL_TIENDA = "https://www.importadoratodomax.com"
URL_API_PRODUCTOS = f"{URL_TIENDA}/api/products"
TIMEOUT_CATALOGO = 5  # segundos, lectura en vivo
TTL_BCV = 900

_lock = threading.Lock()
_cache_bcv = {"ts": 0.0, "dato": None}

_FUENTES_BCV = [
    ("https://ve.dolarapi.com/v1/dolares/oficial", lambda j: float(j.get("promedio") or j.get("venta"))),
    ("https://pydolarve.org/api/v1/dollar?page=bcv&monitor=usd", lambda j: float(j.get("price"))),
]


def enlace_producto(pid):
    return f"{URL_TIENDA}/product/{pid}"


def obtener_productos():
    """Productos con stock, consultados EN VIVO en cada llamada (sin caché). Si la red falla devuelve []."""
    try:
        r = requests.get(URL_API_PRODUCTOS, timeout=TIMEOUT_CATALOGO)
        r.raise_for_status()
        datos = r.json()
        if not isinstance(datos, list):
            print(f"⚠️ Catálogo: la API devolvió {type(datos).__name__} en vez de lista")
            return []
        return [p for p in datos if isinstance(p, dict) and p.get("id") and (p.get("stock") or 0) > 0]
    except requests.exceptions.Timeout:
        print(f"⚠️ Catálogo: timeout ({TIMEOUT_CATALOGO}s) consultando la API de productos")
    except requests.exceptions.HTTPError as e:
        print(f"⚠️ Catálogo: HTTP {e.response.status_code} desde la API de productos")
    except ValueError as e:
        print(f"⚠️ Catálogo: JSON inválido desde la API de productos: {e}")
    except Exception as e:
        print(f"⚠️ No se pudo consultar el catálogo en vivo ({type(e).__name__}): {e}")
    return []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _nombres(lista):
    out = []
    for x in lista or []:
        n = x.get("name") if isinstance(x, dict) else x
        if n:
            out.append(str(n).strip())
    return out


def _tallas_con_stock(p):
    """Tallas con stock real > 0 (sizeStock dict/lista o variantes); sin datos de stock usa 'sizes'."""
    ss = p.get("sizeStock")
    tallas = []
    if isinstance(ss, dict) and ss:
        for k, v in ss.items():
            if isinstance(v, dict):  # {color: {talla: n}}
                tallas += [t for t, n in v.items() if _num(n) > 0]
            elif _num(v) > 0:
                tallas.append(k)
    elif isinstance(ss, list) and ss:
        for it in ss:
            if isinstance(it, dict):
                t = it.get("size") or it.get("talla") or it.get("name")
                if t and _num(it.get("stock", it.get("qty", 0))) > 0:
                    tallas.append(t)
    else:
        vs = p.get("variants")
        if isinstance(vs, list) and vs:
            for it in vs:
                if isinstance(it, dict) and it.get("size") and _num(it.get("stock", 0)) > 0:
                    tallas.append(it["size"])
        else:
            tallas = _nombres(p.get("sizes"))
    return list(dict.fromkeys(str(t) for t in tallas))


def _colores_con_stock(p):
    colores = _nombres(p.get("colors"))
    vs = p.get("variants")
    if isinstance(vs, list) and vs:
        con_stock = {str(it.get("color")) for it in vs if isinstance(it, dict) and it.get("color") and _num(it.get("stock", 0)) > 0}
        colores = [c for c in colores if c in con_stock] if colores else sorted(con_stock)
    return colores


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
            div = _num(p.get("divisaPrice"))
            divisa = f" | PRECIO EN DIVISAS ($): ${div:g} USD" if div > 0 and precio and div < _num(precio) else ""
            colores = _colores_con_stock(p)
            tallas = _tallas_con_stock(p)
            extra = ""
            if colores:
                extra += f" | Colores con stock: {', '.join(colores)}"
            if tallas:
                extra += f" | Tallas con stock: {', '.join(tallas)}"
            filas.append(
                f"- {p.get('title', '').strip()} | ${precio} USD{oferta}{divisa} | {p.get('category', '')} | {disp}{extra} | "
                f"{_resumen(p.get('description'))} | Enlace: {enlace_producto(p['id'])}"
            )
        lista = "\n".join(filas)
    return f"{txt_tasa}\n\nCATÁLOGO EN VIVO (solo productos con stock):\n{lista}"

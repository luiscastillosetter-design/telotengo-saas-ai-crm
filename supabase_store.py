"""Persistencia ligera en Supabase (REST/PostgREST) para Sofia WhatsApp.

Lee SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY del entorno. Si faltan, `habilitado()` es False y
el resto del sistema usa SQLite como respaldo. Toda funcion devuelve None ante error/timeout
para que el llamador caiga al respaldo SQLite sin romper el webhook.
"""
import os
import time

import requests

TIMEOUT = 3.5  # segundos


def _cfg():
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    return url, key


def habilitado():
    url, key = _cfg()
    return bool(url and key)


def _req(metodo, tabla, params=None, json_body=None, prefer=None):
    """Llama a PostgREST. Devuelve la respuesta o None si falla (nunca lanza, nunca imprime claves)."""
    url, key = _cfg()
    if not (url and key):
        return None
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        r = requests.request(metodo, f"{url}/rest/v1/{tabla}", params=params, json=json_body,
                             headers=headers, timeout=TIMEOUT)
        if r.status_code >= 400:
            print(f"⚠️ Supabase {tabla} HTTP {r.status_code}")
            return None
        return r
    except Exception as e:
        print(f"⚠️ Supabase {tabla} error: {type(e).__name__}")
        return None


# ---------- Anti-duplicados ----------
def mensaje_ya_procesado(msg_id):
    """True si ya existia, False si es nuevo (lo registra). None si Supabase fallo."""
    r = _req("POST", "sofia_wa_webhook_logs", params={"on_conflict": "msg_id"},
             json_body={"msg_id": msg_id},
             prefer="resolution=ignore-duplicates,return=representation")
    if r is None:
        return None
    try:
        return len(r.json()) == 0  # vacio = conflicto = duplicado
    except Exception:
        return None


# ---------- Historial ----------
def guardar_historial(telefono, mensaje_usuario, respuesta_bot):
    """Inserta turnos user/assistant. Devuelve True/None."""
    filas = []
    if mensaje_usuario:
        filas.append({"telefono": telefono, "role": "user", "content": mensaje_usuario})
    if respuesta_bot:
        filas.append({"telefono": telefono, "role": "assistant", "content": respuesta_bot})
    if not filas:
        return True
    r = _req("POST", "sofia_wa_historial", json_body=filas, prefer="return=minimal")
    return True if r is not None else None


def obtener_historial(telefono, limite=8):
    """Ultimos `limite` turnos en el formato legado ['Cliente: ..', 'Bot: ..'] (orden cronologico).
    None si Supabase fallo (el llamador usa SQLite)."""
    r = _req("GET", "sofia_wa_historial",
             params={"select": "role,content", "telefono": f"eq.{telefono}",
                     "order": "id.desc", "limit": str(limite)})
    if r is None:
        return None
    try:
        filas = list(reversed(r.json()))
        return [("Cliente: " if f["role"] == "user" else "Bot: ") + f["content"] for f in filas]
    except Exception:
        return None


# ---------- Anti-spam (cupo de IA, ventana deslizante) ----------
def _usos(telefono, desde):
    r = _req("GET", "sofia_wa_antispam",
             params={"select": "ts", "telefono": f"eq.{telefono}", "ts": f"gte.{desde}", "limit": "1000"})
    if r is None:
        return None
    try:
        return len(r.json())
    except Exception:
        return None


def consumir_cupo_ia(telefono, limite, ventana_horas):
    """True si consumio un uso, False si ya alcanzo el limite, None si Supabase fallo."""
    ahora = time.time()
    desde = ahora - ventana_horas * 3600
    usados = _usos(telefono, desde)
    if usados is None:
        return None
    if usados >= limite:
        return False
    r = _req("POST", "sofia_wa_antispam", json_body={"telefono": telefono, "ts": ahora}, prefer="return=minimal")
    if r is None:
        return None
    # Limpieza oportunista de registros vencidos de este telefono
    _req("DELETE", "sofia_wa_antispam", params={"telefono": f"eq.{telefono}", "ts": f"lt.{desde}"})
    return True


def usos_ia(telefono, ventana_horas):
    """Cantidad de usos dentro de la ventana, o None si Supabase fallo."""
    return _usos(telefono, time.time() - ventana_horas * 3600)

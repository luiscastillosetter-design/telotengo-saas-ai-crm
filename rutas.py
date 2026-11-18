"""Rutas de escritura: en Vercel (solo lectura) todo archivo va a /tmp."""
import os

EN_VERCEL = bool(os.environ.get("VERCEL"))
DIR_ESCRITURA = "/tmp" if EN_VERCEL else "."


def ruta_escribible(nombre):
    return os.path.join(DIR_ESCRITURA, nombre)

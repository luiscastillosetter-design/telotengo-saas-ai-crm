import urllib.request
import urllib.error

# =====================================================================
# HERRAMIENTA DE DIAGNÓSTICO DE RED PARA SERVIDORES LOCALES
# Este script verifica que los puertos de tu aplicación estén abiertos
# y listos para recibir el tráfico desde Cloudflare.
# =====================================================================

def probar_puerto_local(nombre_servicio, puerto):
    """
    Intenta conectarse a un puerto local en tu computadora.
    
    Parámetros:
    - nombre_servicio (str): El nombre legible de tu motor (ej. "CRM Visual").
    - puerto (int): El número de puerto donde corre el servicio (ej. 8501).
    """
    url = f"http://127.0.0.1:{puerto}"
    print(f"🔄 Probando conexión con {nombre_servicio} en el puerto {puerto}...")
    
    try:
        # Intentamos abrir la dirección web local con un tiempo límite de 3 segundos
        respuesta = urllib.request.urlopen(url, timeout=3)
        print(f"✅ ¡ÉXITO! {nombre_servicio} está en línea (Código HTTP: {respuesta.getcode()}).")
        return True
    except urllib.error.HTTPError as error_http:
        # Si el servidor responde pero con un bloqueo de seguridad (ej. Error 403 o 404),
        # significa que el puerto SÍ está abierto y funcionando.
        print(f"✅ ¡ÉXITO! {nombre_servicio} respondió correctamente (Código HTTP: {error_http.code}).")
        return True
    except urllib.error.URLError:
        # Si no hay respuesta, el servidor está apagado o el puerto está cerrado.
        print(f"❌ FALLO: No se pudo conectar con {nombre_servicio}. Verifique que la terminal esté corriendo.")
        return False
    except Exception as e:
        print(f"⚠️ Error inesperado evaluando el puerto {puerto}: {e}")
        return False

# =====================================================================
# EJECUCIÓN DE PRUEBAS PARA LOS 2 MOTORES PRINCIPALES
# =====================================================================
if __name__ == "__main__":
    print("================================================================")
    print("📡 INICIANDO DIAGNÓSTICO DE PUERTOS PARA CLOUDFLARE")
    print("================================================================")
    
    # Probamos el Motor 1: Inteligencia Artificial y Webhook (Puerto 5000)
    ia_ok = probar_puerto_local("Backend IA (Flask)", 5000)
    print("-" * 64)
    
    # Probamos el Motor 2: Centro de Mando Visual (Puerto 8501)
    crm_ok = probar_puerto_local("CRM Visual (Streamlit)", 8501)
    
    print("================================================================")
    if ia_ok and crm_ok:
        print("🏆 CONCLUSIÓN: Tus dos puertos locales están 100% operativos.")
        print("👉 Si Cloudflare está bien configurado en internet, tu dominio abrirá perfectamente.")
    else:
        print("⚠️ CONCLUSIÓN: Uno o más servicios están apagados. Enciéndelos con tasks.json.")
    print("================================================================")
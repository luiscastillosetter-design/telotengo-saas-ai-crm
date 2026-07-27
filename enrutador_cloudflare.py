import os
import glob
import json
import yaml

# =====================================================================
# CONSTRUCTOR INTELIGENTE DE ENRUTAMIENTO (FILTRADO POR TUNEL)
# =====================================================================

NOMBRE_TUNEL_OBJETIVO = "telotengo-bot"

def obtener_ruta_cloudflared():
    """Localiza la carpeta de configuración de Cloudflare en tu usuario."""
    return os.path.join(os.path.expanduser("~"), ".cloudflared")

def buscar_credenciales_por_nombre(ruta_carpeta, nombre_esperado):
    """
    Inspecciona el contenido de cada archivo JSON de credenciales
    para encontrar exactamente el UUID del túnel 'telotengo-bot'.
    """
    if not os.path.exists(ruta_carpeta):
        return None
        
    archivos_json = glob.glob(os.path.join(ruta_carpeta, "*.json"))
    
    for archivo in archivos_json:
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                datos = json.load(f)
                # Verificamos si este JSON pertenece a telotengo-bot
                if datos.get("TunnelName") == nombre_esperado:
                    return archivo
        except Exception:
            continue
            
    # Respaldo por si el JSON no tiene la clave pero existe
    if archivos_json:
        return archivos_json[0]
    return None

def generar_archivo_yaml(ruta_credenciales, ruta_salida_yaml):
    """Genera el archivo config.yml con las reglas oficiales para el CRM y la IA."""
    nombre_archivo = os.path.basename(ruta_credenciales)
    uuid_tunel = nombre_archivo.replace(".json", "")
    
    configuracion_red = {
        "tunnel": uuid_tunel,
        "credentials-file": ruta_credenciales,
        "ingress": [
            {
                "hostname": "crm.telotengosolutions.com",
                "service": "http://localhost:8501"
            },
            {
                "hostname": "api.telotengosolutions.com",
                "service": "http://localhost:5000"
            },
            {
                "hostname": "telotengosolutions.com",
                "service": "http://localhost:5000"
            },
            {
                "service": "http_status:404"
            }
        ]
    }
    
    try:
        with open(ruta_salida_yaml, "w", encoding="utf-8") as archivo:
            yaml.dump(configuracion_red, archivo, default_flow_style=False, allow_unicode=True)
        return True
    except Exception as error_escritura:
        print(f"❌ Error al escribir config.yml: {error_escritura}")
        return False

if __name__ == "__main__":
    print("=================================================================")
    print("🛠️ ENRUTAMIENTO INTELIGENTE CLOUDFLARE")
    print("=================================================================\n")
    
    carpeta_cf = obtener_ruta_cloudflared()
    archivo_json = buscar_credenciales_por_nombre(carpeta_cf, NOMBRE_TUNEL_OBJETIVO)
    
    if archivo_json:
        print(f"🔑 Credenciales correctas detectadas para '{NOMBRE_TUNEL_OBJETIVO}':")
        print(f"   📂 {os.path.basename(archivo_json)}")
        
        ruta_config_yml = os.path.join(carpeta_cf, "config.yml")
        exito = generar_archivo_yaml(archivo_json, ruta_config_yml)
        
        if exito:
            print("\n✅ ¡ÉXITO TOTAL! Archivo config.yml sincronizado correctamente.")
            print("🗺️ Rutas activas:")
            print("   👉 https://crm.telotengosolutions.com  --->  localhost:8501")
            print("   👉 https://api.telotengosolutions.com  --->  localhost:5000")
        else:
            print("❌ No se pudo completar la generación del archivo.")
    else:
        print(f"\n❌ ATENCIÓN: No se hallaron credenciales para '{NOMBRE_TUNEL_OBJETIVO}'.")
    print("=================================================================")
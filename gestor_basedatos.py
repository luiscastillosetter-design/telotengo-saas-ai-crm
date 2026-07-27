import sqlite3
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# 1. CARGA DE SEGURIDAD (Regla 13: Apuntamos explícitamente a tu archivo seguridad.env)
load_dotenv("seguridad.env")

DB_NAME = "crm_telotengo.db"

# =====================================================================
# 2. CONEXIÓN INTELIGENTE CON MODO WAL (ALTA CONCURRENCIA)
# =====================================================================
def get_db_connection():
    """
    Crea una conexión segura a SQLite activando el modo WAL.
    El modo WAL (Write-Ahead Logging) permite lecturas y escrituras
    simultáneas sin que la base de datos se bloquee.
    """
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

# =====================================================================
# 3. INICIALIZACIÓN DE TABLAS DEL SISTEMA
# =====================================================================
def asegurar_tablas():
    """
    Verifica y crea todas las tablas necesarias para que el CRM y el Bot
    funcionen correctamente desde el primer segundo.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabla 1: Leads o Prospectos que escriben al WhatsApp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            telefono TEXT PRIMARY KEY,
            nombre TEXT,
            estado_calificacion TEXT,
            fecha_registro TEXT,
            ultima_interaccion TEXT,
            historial_chat TEXT
        )
    ''')

    # Tabla 2: Registro de Webhooks para evitar responder dos veces al mismo mensaje
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhook_logs (
            msg_id TEXT PRIMARY KEY
        )
    ''')

    # Tabla 3: Empresas clientes de tu plataforma SaaS y sus créditos IA
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresas_saas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_empresa TEXT,
            telefono_bot TEXT UNIQUE,
            saldo_creditos INTEGER,
            prompt_maestro TEXT,
            fecha_registro TEXT
        )
    ''')

    # Tabla 4: Registro del programa de referidos de 10 USD
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_tel TEXT,
            datos_raw TEXT,
            fecha TEXT
        )
    ''')

    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN nombre TEXT")
    except sqlite3.OperationalError:
        pass 

    conn.commit()
    conn.close()

# =====================================================================
# 4. FUNCIONES DE CONTROL DE WEBHOOK Y LEADS (PARA EL SERVIDOR FLASK)
# =====================================================================
def mensaje_ya_procesado(msg_id):
    """Verifica si el ID del mensaje de Meta ya fue respondido para evitar duplicados."""
    if not msg_id:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT msg_id FROM webhook_logs WHERE msg_id = ?", (msg_id,))
    res = cursor.fetchone()
    if res:
        conn.close()
        return True
    cursor.execute("INSERT OR IGNORE INTO webhook_logs (msg_id) VALUES (?)", (msg_id,))
    conn.commit()
    conn.close()
    return False

def obtener_o_crear_lead(telefono, nombre_referencia="Prospecto"):
    """Busca un lead en la base de datos. Si no existe, lo crea automáticamente."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telefono, historial_chat FROM leads WHERE telefono = ?", (telefono,))
    lead = cursor.fetchone()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not lead:
        historial_inicial = json.dumps([f"Bot: Inicio de conversación el {now}."], ensure_ascii=False)
        cursor.execute("""
            INSERT INTO leads (telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion, historial_chat)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (telefono, nombre_referencia, "Nuevo Prospecto", now, now, historial_inicial))
        conn.commit()
        historial = []
    else:
        historial = json.loads(lead[1]) if lead[1] else []

    conn.close()
    return historial

def guardar_historial_lead(telefono, nuevo_mensaje_cliente, nuevo_mensaje_bot):
    """Guarda la conversación actualizada entre el cliente y la IA."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    row = cursor.fetchone()

    if row:
        historial = json.loads(row[0]) if row[0] else []
        historial.append(f"Cliente: {nuevo_mensaje_cliente}")
        historial.append(f"Bot: {nuevo_mensaje_bot}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?
        """, (json.dumps(historial, ensure_ascii=False), now, telefono))
        conn.commit()
    conn.close()

def guardar_referido(referrer_tel, datos_raw):
    """Registra los datos de un referido comercial en la base de datos."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO referidos (referrer_tel, datos_raw, fecha)
        VALUES (?, ?, ?)
    """, (referrer_tel, datos_raw, now))
    conn.commit()
    conn.close()

# =====================================================================
# 5. FUNCIONES SAAS Y CRÉDITOS IA
# =====================================================================
def verificar_empresa_saas(telefono_bot_receptor):
    """Busca si el número de WhatsApp que recibió el mensaje pertenece a un cliente SaaS."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, saldo_creditos, prompt_maestro 
        FROM empresas_saas 
        WHERE telefono_bot = ? OR telefono_bot = ?
    """, (telefono_bot_receptor, f"+{telefono_bot_receptor.replace('+', '')}"))
    empresa = cursor.fetchone()
    conn.close()

    if empresa:
        return True, empresa[0], int(empresa[1]), empresa[2]
    return False, None, 0, ""

def descontar_credito_saas(empresa_id):
    """Resta 1 crédito al saldo del cliente SaaS cuando la IA responde un mensaje."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET saldo_creditos = saldo_creditos - 1 WHERE id = ?", (empresa_id,))
    conn.commit()
    conn.close()

def obtener_empresas_saas():
    """Obtiene la lista completa de clientes SaaS para el panel visual."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre_empresa, telefono_bot, saldo_creditos, prompt_maestro, fecha_registro FROM empresas_saas ORDER BY id DESC")
    empresas = cursor.fetchall()
    conn.close()
    return empresas

def registrar_empresa_saas(nombre, telefono, saldo_inicial, prompt):
    """Registra un nuevo cliente comercial en tu plataforma SaaS."""
    if not nombre or not telefono:
        return False, "El nombre y el teléfono son obligatorios."
    telefono = telefono.strip()
    if not telefono.startswith("+"):
        telefono = "+" + telefono
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO empresas_saas (nombre_empresa, telefono_bot, saldo_creditos, prompt_maestro, fecha_registro)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre.strip(), telefono, int(saldo_inicial), prompt.strip(), now))
        conn.commit()
        conn.close()
        return True, "¡Empresa registrada exitosamente en la plataforma SaaS!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"El teléfono {telefono} ya está asociado a otra empresa en el sistema."
    except Exception as e:
        conn.close()
        return False, str(e)

def actualizar_saldo_empresa(empresa_id, nuevo_saldo):
    """Modifica el saldo de créditos IA de una empresa."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET saldo_creditos = ? WHERE id = ?", (int(nuevo_saldo), empresa_id))
    conn.commit()
    conn.close()

def actualizar_prompt_empresa(empresa_id, nuevo_prompt):
    """Modifica la personalidad (prompt) de la IA de una empresa en tiempo real."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET prompt_maestro = ? WHERE id = ?", (nuevo_prompt.strip(), empresa_id))
    conn.commit()
    conn.close()

def eliminar_empresa_saas(empresa_id):
    """Elimina a un cliente del sistema SaaS."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM empresas_saas WHERE id = ?", (empresa_id,))
    conn.commit()
    conn.close()

# =====================================================================
# 6. FUNCIONES DE CRM VISUAL (PARA STREAMLIT)
# =====================================================================
def obtener_leads():
    """Obtiene todos los leads ordenados por la fecha de su último mensaje."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion FROM leads ORDER BY ultima_interaccion DESC")
    leads = cursor.fetchall()
    conn.close()
    return leads

def obtener_historial_completo_lead(telefono):
    """Devuelve los datos y el historial de chat de un lead específico."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat, estado_calificacion, fecha_registro, nombre FROM leads WHERE telefono = ?", (telefono,))
    lead = cursor.fetchone()
    conn.close()
    return lead

def agregar_mensaje_manual_a_db(telefono, nuevo_mensaje):
    """Guarda un mensaje enviado manualmente por el administrador desde el panel CRM."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    row = cursor.fetchone()
    if row:
        historial = json.loads(row[0]) if row[0] else []
        historial.append(nuevo_mensaje)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?", 
                       (json.dumps(historial, ensure_ascii=False), now, telefono))
        conn.commit()
    conn.close()

def registrar_lead_manual(telefono, nombre="", estado="Nuevo Prospecto"):
    """Permite crear o actualizar un lead desde el formulario manual o CSV de Streamlit."""
    if not telefono:
        return False, "El teléfono no puede estar vacío."
    
    telefono = telefono.strip()
    if not telefono.startswith("+"):
        telefono = "+" + telefono
        
    nombre = nombre.strip() if nombre else "Sin Nombre"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT telefono FROM leads WHERE telefono = ?", (telefono,))
    if cursor.fetchone():
        cursor.execute("UPDATE leads SET nombre = ? WHERE telefono = ?", (nombre, telefono))
        conn.commit()
        conn.close()
        return True, f"El número {telefono} ya existía, se actualizó su nombre."
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    historial_inicial = json.dumps([f"Agente: Lead agregado al CRM el {now}."], ensure_ascii=False)
    
    cursor.execute("""
        INSERT INTO leads (telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion, historial_chat)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (telefono, nombre, estado, now, now, historial_inicial))
    
    conn.commit()
    conn.close()
    return True, "Lead registrado con éxito."

def editar_lead_en_db(telefono_antiguo, nuevo_telefono, nuevo_nombre, nuevo_estado):
    """Modifica los datos generales de un contacto existente en la base de datos."""
    if not nuevo_telefono:
        return False, "El teléfono no puede estar vacío."
    nuevo_telefono = nuevo_telefono.strip()
    if not nuevo_telefono.startswith("+"):
        nuevo_telefono = "+" + nuevo_telefono
    nuevo_nombre = nuevo_nombre.strip() if nuevo_nombre else "Sin Nombre"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if nuevo_telefono != telefono_antiguo:
            cursor.execute("SELECT telefono FROM leads WHERE telefono = ?", (nuevo_telefono,))
            if cursor.fetchone():
                conn.close()
                return False, f"El número {nuevo_telefono} ya pertenece a otro lead."
        cursor.execute("""
            UPDATE leads SET telefono = ?, nombre = ?, estado_calificacion = ? WHERE telefono = ?
        """, (nuevo_telefono, nuevo_nombre, nuevo_estado, telefono_antiguo))
        conn.commit()
        conn.close()
        return True, "¡Contacto actualizado con éxito!"
    except Exception as e:
        conn.close()
        return False, f"Error al actualizar: {e}"

# Ejecutamos la verificación de tablas al importar el módulo por primera vez
asegurar_tablas()
import sqlite3
import json
from datetime import datetime
import os

from rutas import ruta_escribible

DB_PATH = ruta_escribible("crm_telotengo.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False) 
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

# ==========================================
# 1. INICIALIZACIÓN Y AUTO-MIGRACIONES
# ==========================================
def inicializar_bd():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabla de Leads (Con la nueva estructura)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            telefono TEXT PRIMARY KEY,
            estado_calificacion TEXT,
            historial_chat TEXT,
            fecha_registro TIMESTAMP,
            ultima_interaccion TIMESTAMP,
            nombre TEXT
        )
    ''')
    
    # AUTO-MIGRACIÓN SILENCIOSA: Inyectar columna bot_phone_id si no existe
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN bot_phone_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass # La columna ya existe, continuamos.
    
    # Tabla de Anti-Duplicados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhook_logs (
            msg_id TEXT PRIMARY KEY
        )
    ''')
    
    # Tabla de Empresas SaaS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS empresas_saas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_empresa TEXT,
            telefono_bot TEXT UNIQUE,
            saldo_creditos INTEGER,
            prompt_maestro TEXT,
            fecha_registro TEXT,
            meta_phone_id TEXT,
            meta_token TEXT,
            email TEXT,
            password TEXT
        )
    ''')
    
    # Tabla de Referidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_tel TEXT,
            datos_raw TEXT,
            fecha TEXT
        )
    ''')
    
    # Cupo de mensajes con IA por usuario (anti-spam)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uso_ia (
            telefono TEXT,
            ts REAL
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uso_ia_tel ON uso_ia (telefono, ts)")

    conn.commit()
    conn.close()

inicializar_bd()

def consumir_cupo_ia(telefono, limite=6, ventana_horas=24):
    """Registra un uso de IA. Devuelve False (sin registrar) si ya alcanzó el límite en la ventana."""
    import time
    ahora = time.time()
    desde = ahora - ventana_horas * 3600
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM uso_ia WHERE ts < ?", (desde,))
        usados = conn.execute("SELECT COUNT(*) FROM uso_ia WHERE telefono = ? AND ts >= ?", (telefono, desde)).fetchone()[0]
        if usados >= limite:
            conn.commit()
            return False
        conn.execute("INSERT INTO uso_ia (telefono, ts) VALUES (?, ?)", (telefono, ahora))
        conn.commit()
        return True
    finally:
        conn.close()

# ==========================================
# 2. FUNCIONES DE GESTIÓN DE LEADS (AISLADAS)
# ==========================================
def registrar_lead_manual(telefono, nombre, estado, bot_phone_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute('''
            INSERT INTO leads (telefono, nombre, estado_calificacion, historial_chat, fecha_registro, ultima_interaccion, bot_phone_id)
            VALUES (?, ?, ?, '[]', ?, ?, ?)
        ''', (telefono, nombre, estado, fecha_actual, fecha_actual, bot_phone_id))
        conn.commit()
        exito, msg = True, f"Lead {nombre} registrado exitosamente."
    except sqlite3.IntegrityError:
        cursor.execute('''
            UPDATE leads SET nombre = ?, estado_calificacion = ?, ultima_interaccion = ?, bot_phone_id = ? WHERE telefono = ?
        ''', (nombre, estado, fecha_actual, bot_phone_id, telefono))
        conn.commit()
        exito, msg = True, f"Lead {nombre} ya existía. Datos actualizados."
    except Exception as e:
        exito, msg = False, f"Error DB: {e}"
    finally:
        conn.close()
    return exito, msg

def obtener_leads(bot_phone_id=None):
    """Obtiene los leads. Si recibe bot_phone_id, filtra solo los de ese Tenant."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if bot_phone_id:
        cursor.execute("SELECT telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion FROM leads WHERE bot_phone_id = ? ORDER BY ultima_interaccion DESC", (bot_phone_id,))
    else:
        # El Super Administrador los ve todos
        cursor.execute("SELECT telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion FROM leads ORDER BY ultima_interaccion DESC")
    leads = cursor.fetchall()
    conn.close()
    return leads

def obtener_historial_completo_lead(telefono):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat, estado_calificacion, fecha_registro, nombre, ultima_interaccion FROM leads WHERE telefono = ?", (telefono,))
    datos = cursor.fetchone()
    conn.close()
    return datos

def editar_lead_en_db(tel_viejo, tel_nuevo, nombre_nuevo, estado_nuevo):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE leads 
            SET telefono = ?, nombre = ?, estado_calificacion = ? 
            WHERE telefono = ?
        ''', (tel_nuevo, nombre_nuevo, estado_nuevo, tel_viejo))
        conn.commit()
        exito, msg = True, "Base de datos actualizada correctamente."
    except Exception as e:
        exito, msg = False, f"Error actualizando lead: {e}"
    finally:
        conn.close()
    return exito, msg

def obtener_o_crear_lead(telefono, bot_phone_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    resultado = cursor.fetchone()
    
    if resultado:
        # Si ya existe, actualizamos su bot_phone_id en caso de que sea un mensaje entrante
        if bot_phone_id:
            cursor.execute("UPDATE leads SET bot_phone_id = ? WHERE telefono = ?", (bot_phone_id, telefono))
            conn.commit()
        historial = json.loads(resultado[0])
        conn.close()
        return historial
    else:
        historial_vacio = []
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO leads (telefono, estado_calificacion, historial_chat, fecha_registro, ultima_interaccion, nombre, bot_phone_id)
            VALUES (?, 'Nuevo Prospecto', ?, ?, ?, 'Sin Nombre', ?)
        ''', (telefono, json.dumps(historial_vacio), fecha_actual, fecha_actual, bot_phone_id))
        conn.commit()
        conn.close()
        return historial_vacio

def guardar_historial_lead(telefono, mensaje_usuario, respuesta_bot):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    resultado = cursor.fetchone()
    
    historial = json.loads(resultado[0]) if resultado else []
    if mensaje_usuario:
        historial.append(f"Cliente: {mensaje_usuario}")
    if respuesta_bot:
        historial.append(f"Bot: {respuesta_bot}")
    
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?
    ''', (json.dumps(historial), fecha_actual, telefono))
    conn.commit()
    conn.close()

def agregar_mensaje_manual_a_db(telefono, mensaje):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    resultado = cursor.fetchone()
    
    if resultado:
        historial = json.loads(resultado[0])
        historial.append(mensaje)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?
        ''', (json.dumps(historial), fecha_actual, telefono))
        conn.commit()
    conn.close()

# ==========================================
# 3. FUNCIONES DEL MOTOR SAAS 
# ==========================================
def registrar_empresa_saas(nom_empresa, tel_bot_empresa, saldo_inicial, prompt_empresa, meta_phone_id, meta_token, email_cliente, pass_cliente):
    conn = get_db_connection()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute('''
            INSERT INTO empresas_saas 
            (nombre_empresa, telefono_bot, saldo_creditos, prompt_maestro, fecha_registro, meta_phone_id, meta_token, email, password)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nom_empresa, tel_bot_empresa, saldo_inicial, prompt_empresa, fecha_actual, meta_phone_id, meta_token, email_cliente, pass_cliente))
        conn.commit()
        exito, msg = True, f"✅ Tenant SaaS de '{nom_empresa}' desplegado con éxito en la plataforma."
    except sqlite3.IntegrityError:
        exito, msg = False, "❌ El teléfono del bot ya pertenece a otro Tenant en el ecosistema."
    except Exception as e:
        exito, msg = False, f"❌ Error Crítico DB: {e}"
    finally:
        conn.close()
    return exito, msg

def obtener_empresas_saas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre_empresa, telefono_bot, saldo_creditos, prompt_maestro, fecha_registro, meta_phone_id, email FROM empresas_saas")
    empresas = cursor.fetchall()
    conn.close()
    return empresas

def actualizar_saldo_empresa(emp_id, nuevo_saldo):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET saldo_creditos = ? WHERE id = ?", (nuevo_saldo, emp_id))
    conn.commit()
    conn.close()

def eliminar_empresa_saas(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM empresas_saas WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()

def actualizar_prompt_empresa(emp_id, nuevo_prompt):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET prompt_maestro = ? WHERE id = ?", (nuevo_prompt, emp_id))
    conn.commit()
    conn.close()

def verificar_empresa_saas(telefono):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, saldo_creditos, prompt_maestro FROM empresas_saas WHERE telefono_bot = ?", (telefono,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado:
        return True, resultado[0], resultado[1], resultado[2]
    return False, None, 0, ""

# ==========================================
# 4. SEGURIDAD Y LOGS
# ==========================================
def mensaje_ya_procesado(msg_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT msg_id FROM webhook_logs WHERE msg_id = ?", (msg_id,))
    resultado = cursor.fetchone()
    
    if resultado:
        conn.close()
        return True
    else:
        cursor.execute("INSERT INTO webhook_logs (msg_id) VALUES (?)", (msg_id,))
        conn.commit()
        conn.close()
        return False

def mensaje_yaml_procesado(msg_id):
    return mensaje_ya_procesado(msg_id)

def guardar_referido(telefono_referrer, alerta_sucia):
    conn = get_db_connection()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO referidos (referrer_tel, datos_raw, fecha)
        VALUES (?, ?, ?)
    ''', (telefono_referrer, alerta_sucia, fecha_actual))
    conn.commit()
    conn.close()

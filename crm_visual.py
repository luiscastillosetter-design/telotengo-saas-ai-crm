import streamlit as st
import sqlite3
import json
import os
import requests
import csv
import io
from datetime import datetime, timedelta

# Configuración inicial de la página
st.set_page_config(
    page_title="CRM Telotengo Solutions — SaaS Platform",
    page_icon="🚀",
    layout="wide"
)

# --- CARGADOR Y GUARDADO DE CONFIGURACIÓN ---
def cargar_config():
    if os.path.exists('config.json'):
        with open('config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            if 'negocio' not in cfg:
                cfg['negocio'] = {}
            return cfg
    return {'negocio': {}}

def guardar_config(config_data):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

config = cargar_config()

# --- SISTEMA DE AUTENTICACIÓN (LOGIN) ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

password_sistema = config.get("crm_password", "telotengo2026")

if not st.session_state.autenticado:
    st.title("🔒 Acceso Restringido — Telotengo SaaS Command Center")
    st.markdown("Por favor, introduce tu contraseña de seguridad para acceder al panel de administración.")
    
    with st.form("form_login"):
        password_ingresada = st.text_input("Contraseña de Acceso", type="password")
        btn_login = st.form_submit_button("🔓 Ingresar al Plataforma")
        
        if btn_login:
            if password_ingresada == password_sistema:
                st.session_state.autenticado = True
                st.success("¡Acceso concedido!")
                st.rerun()
            else:
                st.error("Contraseña incorrecta. Inténtalo de nuevo.")
    st.stop()

# --- CONEXIÓN A BASES DE DATOS (LEADS Y EMPRESAS SAAS) ---
def asegurar_tablas():
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    
    # Tabla de Leads (Prospectos)
    cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
                        telefono TEXT PRIMARY KEY,
                        nombre TEXT,
                        estado_calificacion TEXT,
                        fecha_registro TEXT,
                        ultima_interaccion TEXT,
                        historial_chat TEXT
                    )''')
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN nombre TEXT")
    except sqlite3.OperationalError:
        pass

    # Tabla de Empresas SaaS (Tus Clientes Comerciales)
    cursor.execute('''CREATE TABLE IF NOT EXISTS empresas_saas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre_empresa TEXT,
                        telefono_bot TEXT UNIQUE,
                        saldo_creditos INTEGER,
                        prompt_maestro TEXT,
                        fecha_registro TEXT
                    )''')
    
    conn.commit()
    conn.close()

asegurar_tablas()

# --- FUNCIONES CRUD PARA LEADS ---
def obtener_leads():
    if not os.path.exists('crm_telotengo.db'):
        return []
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT telefono, nombre, estado_calificacion, fecha_registro, ultima_interaccion FROM leads ORDER BY ultima_interaccion DESC")
    leads = cursor.fetchall()
    conn.close()
    return leads

def obtener_historial_lead(telefono):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat, estado_calificacion, fecha_registro, nombre FROM leads WHERE telefono = ?", (telefono,))
    lead = cursor.fetchone()
    conn.close()
    return lead

def agregar_mensaje_a_db(telefono, nuevo_mensaje):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT historial_chat FROM leads WHERE telefono = ?", (telefono,))
    row = cursor.fetchone()
    if row:
        historial = json.loads(row[0])
        historial.append(nuevo_mensaje)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE leads SET historial_chat = ?, ultima_interaccion = ? WHERE telefono = ?", 
                       (json.dumps(historial, ensure_ascii=False), now, telefono))
        conn.commit()
    conn.close()

def registrar_lead_manual(telefono, nombre="", estado="Nuevo Prospecto"):
    if not telefono:
        return False, "El teléfono no puede estar vacío."
    
    telefono = telefono.strip()
    if not telefono.startswith("+"):
        telefono = "+" + telefono
        
    nombre = nombre.strip() if nombre else "Sin Nombre"
        
    conn = sqlite3.connect('crm_telotengo.db')
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
    if not nuevo_telefono:
        return False, "El teléfono no puede estar vacío."
    nuevo_telefono = nuevo_telefono.strip()
    if not nuevo_telefono.startswith("+"):
        nuevo_telefono = "+" + nuevo_telefono
    nuevo_nombre = nuevo_nombre.strip() if nuevo_nombre else "Sin Nombre"
    
    conn = sqlite3.connect('crm_telotengo.db')
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

# --- FUNCIONES CRUD PARA EMPRESAS SAAS ---
def obtener_empresas_saas():
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre_empresa, telefono_bot, saldo_creditos, prompt_maestro, fecha_registro FROM empresas_saas ORDER BY id DESC")
    empresas = cursor.fetchall()
    conn.close()
    return empresas

def registrar_empresa_saas(nombre, telefono, saldo_inicial, prompt):
    if not nombre or not telefono:
        return False, "El nombre y el teléfono son obligatorios."
    telefono = telefono.strip()
    if not telefono.startswith("+"):
        telefono = "+" + telefono
        
    conn = sqlite3.connect('crm_telotengo.db')
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
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET saldo_creditos = ? WHERE id = ?", (int(nuevo_saldo), empresa_id))
    conn.commit()
    conn.close()

def actualizar_prompt_empresa(empresa_id, nuevo_prompt):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE empresas_saas SET prompt_maestro = ? WHERE id = ?", (nuevo_prompt.strip(), empresa_id))
    conn.commit()
    conn.close()

def eliminar_empresa_saas(empresa_id):
    conn = sqlite3.connect('crm_telotengo.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM empresas_saas WHERE id = ?", (empresa_id,))
    conn.commit()
    conn.close()

# --- FUNCIÓN DE ENVÍO DIRECTO A WHATSAPP (API DE META) ---
def enviar_mensaje_whatsapp(telefono, mensaje):
    meta_cfg = config.get("meta", {})
    token = meta_cfg.get("token", "")
    phone_number_id = meta_cfg.get("phone_number_id", "")
    
    if not token or not phone_number_id:
        return False, "Faltan las credenciales de Meta en el archivo config.json."
    
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": mensaje}
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return True, "Enviado con éxito"
        else:
            return False, response.text
    except Exception as e:
        return False, str(e)

# --- INTERFAZ VISUAL DEL CRM ---
col_titulo, col_salir = st.columns([8, 1])
with col_titulo:
    st.title("🚀 Telotengo Solutions — SaaS AI Command Center")
with col_salir:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔒 Salir"):
        st.session_state.autenticado = False
        st.rerun()

st.markdown("---")

# 4 Pestañas Principales
pestana_chat, pestana_saas, pestana_config, pestana_seguimiento = st.tabs([
    "📊 Auditoría, Leads y Chat en Vivo", 
    "🏢 Gestión de Clientes (SaaS & Tokens)",
    "⚙️ Configuración y Personalidad del Bot",
    "🤖 Automatización y Seguimiento (24h)"
])

# ==========================================
# PESTAÑA 1: GESTIÓN DE LEADS (MANUAL, CSV, EDICIÓN) + CHAT
# ==========================================
with pestana_chat:
    st.header("💬 Bandeja, Prospección y Control de Leads")
    
    with st.expander("➕ Registro y Carga Masiva de Leads (Manual o CSV)"):
        col_op1, col_op2 = st.columns(2)
        with col_op1:
            st.subheader("Registro Individual")
            with st.form("form_nuevo_lead"):
                nombre_nuevo = st.text_input("Nombre del Prospecto (ej: Raphie / Carlos Pérez)")
                tel_nuevo = st.text_input("Teléfono con código de país (ej: +15551234567)")
                estado_inicial_lead = st.selectbox("Clasificación Inicial", ["Nuevo Prospecto", "Frío", "Interesado", "Caliente"])
                btn_guardar_lead = st.form_submit_button("💾 Guardar Lead")
                if btn_guardar_lead:
                    exito_reg, mensaje_reg = registrar_lead_manual(tel_nuevo, nombre_nuevo, estado_inicial_lead)
                    if exito_reg:
                        st.success(mensaje_reg)
                        st.rerun()
                    else:
                        st.error(mensaje_reg)
                        
        with col_op2:
            st.subheader("Carga Masiva vía CSV")
            st.markdown("El archivo CSV debe tener las columnas **nombre** y **telefono** (y opcionalmente **estado**).")
            archivo_csv = st.file_uploader("Sube tu archivo .csv", type=["csv"])
            if archivo_csv is not None:
                if st.button("🚀 Procesar e Importar CSV"):
                    try:
                        decoded_file = archivo_csv.read().decode('utf-8')
                        io_string = io.StringIO(decoded_file)
                        reader = csv.DictReader(io_string)
                        importados = 0
                        for row in reader:
                            nom = row.get("nombre") or row.get("Nombre") or row.get("NAME") or "Sin Nombre"
                            tel = row.get("telefono") or row.get("Teléfono") or row.get("PHONE")
                            est = row.get("estado") or row.get("Estado") or "Nuevo Prospecto"
                            if tel:
                                exito, _ = registrar_lead_manual(tel.strip(), nom.strip(), est.strip())
                                if exito:
                                    importados += 1
                        st.success(f"¡Importación masiva completada! Se agregaron/actualizaron {importados} leads.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error procesando el archivo CSV: {e}")
                    
    st.markdown("---")
    leads = obtener_leads()
    
    if not leads:
        st.info("💡 Todavía no hay prospectos registrados. Utiliza el panel superior para agregar leads de forma manual o subiendo tu CSV.")
    else:
        lead_dict = {f"{lead[1] if lead[1] else 'Sin Nombre'} — {lead[0]}": lead[0] for lead in leads}
        seleccion_formato = st.selectbox("Selecciona un prospecto de la base de datos:", list(lead_dict.keys()))
        lead_seleccionado = lead_dict[seleccion_formato]
        
        if lead_seleccionado:
            datos_lead = obtener_historial_lead(lead_seleccionado)
            if datos_lead:
                historial_chat = json.loads(datos_lead[0])
                estado = datos_lead[1]
                fecha = datos_lead[2]
                nombre_lead = datos_lead[3] if len(datos_lead) > 3 and datos_lead[3] else "Sin Nombre"
                
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    st.metric(label="Nombre del Lead", value=nombre_lead)
                with col_m2:
                    st.metric(label="Estado", value=estado)
                with col_m3:
                    st.metric(label="Registro", value=fecha)
                
                st.markdown("---")
                
                with st.expander(f"✏️ Editar información de {nombre_lead}"):
                    with st.form("form_editar_lead"):
                        edit_nombre = st.text_input("Nombre Actualizado", value=nombre_lead)
                        edit_telefono = st.text_input("Número de Teléfono Actualizado", value=lead_seleccionado)
                        estados_posibles = ["Nuevo Prospecto", "Frío", "Interesado", "Caliente"]
                        current_idx = estados_posibles.index(estado) if estado in estados_posibles else 0
                        edit_estado = st.selectbox("Estado de Calificación", estados_posibles, index=current_idx)
                        btn_actualizar_lead = st.form_submit_button("💾 Guardar Cambios del Contacto")
                        if btn_actualizar_lead:
                            exito_edit, msg_edit = editar_lead_en_db(lead_seleccionado, edit_telefono, edit_nombre, edit_estado)
                            if exito_edit:
                                st.success(msg_edit)
                                st.rerun()
                            else:
                                st.error(msg_edit)
                
                telefono_limpio = lead_seleccionado.replace("+", "").strip()
                st.markdown("##### 🚀 Acciones de Apertura Manual:")
                st.link_button(
                    f"💬 Abrir chat en WhatsApp con {nombre_lead}", 
                    f"https://wa.me/{telefono_limpio}?text=Hola%20{nombre_lead},%20te%20escribo%20desde%20el%20equipo%20de%20Telotengo%20Solutions...", 
                    use_container_width=True
                )
                
                st.markdown("### 📱 Conversación y Chat por API:")
                chat_container = st.container(height=350)
                with chat_container:
                    for mensaje in historial_chat:
                        if mensaje.startswith("Cliente:"):
                            with st.chat_message("user", avatar="👤"):
                                st.write(mensaje.replace("Cliente:", "").strip())
                        else:
                            avatar_tipo = "👨‍💻" if "Agente:" in mensaje else "🤖"
                            with st.chat_message("assistant", avatar=avatar_tipo):
                                st.write(mensaje.replace("Bot:", "").replace("Agente:", "").strip())
                
                texto_manual = st.chat_input(f"Escribe un mensaje para {nombre_lead} (soporta emojis 🚀✨)...")
                if texto_manual:
                    mensaje_formateado = f"Agente: {texto_manual}"
                    exito, detalle = enviar_mensaje_whatsapp(lead_seleccionado, texto_manual)
                    if exito:
                        agregar_mensaje_a_db(lead_seleccionado, mensaje_formateado)
                        st.success("¡Mensaje enviado a WhatsApp correctamente! ✅")
                        st.rerun()
                    else:
                        st.error(f"No se pudo enviar el mensaje por API: {detalle}")

# ==========================================
# PESTAÑA 2: GESTIÓN DE CLIENTES SAAS & TOKENS
# ==========================================
with pestana_saas:
    st.header("🏢 Gestión de Empresas Clientes y Saldo de Inteligencia Artificial")
    st.markdown("""
    Controla aquí a los clientes que pagan por tu tecnología. Cada mensaje que su bot responda descontará **1 crédito** de su saldo.
    **Plan Recomendado:** Fee de instalación + **$100 USD mensuales** por paquete de **1,000 Créditos IA**.
    """)
    
    prompt_360_default = (
        "Eres el Consultor e Ingeniero IA de Telotengo Solutions. Tu objetivo es asesorar a dueños de negocios "
        "y ofrecerles nuestro ecosistema de soluciones tecnológicas 360° para escalar sus ventas:\n"
        "1) Asistentes e Agentes de IA 24/7 para WhatsApp (como tú).\n"
        "2) CRMs personalizados y automatizados para control total de prospectos.\n"
        "3) Diseño y Desarrollo Web de alta conversión enfocados en ventas.\n"
        "4) Automatización y gestión de Redes Sociales.\n"
        "5) Avatares personalizados creados con Inteligencia Artificial para marketing y video.\n\n"
        "Sé profesional, innovador, persuasivo y busca siempre agendar una llamada de consultoría gratuita con el ingeniero Luis Castillo."
    )
    
    with st.expander("➕ Dar de Alta Nueva Empresa Cliente (SaaS)", expanded=False):
        with st.form("form_nueva_empresa"):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                nom_empresa = st.text_input("Nombre de la Empresa / Cliente", placeholder="Ej: Raphie Closets & TV Hosts")
                tel_bot_empresa = st.text_input("Teléfono de WhatsApp del Bot", placeholder="Ej: +15559876543")
            with col_e2:
                saldo_inicial = st.number_input("Créditos IA Iniciales (1 Mensaje = 1 Crédito)", min_value=0, value=1000, step=100)
                st.info("💡 **1,000 Créditos** equivalen a un plan estándar de **$100 USD/mes**.")
            
            prompt_empresa = st.text_area("📝 Prompt Maestro de Personalidad para esta Empresa:", value=prompt_360_default, height=150)
            
            btn_crear_empresa = st.form_submit_button("🚀 Registrar Empresa en la Plataforma")
            if btn_crear_empresa:
                exito_saas, msg_saas = registrar_empresa_saas(nom_empresa, tel_bot_empresa, saldo_inicial, prompt_empresa)
                if exito_saas:
                    st.success(msg_saas)
                    st.rerun()
                else:
                    st.error(msg_saas)
                    
    st.markdown("---")
    st.subheader("📋 Empresas Activas en tu Plataforma SaaS")
    
    empresas = obtener_empresas_saas()
    
    if not empresas:
        st.info("💡 Aún no tienes empresas clientes registradas. ¡Agrega la primera en el panel superior!")
    else:
        for emp in empresas:
            emp_id, emp_nom, emp_tel, emp_saldo, emp_prompt, emp_fecha = emp
            
            with st.container():
                col_c1, col_c2, col_c3, col_c4 = st.columns([3, 2, 2, 2])
                with col_c1:
                    st.markdown(f"#### 🏢 **{emp_nom}**")
                    st.caption(f"📱 Teléfono Bot: `{emp_tel}` | 📅 Alta: {emp_fecha}")
                with col_c2:
                    if emp_saldo <= 0:
                        st.error("🚨 **PAUSADO — SIN SALDO**")
                    elif emp_saldo < 200:
                        st.warning(f"⚠️ **Saldo Bajo:** {emp_saldo} créditos")
                    else:
                        st.success(f"🟢 **Activo:** {emp_saldo} créditos")
                with col_c3:
                    if st.button(f"➕ Recargar 1,000 Créditos ($100)", key=f"rec_{emp_id}"):
                        actualizar_saldo_empresa(emp_id, emp_saldo + 1000)
                        st.success("¡Recarga aplicada!")
                        st.rerun()
                with col_c4:
                    if st.button("🗑️ Eliminar Cliente", key=f"del_{emp_id}"):
                        eliminar_empresa_saas(emp_id)
                        st.warning("Cliente eliminado.")
                        st.rerun()
                
                with st.expander(f"⚙️ Editar Ajustes y Prompt de {emp_nom}", key=f"exp_{emp_id}"):
                    col_adj1, col_adj2 = st.columns([1, 3])
                    with col_adj1:
                        nuevo_saldo_manual = st.number_input("Ajustar Saldo Exacto", value=emp_saldo, key=f"num_{emp_id}")
                        if st.button("💾 Guardar Saldo", key=f"save_saldo_{emp_id}"):
                            actualizar_saldo_empresa(emp_id, nuevo_saldo_manual)
                            st.success("Saldo actualizado.")
                            st.rerun()
                    with col_adj2:
                        prompt_editado = st.text_area("Prompt Maestro Inteligente (Modificable en vivo):", value=emp_prompt, height=120, key=f"prompt_{emp_id}")
                        if st.button("📝 Actualizar Personalidad del Bot", key=f"save_prompt_{emp_id}"):
                            actualizar_prompt_empresa(emp_id, prompt_editado)
                            st.success("¡Personalidad del bot actualizada sin reiniciar código!")
                            st.rerun()
                st.markdown("---")

# ==========================================
# PESTAÑA 3: CONFIGURACIÓN Y PERSONALIDAD DEL BOT PRINCIPAL (¡LO QUE ESTABAS BUSCANDO!)
# ==========================================
with pestana_config:
    st.header("⚙️ Configuración y Personalidad de la Agencia")
    if config:
        with st.form("form_config"):
            st.subheader("🧠 Prompt Maestro del Asistente Principal (Telotengo Solutions)")
            st.markdown("Este cuadro controla la personalidad, tono y servicios que ofrece tu bot en WhatsApp. Edítalo y se aplicará al instante sin tocar código:")
            
            prompt_defecto = (
                "Eres el Consultor e Ingeniero IA de Telotengo Solutions. Tu objetivo es asesorar a dueños de negocios "
                "y ofrecerles nuestro ecosistema de soluciones tecnológicas 360° para escalar sus ventas:\n"
                "1) Asistentes e Agentes de IA 24/7 para WhatsApp (como tú).\n"
                "2) CRMs personalizados y automatizados para control total de prospectos.\n"
                "3) Diseño y Desarrollo Web de alta conversión enfocados en ventas.\n"
                "4) Automatización y gestión de Redes Sociales.\n"
                "5) Avatares personalizados creados con Inteligencia Artificial para marketing y video.\n\n"
                "Sé profesional, innovador, persuasivo y busca siempre agendar una llamada de consultoría gratuita con el ingeniero Luis Castillo."
            )
            
            prompt_maestro_global = st.text_area(
                "📝 Instrucciones y Personalidad del Bot:", 
                value=config['negocio'].get('prompt_maestro', prompt_defecto),
                height=220
            )
            
            st.markdown("---")
            st.subheader("🏢 Datos Generales de tu Negocio")
            nombre_negocio = st.text_input("Nombre de la Agencia", value=config['negocio'].get('nombre', 'Telotengo Solutions'))
            promesa_negocio = st.text_area("Promesa Principal", value=config['negocio'].get('promesa_principal', 'Soluciones Tecnológicas 360° para Escalar Negocios'))
            tono_voz = st.text_input("Tono de Voz", value=config['negocio'].get('tono_voz', 'Profesional, Tecnológico y Persuasivo'))
            enlace_citas = st.text_input("Enlace de Agendamiento", value=config['negocio'].get('enlace_citas', ''))
            
            st.markdown("---")
            st.subheader("🔒 Seguridad de la Plataforma SaaS")
            nueva_pwd = st.text_input("Cambiar Contraseña del CRM", type="password", value=config.get('crm_password', 'telotengo2026'))
            
            btn_guardar = st.form_submit_button("💾 Guardar Personalidad y Configuración")
            if btn_guardar:
                config['negocio']['prompt_maestro'] = prompt_maestro_global
                config['negocio']['nombre'] = nombre_negocio
                config['negocio']['promesa_principal'] = promesa_negocio
                config['negocio']['tono_voz'] = tono_voz
                config['negocio']['enlace_citas'] = enlace_citas
                config['crm_password'] = nueva_pwd
                guardar_config(config)
                st.success("¡Prompt Maestro y personalidad actualizados con éxito! Tu bot ya piensa como un consultor 360°. 🚀")

# ==========================================
# PESTAÑA 4: AUTOMATIZACIÓN Y SEGUIMIENTO 24H
# ==========================================
with pestana_seguimiento:
    st.header("🤖 Configuración de Seguimiento Automático (Reactivación de Leads)")
    st.markdown("""
    Aquí puedes definir las reglas para reactivar prospectos fríos o que dejaron la conversación en visto.
    """)
    st.info("💡 **Regla de las 24 horas:** El sistema analiza la última interacción del lead. Si han pasado más de 24 horas y no ha completado el agendamiento, el sistema puede disparar automáticamente un mensaje de reactivación.")
    
    mensaje_seguimiento = st.text_area(
        "Plantilla de Mensaje de Seguimiento automático:", 
        value="¡Hola! 👋 Estuve analizando la tecnología actual de tu negocio y quería saber si tienes 5 minutos hoy para que agendemos una llamada rápida y mostrarte cómo podemos automatizar tus ventas. ¿Qué opinas?"
    )
    
    if st.button("🚀 Ejecutar barrido de seguimiento manual ahora"):
        leads_todos = obtener_leads()
        contador_enviados = 0
        ahora = datetime.now()
        for lead in leads_todos:
            tel = lead[0]
            ult_interaccion_str = lead[4] if len(lead) > 4 else lead[3]
            try:
                ult_fecha = datetime.strptime(ult_interaccion_str, "%Y-%m-%d %H:%M:%S")
                if ahora - ult_fecha > timedelta(hours=24):
                    exito, _ = enviar_mensaje_whatsapp(tel, mensaje_seguimiento)
                    if exito:
                        agregar_mensaje_a_db(tel, f"Bot (Seguimiento 24h): {mensaje_seguimiento}")
                        contador_enviados += 1
            except Exception:
                pass
        st.success(f"¡Barrido completado! Se enviaron {contador_enviados} mensajes de seguimiento automático a leads inactivos.")
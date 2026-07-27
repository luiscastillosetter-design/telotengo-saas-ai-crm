const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const sqlite3 = require('sqlite3').verbose();
const fs = require('fs');

// =====================================================================
// DATOS GENERALES DEL NEGOCIO (IMPULSO A LA COMPRA)
// =====================================================================
const DATOS_NEGOCIO = {
    nombre: "Telotengo Solutions",
    promesa: "Automatización con IA 24/7 para WhatsApp que atiende, califica y remata ventas por ti, más desarrollo de cualquier ecosistema o proyecto digital a medida. ¡Una inversión que se paga sola desde el primer mes! 🚀",
    agendamentoWhatsapp: "https://wa.me/584245885477",
    calendarioReuniones: "https://api.leadconnectorhq.com/widget/booking/cHgLoMCk71bch2PmxVee"
};

// =====================================================================
// INICIALIZACIÓN DEL CLIENTE DE WHATSAPP (SOFÍA)
// =====================================================================
const client = new Client({
    authStrategy: new LocalAuth({ clientId: "telotengo-bot" })
});

client.on('qr', (qr) => {
    console.log('Escanea el código QR para iniciar sesión en WhatsApp:');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('✅ Sofía (Asistente Ejecutiva) está lista, conectada y operando sin errores.');
});

// =====================================================================
// MÓDULO DE COMANDOS GERENCIALES Y RECONOCIMIENTO ("EL JEFE")
// =====================================================================
const NUMERO_JEFE = '584245885477@c.us';

/**
 * Intercepta y procesa cualquier mensaje proveniente del Administrador.
 * Retorna true si el mensaje es del Jefe para detener el flujo de ventas.
 */
async function procesarComandosJefe(msg) {
    if (msg.from !== NUMERO_JEFE) {
        return false; // No es el jefe, permite que continúe el flujo para clientes
    }

    const textoMensaje = msg.body.trim();

    // 1. Comando gerencial: REPORTE
    if (textoMensaje === 'REPORTE') {
        const db = new sqlite3.Database('crm_telotengo.db');
        
        db.all("SELECT * FROM leads", [], async (err, rows) => {
            db.close();
            if (err) {
                await msg.reply('❌ Error al consultar la base de datos para generar el reporte gerencial.');
                return;
            }

            let reporte = `📊 *REPORTE EJECUTIVO DEL DÍA (SOFÍA)*\n\n`;
            reporte += `👥 Total de registros en base de datos: ${rows.length}\n\n`;
            
            rows.slice(-5).forEach((lead, index) => {
                reporte += `${index + 1}. *${lead.nombre || 'Sin nombre'} ${lead.apellido || ''}*\n   Origen: ${lead.tipo_contacto || 'Directo'}\n   Etapa: ${lead.etapa || 'Nuevo'}\n`;
            });

            await msg.reply(reporte);
        });
        return true;
    }

    // 2. Consulta interactiva de leads (Sintaxis: lead: Nombre)
    if (textoMensaje.toLowerCase().startsWith('lead:')) {
        const nombreBusqueda = textoMensaje.replace('lead:', '').trim();
        const db = new sqlite3.Database('crm_telotengo.db');

        db.get("SELECT * FROM leads WHERE nombre LIKE ?", [`%${nombreBusqueda}%`], async (err, row) => {
            db.close();
            if (err || !row) {
                await msg.reply(`❌ No se encontró ningún lead que coincida con: "${nombreBusqueda}"`);
                return;
            }

            let infoLead = `👤 *INFORMACIÓN DETALLADA DEL LEAD*\n\n`;
            infoLead += `• *Nombre:* ${row.nombre} ${row.apellido || ''}\n`;
            infoLead += `• *Teléfono:* ${row.telefono || 'No registrado'}\n`;
            infoLead += `• *Tipo:* ${row.tipo_contacto || 'Prospecto'}\n`;
            infoLead += `• *Referido por:* ${row.referido_por || 'N/A'}\n`;
            infoLead += `• *Etapa:* ${row.etapa || 'Seguimiento'}\n`;

            await msg.reply(infoLead);
        });
        return true;
    }

    // 3. RECONOCIMIENTO GENERAL: Si el Jefe escribe saludos o cualquier otra cosa
    let respuestaJefe = `¡Hola, Jefe! 🫡 Le reconozco perfectamente. Sofía a sus órdenes.\n\n`;
    respuestaJefe += `📌 *SUS COMANDOS EJECUTIVOS DISPONIBLES:*\n`;
    respuestaJefe += `• Escriba *REPORTE* (en mayúsculas) para ver el resumen general de leads.\n`;
    respuestaJefe += `• Escriba *lead: Nombre* para buscar datos de un cliente (ej: lead: Juan).\n\n`;
    respuestaJefe += `*(He bloqueado la respuesta de la IA de ventas para este mensaje para no generar registros innecesarios en su CRM)*. ¡Quedo atenta a sus instrucciones! 🚀`;

    await msg.reply(respuestaJefe);
    return true; // Retornamos true para detener el flujo aquí y no enviarlo a Groq Cloud
}

// =====================================================================
// MÓDULO DE GESTIÓN DE NOTAS DE VOZ (RESPUESTA AMABLE)
// =====================================================================
async function procesarNotasDeVoz(msg) {
    if (msg.hasMedia && (msg.type === 'ptt' || msg.type === 'audio')) {
        await msg.reply("¡Hola! He recibido tu nota de voz 🎙️. Para brindarte la mejor atención de forma inmediata y precisa, ¿podrías escribirme tu consulta brevemente por aquí por favor? Así podré ayudarte mucho más rápido.");
        return true;
    }
    return false;
}

// =====================================================================
// MÓDULO DE IMPULSO A LA COMPRA Y AGENDAMIENTO AUTOMÁTICO
// =====================================================================
async function procesarIntencionCompra(msg) {
    const texto = msg.body.toLowerCase();
    const palabrasClave = ['agendar', 'reunión', 'precio', 'comprar', 'información', 'contacto', 'cita'];
    const contieneIntencion = palabrasClave.some(palabra => texto.includes(palabra));

    if (contieneIntencion) {
        let respuestaComercial = `¡Excelente decisión! ${DATOS_NEGOCIO.promesa}\n\n`;
        respuestaComercial += `Puedes agendar tu reunión directamente aquí:\n📅 ${DATOS_NEGOCIO.calendarioReuniones}\n\n`;
        respuestaComercial += `O escribirnos por WhatsApp directo:\n💬 ${DATOS_NEGOCIO.agendamentoWhatsapp}`;

        await msg.reply(respuestaComercial);
        return true;
    }
    return false;
}

// =====================================================================
// ESCUCHADOR DE MENSAJES ENTRANTES (ENRUTADOR PRINCIPAL)
// =====================================================================
client.on('message', async msg => {
    // 1. Verificamos si es El Jefe. Si es el Jefe, Sofía le responde y DETIENE el flujo aquí.
    const esJefe = await procesarComandosJefe(msg);
    if (esJefe) return;

    // 2. Verificamos si es una nota de voz de un cliente normal
    const esAudio = await procesarNotasDeVoz(msg);
    if (esAudio) return;

    // 3. Verificamos si tiene intención de compra
    await procesarIntencionCompra(msg);
    
    // Aquí el mensaje continúa su camino normal hacia tu servidor Flask / Groq Cloud si es un cliente regular
});

// Inicializar el cliente
client.initialize();
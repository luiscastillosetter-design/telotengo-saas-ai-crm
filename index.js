const { Client, LocalAuth } = require('whatsapp-web.js');
const Anthropic = require('@anthropic-ai/sdk');
const qrcode = require('qrcode-terminal');

// 1. CONEXIÓN AL CEREBRO DE CLAUDE (Protegido para GitHub)
const anthropic = new Anthropic({
    apiKey: 'TU_API_KEY_AQUI', // <-- Reemplaza con tu llave real en tu entorno local (nunca la subas a GitHub)
});

// 2. CONFIGURACIÓN DEL MOTOR WHATSAPP
const client = new Client({
    authStrategy: new LocalAuth()
});

client.on('qr', (qr) => {
    console.log('📱 Escanea el QR para reconectar el motor:');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('✅ ¡Motor conectado!');
    console.log('🧠 Cerebro Gema en línea, escuchando y lista para cerrar ventas...');
    console.log('---------------------------------------------------------');
});

// 3. MÓDULO DE ESCUCHA ACTIVA Y CIERRE DE VENTAS (MODO SEGURO)
client.on('message', async message => {
    // 1. Filtro base: Evitamos grupos y estados
    if (message.from === 'status@broadcast' || message.from.includes('-') || message.isStatus) return;

    // 2. Filtro: Ignorar los mensajes de tu apertura manual
    if (message.fromMe) return;

    // 3. Filtro: Ignorar mensajes vacíos
    if (!message.body || message.body.trim() === '') return;

    console.log(`👤 Prospecto [${message.from.split('@')[0]}] dice: ${message.body}`);

    try {
        console.log('⏳ Gema está pensando la respuesta...');

        const response = await anthropic.messages.create({
            model: "claude-haiku-4-5-20251001", 
            max_tokens: 250,
            system: `Eres Gema, la SDR y cerradora de ventas de Telotengo Solutions.
            Un prospecto acaba de responder a nuestra campaña de prospección.
            
            Reglas estrictas:
            1. Sé persuasiva, natural y concisa (máximo 3 oraciones).
            2. Si el prospecto tiene una objeción, rebátela educadamente enfocándote en que nuestro sistema es 'Done-for-you'.
            3. Si el prospecto dice 'sí' o muestra interés, entrégale este enlace para agendar una auditoría gratis: https://api.leadconnectorhq.com/widget/booking/cHgLoMCK71bch2PmxVee
            4. Si el prospecto pide más información, ofrécele OBLIGATORIAMENTE los regalos VIP por contratar (Web de $1,500 y 3 meses de redes por $2,400 gratis).
            5. Nunca envíes código ni formato markdown. Solo texto limpio.`,
            messages: [
                { role: "user", content: message.body }
            ]
        });

        const respuestaGema = response.content[0].text;

        // Pausa aleatoria anti-bloqueo (entre 8 y 14 segundos)
        const tiempoPausa = Math.floor(Math.random() * (14000 - 8000 + 1) + 8000);
        console.log(`⏳ Esperando ${tiempoPausa/1000} segundos antes de enviar (Modo Seguro)...`);
        await new Promise(resolve => setTimeout(resolve, tiempoPausa));

        // Enviar respuesta DIRECTA (Evitamos usar message.getChat() para que no colapse)
        await message.reply(respuestaGema);

        console.log(`✅ Gema respondió: ${respuestaGema}`);
        console.log('---------------------------------------------------------');

    } catch (error) {
        console.error('❌ Error DETALLADO en el cerebro de Gema:');
        console.error(error); 
        console.log('---------------------------------------------------------');
    }
});

// 4. ENCENDIDO DEL MOTOR 
client.initialize();
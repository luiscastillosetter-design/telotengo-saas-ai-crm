-- =====================================================================
-- Persistencia de Sofia WhatsApp en Supabase (reemplaza SQLite en /tmp de Vercel)
-- Ejecutar en: Supabase > SQL Editor. Prefijo sofia_wa_ para no chocar con tablas existentes.
-- Todo el acceso se hace desde el servidor con SUPABASE_SERVICE_ROLE_KEY (omite RLS).
-- RLS activado SIN politicas: anon/authenticated no pueden leer ni escribir nada.
-- =====================================================================

-- 1) Anti-duplicados de webhook (msg_id unico)
CREATE TABLE IF NOT EXISTS public.sofia_wa_webhook_logs (
    msg_id     TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sofia_wa_webhook_logs_created
    ON public.sofia_wa_webhook_logs (created_at);

-- 2) Historial de chat por telefono
CREATE TABLE IF NOT EXISTS public.sofia_wa_historial (
    id         BIGSERIAL PRIMARY KEY,
    telefono   TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sofia_wa_historial_tel
    ON public.sofia_wa_historial (telefono, id DESC);

-- 3) Anti-spam: un registro por uso de IA (ventana deslizante de 24h)
CREATE TABLE IF NOT EXISTS public.sofia_wa_antispam (
    id         BIGSERIAL PRIMARY KEY,
    telefono   TEXT NOT NULL,
    ts         DOUBLE PRECISION NOT NULL,  -- epoch en segundos
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sofia_wa_antispam_tel
    ON public.sofia_wa_antispam (telefono, ts);

-- Seguridad: RLS sin politicas publicas
ALTER TABLE public.sofia_wa_webhook_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sofia_wa_historial    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sofia_wa_antispam     ENABLE ROW LEVEL SECURITY;

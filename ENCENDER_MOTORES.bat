@echo off
title Ecosistema Telotengo Solutions AI - Centro de Mando
color 0A

echo ================================================================
echo   INICIANDO MOTORES DEL SISTEMA SAAS (FLASK + STREAMLIT + TUNEL)
echo ================================================================
echo.

echo [1/3] Levantando Motor Backend de IA y Webhook de Meta (Puerto 5000)...
start "Motor 1 - Servidor Backend (API Meta)" cmd /k "python servidor.py"

echo Esperando 3 segundos para asegurar la inicializacion del modo WAL...
timeout /t 3 /nobreak >nul

echo [2/3] Levantando Centro de Mando Visual CRM (Puerto 8501)...
start "Motor 2 - CRM Visual Command Center" cmd /k "python -m streamlit run crm_visual.py"

echo Esperando 3 segundos para estabilizar la interfaz web...
timeout /t 3 /nobreak >nul

echo [3/3] Levantando Tunel Cloudflare para recibir mensajes de WhatsApp...
start "Motor 3 - Tunel Cloudflare" cmd /k "cloudflared tunnel run --url http://localhost:5000 telotengo-bot"

echo.
echo ================================================================
echo   ¡SISTEMA ENCENDIDO CON EXITO! LOS 3 MOTORES ESTAN OPERANDO.
echo ================================================================
echo   - Backend IA: http://localhost:5000
echo   - Panel CRM:  http://localhost:8501
echo.
echo Puedes minimizar esta ventana pero NO la cierres mientras operes.
pause >nul
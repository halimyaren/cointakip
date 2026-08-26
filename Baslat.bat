@echo off
title Kripto Portfoy & Canli Terminal
cd /d "%~dp0app"

echo ========================================================
echo   KRIPTO PORTFOY TAKIP & CANLI TERMINAL BASLATILIYOR...
echo ========================================================
echo.

start "" "http://localhost:8000"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
pause

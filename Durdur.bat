@echo off
title Kripto Terminal Durdurucu
echo ========================================================
echo   KRIPTO PORTFOY TERMINALI DURDURULUYOR...
echo ========================================================
echo.

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo Uygulama basariyla durduruldu ve kapatildi.
timeout /t 2 >nul

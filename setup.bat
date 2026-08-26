@echo off
setlocal enabledelayedexpansion
title CoinTakip - Kurulum Sihirbazi
cd /d "%~dp0"

echo ========================================================
echo   COINTAKIP - KURULUM SIHIRBAZI
echo ========================================================
echo.
echo Bu sihirbaz gerekli kontrolleri yapar ve bagimliliklari
echo kurar. Mevcut verilerinize DOKUNMAZ.
echo.

REM ---------------------------------------------------------
REM 1) Python var mi?
REM ---------------------------------------------------------
echo [1/5] Python kontrol ediliyor...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   HATA: Python bulunamadi.
    echo.
    echo   Python 3.10 veya uzeri gerekli. Kurulum:
    echo     https://www.python.org/downloads/
    echo.
    echo   ONEMLI: Kurulum sirasinda "Add Python to PATH"
    echo   secenegini mutlaka isaretleyin.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Bulundu: Python !PYVER!

REM Surum en az 3.10 mu? (major.minor kontrolu)
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    set MAJOR=%%a
    set MINOR=%%b
)
if !MAJOR! LSS 3 goto :eskisurum
if !MAJOR! EQU 3 if !MINOR! LSS 10 goto :eskisurum
goto :surumtamam

:eskisurum
echo.
echo   UYARI: Python !PYVER! eski. En az 3.10 onerilir.
echo   Kuruluma devam edilebilir ama sorun cikabilir.
echo.
choice /c EH /n /m "   Devam edilsin mi? (E/H): "
if errorlevel 2 exit /b 1

:surumtamam
echo.

REM ---------------------------------------------------------
REM 2) pip var mi?
REM ---------------------------------------------------------
echo [2/5] pip kontrol ediliyor...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   pip bulunamadi, kuruluyor...
    python -m ensurepip --upgrade
    if errorlevel 1 (
        echo   HATA: pip kurulamadi.
        pause
        exit /b 1
    )
)
echo   pip hazir.
echo.

REM ---------------------------------------------------------
REM 3) Bagimliliklar
REM ---------------------------------------------------------
echo [3/5] Bagimliliklar kuruluyor (fastapi, uvicorn, pydantic, openpyxl)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo   HATA: Bagimliliklar kurulamadi.
    echo   Internet baglantinizi kontrol edip tekrar deneyin.
    echo.
    pause
    exit /b 1
)
echo   Kuruldu.
echo.

REM ---------------------------------------------------------
REM 4) Dogrulama
REM ---------------------------------------------------------
echo [4/5] Kurulum dogrulaniyor...
python -c "import fastapi, uvicorn, pydantic, openpyxl; print('   Tum paketler yuklendi.')"
if errorlevel 1 (
    echo   HATA: Paketler ice aktarilamadi.
    pause
    exit /b 1
)

if not exist "app\static\vendor\tailwind.min.js" (
    echo   UYARI: app\static\vendor klasoru eksik gorunuyor.
    echo   Arayuz kutuphaneleri yerelde bulunamadi; uygulama
    echo   internet olmadan duzgun gorunmeyebilir.
)
echo.

REM ---------------------------------------------------------
REM 5) Veri klasoru
REM ---------------------------------------------------------
echo [5/5] Veri klasoru hazirlaniyor...
if not exist "data" mkdir "data"
if not exist "data\backups" mkdir "data\backups"
if not exist "data\logs" mkdir "data\logs"

if exist "data\portfolio.json" (
    echo   Mevcut portfoy bulundu - korundu, uzerine yazilmadi.
) else (
    echo   Yeni kurulum: uygulama ilk acilista bos portfoy olusturacak.
)
echo.

echo ========================================================
echo   KURULUM TAMAMLANDI
echo ========================================================
echo.
echo   Uygulamayi baslatmak icin: Baslat.bat
echo   Testleri calistirmak icin: python -m pytest
echo                              (once: pip install -r requirements-dev.txt)
echo.
choice /c EH /n /m "   Uygulamayi simdi baslatmak ister misiniz? (E/H): "
if errorlevel 2 goto :son
if errorlevel 1 (
    echo.
    echo   Baslatiliyor...
    call "Baslat.bat"
    exit /b 0
)

:son
echo.
pause

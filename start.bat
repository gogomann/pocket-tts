@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo  Starting Pocket TTS Studio (Windows Docker)...
echo ==================================================

if not exist voices mkdir voices
if not exist fertige_files mkdir fertige_files

if not exist .env (
    if exist .env.example (
        echo Creating .env from .env.example...
        copy .env.example .env >nul
    )
)

docker compose up -d --build
if errorlevel 1 (
    echo Notice: Retrying build with docker build...
    docker build -t pocket-tts:latest .
    docker compose up -d
)

echo.
echo ==================================================
echo  Pocket TTS Studio laeuft erfolgreich!
echo  Web-Interface: http://localhost:8000
echo  Logs:          docker compose logs -f
echo  Stoppen mit:   stop.bat
echo ==================================================
echo.
pause

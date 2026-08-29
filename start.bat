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

docker image inspect pocket-tts:latest >nul 2>&1
if errorlevel 1 (
    echo Building Docker image pocket-tts:latest...
    docker build -t pocket-tts:latest .
)

docker compose up -d --no-build

echo.
echo ==================================================
echo  Pocket TTS Studio laeuft erfolgreich!
echo  Web-Interface: http://localhost:8000
echo  Logs:          docker compose logs -f
echo  Stoppen mit:   stop.bat
echo ==================================================
echo.
pause

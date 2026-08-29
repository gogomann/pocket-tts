@echo off
cd /d "%~dp0"
echo Stoppe Pocket TTS Studio...
docker compose down
echo Gestoppt.
pause

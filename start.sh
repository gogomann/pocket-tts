#!/usr/bin/env bash
set -e

# Add standard tool paths (Mac/Linux)
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:$PATH"

# Change to script directory
cd "$(dirname "$0")"

echo "=================================================="
echo " Starting Pocket TTS Studio (Docker)..."
echo "=================================================="

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Fehler: 'docker' wurde nicht gefunden."
    echo "Bitte installiere Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
fi

# Ensure directories exist
mkdir -p voices fertige_files

# Copy .env.example to .env if not exists
if [ ! -f .env ] && [ -f .env.example ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Build Docker image if not present
if ! docker image inspect pocket-tts:latest &> /dev/null; then
    echo "Building Docker image pocket-tts:latest..."
    docker build -t pocket-tts:latest .
fi

# Start containers in background
docker compose up -d --no-build

echo ""
echo "=================================================="
echo " ✅ Pocket TTS Studio läuft erfolgreich!"
echo " 👉 Web-Interface öffnen: http://localhost:8000"
echo " 👉 Logs anzeigen:        docker compose logs -f"
echo " 👉 Stoppen mit:          ./stop.sh"
echo "=================================================="

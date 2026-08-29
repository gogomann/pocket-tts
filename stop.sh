#!/usr/bin/env bash
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:$PATH"
cd "$(dirname "$0")"
echo "Stopping Pocket TTS Studio..."
docker compose down
echo "Pocket TTS Studio gestoppt."

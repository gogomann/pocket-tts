Set-Location -Path $PSScriptRoot

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Starting Pocket TTS Studio (PowerShell)..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (!(Test-Path -Path "voices")) { New-Item -ItemType Directory -Path "voices" | Out-Null }
if (!(Test-Path -Path "fertige_files")) { New-Item -ItemType Directory -Path "fertige_files" | Out-Null }

if (!(Test-Path -Path ".env") -and (Test-Path -Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Green
}

if (!(docker image inspect pocket-tts:latest 2>$null)) {
    Write-Host "Building Docker image pocket-tts:latest..." -ForegroundColor Cyan
    docker build -t pocket-tts:latest .
}

docker compose up -d --no-build

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host " Pocket TTS Studio laeuft erfolgreich!" -ForegroundColor Green
Write-Host " Web-Interface: http://localhost:8000" -ForegroundColor Yellow
Write-Host " Logs:          docker compose logs -f" -ForegroundColor White
Write-Host " Stoppen mit:   docker compose down" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Green

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

try {
    docker compose up -d --build
} catch {
    Write-Host "Notice: Retrying build with docker build..." -ForegroundColor Yellow
    docker build -t pocket-tts:latest .
    docker compose up -d
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host " Pocket TTS Studio laeuft erfolgreich!" -ForegroundColor Green
Write-Host " Web-Interface: http://localhost:8000" -ForegroundColor Yellow
Write-Host " Logs:          docker compose logs -f" -ForegroundColor White
Write-Host " Stoppen mit:   docker compose down" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Green

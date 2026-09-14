# AI Council - start the server (it serves both the API and the web interface) and open the browser.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env") -and -not (Test-Path "backend/.env")) {
    Write-Host "No .env file found." -ForegroundColor Red
    Write-Host "  1. Copy .env.example to .env"
    Write-Host "  2. Set GROQ_API_KEY (free at https://console.groq.com/keys)"
    exit 1
}

$python = if (Test-Path ".venv/Scripts/python.exe") { (Resolve-Path ".venv/Scripts/python.exe").Path } else { "python" }

Write-Host "Checking dependencies..." -ForegroundColor Cyan
& $python -m pip install -r backend/requirements.txt --quiet --disable-pip-version-check

Write-Host "Starting AI Council at http://localhost:8000" -ForegroundColor Green
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 3
    Start-Process "http://localhost:8000"
} | Out-Null

Set-Location backend
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

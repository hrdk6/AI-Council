# AI Council - Start Both Backend and Frontend
# This script starts both services in separate windows

Write-Host "🚀 Starting AI Council - Complete Setup" -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "❌ Error: .env file not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please create a .env file:" -ForegroundColor Yellow
    Write-Host "  1. Copy .env.example to .env" -ForegroundColor Yellow
    Write-Host "  2. Add your GROQ_API_KEY" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Example:" -ForegroundColor Gray
    Write-Host "  GROQ_API_KEY=your_key_here" -ForegroundColor Gray
    Write-Host ""
    exit 1
}

Write-Host "✓ Found .env file" -ForegroundColor Green
Write-Host ""

# Get current directory
$projectRoot = Get-Location

# Start backend in new window
Write-Host "🔧 Starting Backend Server..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$projectRoot'; .\start_backend.ps1"

# Wait for backend to be ready
Write-Host "⏳ Waiting for backend to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$backendReady = $false
$attempts = 0
$maxAttempts = 12

while (-not $backendReady -and $attempts -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/v1/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "✓ Backend is ready!" -ForegroundColor Green
        }
    } catch {
        $attempts++
        Write-Host "  Attempt $attempts/$maxAttempts..." -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

if (-not $backendReady) {
    Write-Host "⚠️  Backend may still be starting. Launching frontend anyway..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎨 Starting Frontend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$projectRoot'; .\start_frontend.ps1"

Write-Host ""
Write-Host "✅ AI Council is starting!" -ForegroundColor Green
Write-Host ""
Write-Host "Services:" -ForegroundColor White
Write-Host "  • Backend:  http://localhost:8000" -ForegroundColor Cyan
Write-Host "  • Frontend: http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
Write-Host "The frontend will open automatically in your browser." -ForegroundColor Gray
Write-Host ""
Write-Host "To stop the services:" -ForegroundColor Yellow
Write-Host "  1. Close the PowerShell windows, or" -ForegroundColor Yellow
Write-Host "  2. Press Ctrl+C in each window" -ForegroundColor Yellow
Write-Host ""

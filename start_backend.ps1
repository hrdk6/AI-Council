# AI Council - Backend Startup Script
# Run this script to start the FastAPI backend server

Write-Host "🚀 Starting AI Council Backend..." -ForegroundColor Cyan
Write-Host ""

# Check if .env file exists
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  Warning: .env file not found!" -ForegroundColor Yellow
    Write-Host "   Copy .env.example to .env and add your GROQ_API_KEY" -ForegroundColor Yellow
    Write-Host ""
}

# Change to backend directory
Set-Location backend

Write-Host "📦 Installing/checking dependencies..." -ForegroundColor Green
python -m pip install -r requirements.txt --quiet

Write-Host "✓ Dependencies ready" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Starting FastAPI server on http://localhost:8000" -ForegroundColor Cyan
Write-Host "   - API: http://localhost:8000/v1/ask" -ForegroundColor Gray
Write-Host "   - Health: http://localhost:8000/v1/health" -ForegroundColor Gray
Write-Host "   - Docs: http://localhost:8000/docs" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start uvicorn with auto-reload
# Using --reload-dir to avoid watching unnecessary directories
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app

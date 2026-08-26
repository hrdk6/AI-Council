# AI Council - Frontend Startup Script
# AI Council Frontend - Startup Script
# Run this script to start the Streamlit frontend

Write-Host "Starting AI Council Frontend..." -ForegroundColor Cyan
Write-Host ""

# Check if backend is running
$backendRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/v1/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $backendRunning = $true
    }
} catch {
    # Backend not running
}

if (-not $backendRunning) {
    Write-Host "Warning: Backend is not running on http://localhost:8000" -ForegroundColor Yellow
    Write-Host "Start the backend first using: .\start_backend_simple.ps1" -ForegroundColor Yellow
    Write-Host ""
}

# Change to frontend directory
Set-Location frontend

Write-Host "Installing/checking dependencies..." -ForegroundColor Green
python -m pip install -r requirements.txt --quiet

Write-Host "Dependencies ready" -ForegroundColor Green
Write-Host ""
Write-Host "Starting Streamlit on http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start Streamlit
python -m streamlit run app.py

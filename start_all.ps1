# RakshakAI - Launch Backend & Frontend Services
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  Starting RakshakAI Safety Dashboard    " -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

$RootPath = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Start Backend in a new window
Write-Host "Launching Backend (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RootPath\backend'; & '$RootPath\.venv\Scripts\Activate.ps1'; uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

Start-Sleep -Seconds 2

# 2. Start Frontend in a new window
Write-Host "Launching Frontend (Vite on http://localhost:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RootPath\frontend'; npm run dev"

Write-Host "RakshakAI services starting!" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host "Backend API: http://127.0.0.1:8000/docs" -ForegroundColor Yellow

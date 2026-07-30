param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8085
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Virtual environment Python was not found at $Python. Create .venv and install requirements first."
}

Write-Host "Starting OneDesk Assistant FastAPI on http://$HostAddress`:$Port"
& $Python -m uvicorn backend.app.main:app --reload --host $HostAddress --port $Port

# Windows PowerShell launcher for RegView.
# Usage:  .\run.ps1
$ErrorActionPreference = "Stop"

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
pip install --upgrade pip | Out-Null
pip install -r requirements.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example — set ANTHROPIC_API_KEY before continuing." -ForegroundColor Yellow
    exit 1
}

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

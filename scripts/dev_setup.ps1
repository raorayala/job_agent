# Local development setup for Job Search Agent (Windows / PowerShell)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

if (-not (Test-Path .env) -and (Test-Path .env.example)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

python -m job_agent setup
Write-Host "Dev setup complete. Edit config.yaml and .env next."

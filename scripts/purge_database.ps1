# Purge all records from every Job Search Agent SQLite table.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    Write-Host "Virtual env not found. Run scripts/dev_setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

.\.venv\Scripts\python.exe scripts/purge_database.py @args

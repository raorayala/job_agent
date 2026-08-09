# PowerShell script for automated daily sync and job analysis via Windows Task Scheduler
# Usage: Run this script directly or configure it in Windows Task Scheduler.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment Python executable not found at $VenvPython. Run dev_setup.ps1 first."
    exit 1
}

$env:PYTHONUTF8 = "1"

Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting daily Job Search Agent sync..." -ForegroundColor Cyan

# 1. Sync job alert emails from Gmail
& $VenvPython -m job_agent sync-gmail

# 2. Re-analyze all saved jobs in SQLite against candidate profile
& $VenvPython -m job_agent analyze

Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Daily Job Search Agent sync and analysis complete!" -ForegroundColor Green

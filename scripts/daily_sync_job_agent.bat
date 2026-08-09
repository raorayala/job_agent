@echo off
REM Batch script for Windows Task Scheduler daily job agent automation
setlocal

cd /d "%~dp0\.."

set PYTHONUTF8=1
set VENV_PYTHON=.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo Error: Virtual environment python not found at %VENV_PYTHON%
    exit /b 1
)

echo [%date% %time%] Syncing Gmail job alerts...
"%VENV_PYTHON%" -m job_agent sync-gmail

echo [%date% %time%] Analyzing jobs against candidate profile...
"%VENV_PYTHON%" -m job_agent analyze

echo [%date% %time%] Done.

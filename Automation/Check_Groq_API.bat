@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Open Open_Invoice_App.bat first to prepare Python.
    pause
    exit /b 1
)
echo Checking Groq access. No invoice uploaded. One small JSON request uses API quota.
".venv\Scripts\python.exe" Groq_Diagnostic.py
pause

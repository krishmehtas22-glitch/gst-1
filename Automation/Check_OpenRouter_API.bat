@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "INVOICE_CHECK_PY=.venv\Scripts\python.exe"
) else if exist ".build-venv\Scripts\python.exe" (
    set "INVOICE_CHECK_PY=.build-venv\Scripts\python.exe"
) else (
    echo Open Open_Invoice_App.bat first to prepare Python, or use the environment created by Build_Windows_EXE.bat.
    pause
    exit /b 1
)
echo Checking OpenRouter free-only access. No invoice uploaded. One small free JSON request uses quota.
"%INVOICE_CHECK_PY%" OpenRouter_Diagnostic.py
pause

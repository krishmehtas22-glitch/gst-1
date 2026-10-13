@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment is missing. Open Open_Invoice_App.bat first.
    pause
    exit /b 1
)
echo Checking Gemini model access. No invoice will be uploaded.
echo A successful connection test uses one small text-generation request.
".venv\Scripts\python.exe" Gemini_Diagnostic.py
pause

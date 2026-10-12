@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import pypdf, openpyxl, tkinter, rapidocr_onnxruntime, pypdfium2"
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" Invoice_Desktop.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Invoice application could not start. Read the error above.
pause
exit /b 1

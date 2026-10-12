@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import pypdf, openpyxl"
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" Process_All_Demo_Clients.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo Automatic XML could not start. Read the error above.
pause
exit /b 1

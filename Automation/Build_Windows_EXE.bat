@echo off
setlocal
cd /d "%~dp0"
echo Building Windows Invoice Reader. Invoice data and existing .venv are preserved.
if not exist "InvoiceReader.spec" goto missing
if not exist "Windows_Entry.py" goto missing
if not exist ".build-venv\Scripts\python.exe" (
    py -3.13 -m venv .build-venv
    if errorlevel 1 goto python_missing
)
".build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean InvoiceReader.spec
if errorlevel 1 goto failed
start "" /wait "dist\InvoiceReader\InvoiceReader.exe" --self-test "%CD%\dist\InvoiceReader\Build_Check.json"
if errorlevel 1 goto failed
if not exist "dist\InvoiceReader\Build_Check.json" goto failed
echo.
echo Ready: "%CD%\dist\InvoiceReader\InvoiceReader.exe"
echo Keep the whole InvoiceReader folder, including _internal.
echo Double-click InvoiceReader.exe, then Choose invoice parent folder to use your existing invoices.
echo Python is not needed to run the finished app. API keys stay in Windows user environment variables.
explorer "%CD%\dist\InvoiceReader"
pause
exit /b 0
:missing
echo Extract the complete latest update ZIP first. Build files are missing.
goto failed
:python_missing
echo Building requires Python 3.13 with the Windows py launcher. Install it, then run this builder again.
goto failed
:failed
echo Build did not complete. Save the error lines above. Existing invoices and XML were not changed.
pause
exit /b 1

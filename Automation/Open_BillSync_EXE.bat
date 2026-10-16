@echo off
setlocal
cd /d "%~dp0"
if exist "..\Invoice_Desktop.py" (
    start "" "%~dp0InvoiceReader.exe" --data-root "%~dp0.."
) else (
    start "" "%~dp0InvoiceReader.exe"
)

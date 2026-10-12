@echo off
setlocal
cd /d "%~dp0"
echo Starting invoice application from "%CD%"
if not exist "Invoice_Desktop.py" goto incomplete
if not exist "Common_Rules\desktop.py" goto incomplete
if not exist "Common_Rules\ocr.py" goto incomplete
if not exist "Common_Rules\paired_layout.py" goto incomplete
if not exist "Common_Rules\section_layout.py" goto incomplete
if not exist "Common_Rules\supplier_layouts.py" goto incomplete
if not exist "Common_Rules\supplier_editor.py" goto incomplete
if not exist "Common_Rules\tabular_layout.py" goto incomplete
if not exist "Common_Rules\flat_layout.py" goto incomplete
if not exist "Common_Rules\party_evidence.py" goto incomplete
if not exist "Common_Rules\unit_choices.py" goto incomplete
if not exist "Common_Rules\unit_catalog.py" goto incomplete
if not exist "Common_Rules\unit_inference.py" goto incomplete
if not exist "Common_Rules\tax_treatment.py" goto incomplete
if not exist "Common_Rules\workflow_status.py" goto incomplete
if not exist "Common_Rules\source_documents.py" goto incomplete
if not exist "requirements-ocr.txt" goto incomplete
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import sys; print('Python:', sys.version.split()[0]); raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto python_failed
".venv\Scripts\python.exe" -c "import tkinter"
if errorlevel 1 goto tkinter_failed
".venv\Scripts\python.exe" -c "import pypdf, openpyxl"
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install openpyxl==3.1.5 pypdf==6.1.3
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import rapidocr, onnxruntime, pypdfium2" >nul 2>&1
if errorlevel 1 (
    echo Installing optional scanned-PDF OCR dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements-ocr.txt
    if errorlevel 1 echo OCR installation failed. The app will open for text PDFs and manual review.
)
".venv\Scripts\python.exe" Invoice_Desktop.py
set "APP_EXIT=%ERRORLEVEL%"
echo.
echo Application closed. Exit code: %APP_EXIT%
echo If no window appeared, copy the error lines above.
pause
exit /b %APP_EXIT%
:incomplete
echo Program files are missing. Extract the whole update ZIP beside this launcher.
goto failed
:python_failed
echo This Python environment is broken or older than Python 3.10.
echo Copy the error above so the environment can be repaired.
goto failed
:tkinter_failed
echo Python cannot load Tkinter. Repair Python using its Windows installer and include Tcl/Tk.
goto failed
:failed
echo Invoice application could not start. Read the error above.
pause
exit /b 1

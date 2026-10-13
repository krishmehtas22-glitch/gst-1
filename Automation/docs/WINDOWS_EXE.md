# Windows executable

The portable app is **InvoiceReader.exe**. Keep it together with its **_internal**
folder; that folder contains Python, libraries, bundled OCR models and DLLs.
Python does not have to be installed on the computer running the finished app.

## Download a Windows build

Open the repository's **Actions → Build Windows Invoice Reader**. Open a successful
run and download its **InvoiceReader-Windows** artifact at the bottom (GitHub sign-in
may be required). Extract the full ZIP, then double-click **InvoiceReader.exe**.
A build is available only after the Windows workflow has succeeded, including its
frozen OCR/provider self-test. Workflow artifacts expire after 30 days.

Click **Choose invoice parent folder**, then select your existing folder, for example
`F:\Downloads\dummy sales invoice`. This reuses your invoices, `.invoice_app` caches,
manual corrections and output. Do not delete that folder or its hidden data.
You may instead put the executable and `_internal` folder alongside existing files.
Invoice data is stored beside the executable or in the invoice folder you choose;
it is never stored inside `_internal` or a temporary unpacking directory.

API keys remain private Windows user environment variables. The build does not
include your keys, invoices, caches, XML outputs or Tally company data. On another
computer, configure its own keys privately. Tally direct import still needs Tally
running locally with port 9000 enabled. Extraction, AI fallback, complete-folder
imports, amounts and generated XML use the same existing code.

## Build locally on Windows

Extract the whole latest source/update ZIP into your existing program folder and
double-click **Build_Windows_EXE.bat**. Building needs 64-bit Python 3.13 with its
`py` launcher, internet access for packages and sufficient disk space for OCR
libraries. The separate `.build-venv` preserves your current `.venv`. The builder
runs PyInstaller and checks the finished app's bundled OCR models/providers.

The result is `dist\InvoiceReader\InvoiceReader.exe`. Keep the complete containing
folder. Existing invoice/AI caches and XML are never packaged into the app. A build
failure prints its error and does not overwrite existing invoice data.

## Startup problems

If startup fails, look for **InvoiceReader_Startup_Error.log** beside the executable.
The desktop UI is Windows software: a Linux build cannot produce the Windows EXE.

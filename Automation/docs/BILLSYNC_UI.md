BillSync desktop UI — original Reader engine preserved

WINDOWS EXE
Download the InvoiceReader-Windows artifact from the successful Windows build.
Extract the WHOLE ZIP into a NEW folder (for example BillSync-Windows) beside
F:\Downloads\dummy sales invoice\Invoice_Desktop.py. Keep _internal intact.
Double-click Open_BillSync.bat. If the original reader is in the parent folder,
its invoice storage is selected automatically. Otherwise select the existing
storage once in Settings. You can also use a new client and Upload invoices.

The original source reader and Open_Invoice_App.bat remain unchanged.
Original_Reader_Backup.zip contains the pre-UI source and fingerprint manifest.
Existing invoices, source reviews, AI caches, XML and import history are not
included in the program ZIP, modified by installation, or sent to GitHub.
To revert, close BillSync and run the existing Open_Invoice_App.bat.

SOURCE INSTALLATION
The new UI source targets the locked Reader 7.30 engine in this checkout.
Use Open_BillSync_App.bat for the new UI; Open_Invoice_App.bat remains original.
Do not overlay new UI files onto older custom reader sources. The Windows ZIP
contains its matching engine and runs beside the old installation.
Build_Windows_EXE.bat builds and checks the Windows EXE locally if needed.

UI / UPLOAD
Choose a client or click Add client. Upload or drag PDF, PNG, JPG or JPEG invoices.
PDFs retain their bytes. Images are retained locally and embedded without crop
into a deterministic one-page PDF for the existing reader. Original images are
kept under .invoice_app/original_uploads. Matching client PDFs are reused; files
with the same name but different bytes are preserved separately.
Uploads, refresh, startup and watching never start AI or generate XML.
Process this invoice / selected invoices / all client invoices still require the
existing confirmation and shared fresh-request budget. Stop behavior is unchanged.
Double-click opens the complete original editor. Manual save updates XML locally.
View XML is read-only; Open XML folder uses the original reader action.
Import all to Tally opens the exact existing import dialog with company selection
and the original Units -> Masters -> Sales vouchers order and actual results.

The Summary GST checkbox is hidden; its original default is preserved. This UI
update does not force a different accounting mode, infer taxes or change output.
The original Invoice_Desktop.py and every Common_Rules file are byte-identical
to the backup. Naming policy, quantities, rates, taxes, UQC, voucher GUIDs and
Tally transport are unchanged. No imported-success status is inferred from XML.
The desktop is scrollable at smaller resolutions; all fields/details remain
available through the table, complete invoice editor and activity-history window.

API credentials stay in the existing Windows user environment; none are bundled.
The build self-test is offline, initializes OCR and tests actual Tk/drag-and-drop
startup. No live AI extraction or Tally import is used by installation/building.

INCOMING TALLY MASTERS (REVIEW COPY ONLY)
Import masters from Tally opens a separate read-only window. Open the source
company in local Tally and enable its HTTP/XML server on port 9000. Click Connect /
refresh companies, choose the source company, then Import ledgers, items & units.
All three collections must be read successfully before a snapshot is saved.
Review Ledgers, Inventory items and Units tabs; select a row for returned details.
Snapshots are separate JSON files under .invoice_app/tally_master_snapshots,
grouped by source company. View saved snapshot opens a previous copy locally.
These snapshots are NOT applied to extraction, master matching, unit mapping,
XML generation or Import ALL yet. No AI requests or Tally writes are made by this
feature. No Tally company settings are changed. Connection errors are shown.
The original Tally import action still works exactly as before.
Previous_UI_Backup.zip additionally preserves the UI before this refinement.

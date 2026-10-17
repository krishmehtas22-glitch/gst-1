BillSync UI 2.3 — invoice workspace, foreign currency and refund review

FOREIGN CURRENCY
Select an invoice and click Currency / exchange rate (also in the right-click
menu). AI reads the currency and any printed rate during your explicit Process
action. Python converts source monetary values with Decimal, retaining original
amounts in the batch report. Codes, unambiguous symbols and common names/spelling
variants are recognized; ambiguous dollar/yen/rupee symbols need a currency choice.
No market-rate lookup or AI request happens during rate entry, preview or save.
If no printed rate is available, enter INR per ONE unit (e.g. USD, 83.25), preview,
then Save rate & prepare XML. Confirm whether source values are foreign or
already INR. Already-INR values are not multiplied again. Quantity and tax
percentages are unchanged. Printed inverse/100-unit rates are normalized locally.
Missing/invalid/conflicting currency or rate holds new XML and retains previous
output. Fix it before importing the revised invoice. A saved manual rate applies
only to the selected client/source and must be reviewed again if amounts change.
Table totals and export IGST estimates use the INR projection. Refund eligibility
still needs review; changing a manual rate invalidates saved refund reviews.
Original invoice files, AI caches, UQC and Import ALL behavior are preserved.
Backup before this change: Backups/Before_Foreign_Currency.zip.

SOURCE-ONLY UPDATE (NO EXE DOWNLOAD)
Close the app. Save Install_BillSync_Source.py in the existing reader source
folder containing Invoice_Desktop.py and run it with Python. The installer
checks the matching Reader 7.30 engine, backs up existing UI files under
.invoice_app/code_backups/billsync_source_*, then installs UI/upload/snapshot
files, requirements-ui.txt and the authorized Common_Rules export-country and
optional Tally master-matching hooks. Other reader engine files remain unchanged. Existing original and updated exporter fingerprints are checked.
No AI, XML generation or Tally import is sent.
Run the commands printed by the installer to check/install UI dependencies
with the existing .venv and start BillSync_UI.py. The title shows UI 2.2.

WINDOWS EXE
Download InvoiceReader-Windows from the successful Windows build. Extract the
whole ZIP into a NEW folder beside the existing reader source folder's
Invoice_Desktop.py. Keep _internal beside InvoiceReader.exe. Run Open_BillSync.bat.
The existing storage is detected in the parent source folder; otherwise choose
Use existing invoice storage in Settings. Original source launchers still work.
The program ZIP contains no customer documents, caches, reviews, API keys or
import history. Keep browser protection enabled; the source-only update above
is an alternative when a browser blocks the EXE ZIP.

THE APPROVED WORKSPACE
Large drag-and-drop area; Client dropdown and outlined New client control;
complete status cards; invoice processing and Tally/XML actions side by side.
The full-width table has no fixed details panel. Double-click or Enter opens
the original editor. Right-click offers editor, source PDF and XML actions.
All rows stay accessible using scrollbars and search/status filtering. There
is no pagination that changes the existing selected-invoice behavior.
Process selected and Process this invoice call the exact inherited actions.
The adjacent dropdown also offers Process all client invoices. AI starts only
after the original confirmation and shared fresh-request budget. Caches and
approved reads are reused. Stop behavior is unchanged. No startup/upload/
refresh/watch operation triggers AI automatically.
Auto-fill units, test mode, list-only watching, supplier layout and storage
controls are in Settings. Accounting defaults remain unchanged. View history
retains full status/error details; the activity strip previews long messages.
XML ready is the original XML-prepared count, not proof of a Tally import.

DOCUMENTS AND EDITING
Upload or drag PDF, PNG, JPG or JPEG files after choosing a client. PDF bytes
are preserved. Images are retained under .invoice_app/original_uploads and
converted without cropping into deterministic PDFs for the unchanged reader.
Existing matching files are reused; same-named different files are retained.
Text/scanned/multipage PDF, JPG/JPEG (EXIF rotation, CMYK, grayscale) and PNG
were checked through actual local OCR and unchanged Groq-input preparation.
This does not guarantee live AI accuracy on arbitrary unreadable photographs.
The complete original editor keeps all buyer/seller, item/unit and financial
fields. Save changes to XML persists the review and regenerates client XML
locally without a new AI request. View XML is read-only. Folder icon opens the
original output location.

TALLY DIRECTIONS
Import to Tally opens the unchanged Import ALL/company-selection dialog.
Its order remains Units -> Masters -> Sales vouchers, with actual receipts.
Read Tally masters opens a local, read-only connection window for the selected
client. Selecting/importing its snapshot enables optional AI master matching.
Open the source company in Tally and enable its HTTP/XML server on port 9000.
Click Connect / refresh companies, select the source company, then Import
ledgers, items & units. All three reads must succeed before a snapshot is saved.
Ledgers, Inventory items and Units tabs show the returned data. Snapshots are
JSON under .invoice_app/tally_master_snapshots, grouped by source company.
View saved snapshot reopens a local copy; Use snapshot selects it for the client.
Process invoices to match existing party/stock/unit references with Groq; unmatched
entries use the current creation method. See TALLY_MASTER_MATCHING.md. No AI
requests start during snapshot import/selection. No Tally settings are changed.

BACKUPS AND VERIFICATION
Original_Reader_Backup.zip preserves the original engine and launchers.
Previous_UI_Backup.zip preserves the UI before incoming Tally snapshots.
Before_Approved_Design_Backup.zip preserves the UI before this approved design.
Each code-only backup has a checksum manifest. Original fingerprints remain
recorded. EXPORT_COUNTRY_REFUND_CHANGE.json
records the authorized export-country exception. Domestic XML, financial
allocations, PNG/upload/unit/UQC behavior is preserved. TALLY_MASTER_MATCHING_CHANGE.json
records optional AI-context/XML-reference and import dependency/company checks;
Import ALL dispatch, unit protocol, counters and retries remain unchanged. The offline
build smoke check initializes bundled CPU OCR, the UI and drag-and-drop.
No live AI requests or Tally imports are used by installation or build checks.

EXPORT COUNTRY AND REFUND REVIEW
See EXPORT_COUNTRY_REFUND.md. The workspace adds Export country and Potential
IGST refund columns, with Refund review available for an analysed export.

BillSync UI 3.1 — navy, royal blue and amber with boxed sections

BOXED INVOICE REVIEW
The user-selected navy/royal blue/amber palette applies across the workspace and
app dialogs. The editor has three bordered summary cards for invoice number,
buyer and total, plus separate rounded section cards with coloured heading bands.
Summary values use the editor’s existing bound variables, so edits are reflected
without AI calls or financial recalculation. Input borders are more distinct.
All original fields, save callbacks and processing remain intact.
Backup: Backups/Before_Boxed_UI.zip; exception: BOXED_UI_CHANGE.json.

PREMIUM PRESENTATION
Navy navigation, blue and amber accents, cool neutral backgrounds, rounded controls, consistent
Segoe UI typography, calmer status cards and a full-width invoice list. Client
management now has a searchable table and Open workspace action; New client has
a dedicated modal form. Settings groups Preferences and Tools & storage.

The existing invoice editor now presents Invoice details, Seller & buyer, Items,
and Export & currency sections. Every original field, variable, item add/remove
command and Save changes to XML callback is retained. Long sections scroll;
source/test-data notices remain visible. Other app windows share the same style:
Tally import and master review, currency, refund, buyer-ledger and OCR review,
XML, activity and supplier layouts. Confirmations use the app's visual style and
retain explicit yes/no/cancel semantics. Native operating-system file pickers
remain native. XML tabs have horizontal and vertical scrollbars.

Invoice_Desktop.py and all Common_Rules files are byte-identical to the OCR
release. No AI prompts/budgets, processing defaults, source/cache formats, unit
rules, financial calculations, XML writers or Tally transport changed. The source
installer remains cumulative, including all prior foreign-currency and quality
fixes. Backup: Backups/Before_Premium_UI.zip; fingerprints are recorded separately
in PREMIUM_UI_CHANGE.json without replacing earlier locks. Preview images use
included synthetic invoice fixtures, never customer documents.

PDF UPLOAD READABILITY
Explicit PDF uploads now validate the page tree/content references and load/render
every page using a small in-memory preview. Header-only files, truncated/unreadable
PDFs, zero-page files and password-protected PDFs show a per-file error before
being stored. Save an unlocked/exported/scanned copy and upload again. Valid
files in the same batch continue, preserving their original bytes and filenames.
Scanned and multipage PDFs are supported. This is a local readability check,
not OCR, AI extraction or proof that the invoice content is correct. No new AI
credits are used, and existing folder files are not scanned on startup/refresh.
PNG/JPEG conversion, processing, financial XML, masters, quantities, currencies
and import controls are unchanged. Backup: Backups/Before_PDF_Upload_Validation.zip.

BUYER LEDGER ROLE CHECK
Python validates AI buyer-ledger choices using the imported name and Under group,
even when the buyer GSTIN matches. Sales, CGST, SGST, IGST, Cess, Round Off and
the review-difference account cannot become buyer ledgers. Non-party groups and
unknown custom subgroup ancestry require review. Direct Sundry Debtors/Creditors
groups still need the original buyer GSTIN/name/address/country checks.
Wrong roles hold new XML and retain the previous output. If an existing system
ledger such as Sales is Under Sundry Debtors, correct it in Tally and read masters
again; the app does not rename or alter that ledger automatically.
Right-click an invoice -> Review buyer ledger. The dialog shows the selected
name/group and explains conflicts. Select a verified party ledger, or explicitly
use the current invoice-buyer creation method, then Save buyer & prepare XML.
The action is local, preserves stock/unit choices and invoice facts, and sends no
AI request or Tally write. Existing XML can still be viewed as retained previous
output; prepare the corrected client XML before importing the affected invoice.
Backup: Backups/Before_Buyer_Ledger_Guard.zip.

DUPLICATE INVOICE WARNING
Once invoice fields have been analysed or entered manually, the same invoice
number and date in one client shows a red Duplicate invoice — review status.
Seller/GSTIN, amount and file fingerprint are not part of this comparison.
Known date formats normalize to the same calendar date; number comparison ignores
case and extra spaces but preserves punctuation. Missing/unread fields do not
match. Clients are kept separate. Uploading/listing does not start extra AI/OCR.
This is a warning only: both files and vouchers are retained, GUIDs stay stable,
and the user can continue processing/importing both. Needs review includes these
rows; selected-invoice details and Batch_Report.json/narration explain the warning.
Correcting the number/date or removing a row clears its current-list warning.
Existing XML is only rebuilt through the existing explicit processing/save actions.
The comparison covers invoices present in the client workspace, not deleted
documents or a live query of Tally's voucher history. Currency/quantity rules
remain locked. Backup: Backups/Before_Duplicate_Warning.zip.

EXACT QUANTITIES
The currency release is locked. The quantity-only follow-up preserves 2.4877 KG
as 2.4877 KG in actual/billed quantities and batch allocations, with at least
four decimal places on a newly generated unit. The maximum required precision
across all rows using a unit is retained. Existing imported Tally units are
checked across every referenced row, including rows without an AI assignment.
If an existing KG unit supports fewer decimals, new XML is held with an explicit
instruction: increase Number of decimal places in Tally, read masters again,
then prepare XML. The app does not round quantities or silently alter Tally
masters. The existing import connection also checks units in the destination.
More than six significant decimal places requires source/unit review rather
than automatic rounding. Backup: Backups/Before_Quantity_Precision.zip.

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

OCR ambiguity review (17 October 2026): during explicit invoice processing,
low-confidence regions and possible letter/digit confusions such as Penci1
receive up to four local threshold-crop second reads per page. Primary OCR text
and original documents are retained. Alternate readings are clearly marked as
uncertain evidence in the existing AI request, without another provider call.
If alternate numbers disagree with primary numbers, those alternatives stay in
local evidence and are withheld from AI hints. Python never performs a global
1→l or 0→o replacement. This does not guarantee every spelling/code is correct.

Uncertain invoices retain an OCR source-review warning in results and XML audit
narration. Right-click an invoice > OCR reading evidence to compare readings,
open the source or edit through the existing invoice editor. Saving reviewed
manual corrections preserves them and resolves the same warnings. Old AI caches
remain reusable; no paid reread is forced. New local evidence can flag a cached
result without rewriting its extracted values. Embedded-PDF text and the existing
unit, accounting and Import ALL rules are preserved. Upload/list/startup do not
run OCR or AI. Up to 5,000 JSON characters of complete evidence entries are
included in AI hints; remaining local evidence remains available for review.

# Sales invoice automation

## Desktop workflow: inspection, corrections and seller grouping

On Windows, double-click `Open_Invoice_App.bat` alongside `main.py`. Select the
parent folder containing the client folders. Leave **Watch for new PDFs** enabled
to process stable file changes automatically. The **Dummy PDFs** checkbox is for
the supplied fictional documents; uncheck it for real invoices. Real invoices
must contain valid GSTINs and explicit registration/tax details, or require review.
The application reads supported text layouts, not every possible invoice style.
Image-only pages are rendered locally and read with bundled RapidOCR models.
The OCR engine is `rapidocr` 3.10, which supports Python 3.13; the older
`rapidocr_onnxruntime` 1.4.4 package is no longer used. The Windows launcher
installs OCR from `requirements-ocr.txt`, keeping an existing `.venv` intact.
No external OCR service or API key is used. OCR may miss or misread fields; every
OCR-derived invoice must be checked in Review before it can generate XML. Use
**Open source PDF** to compare the original. Extracted records are cached by PDF
digest and parser revision, so unchanged scans do not repeatedly run OCR.

The reader also recognizes alternate invoice/date labels, separate seller/buyer
blocks with role-specific GSTIN/state fields, and reordered item columns with
combined GST rates or separate component rates. Multiple labels on one row and
standalone labels above their values are supported. Arbitrary layouts, complex
multi-page tables, handwriting, ambiguous OCR and unsupported GST treatments
still require review; automatic recognition of every invoice is not guaranteed.

The app displays extracted invoice summaries and errors. Select an invoice and
click **Review selected invoice** to correct fields/items in a form, then
**Approve corrections and revalidate**. Approval binds the corrections to the
exact PDF SHA256 and never bypasses GST, total, unit or master-conflict checks.

### Save a supplier layout once

Select a readable text invoice and click **Save supplier layout**. The editor
shows its extracted PDF text beside the mapping form. For a layout the reader
already recognizes (including CLIENT 11), leave the mappings blank, check the
supplier name/GSTIN and layout headings, then **Preview mapping** and **Save
supplier layout**. Pick a clean taxable invoice as the sample: a layout does
not resolve "exempt / nil-rated" ambiguity or approve future OCR.

For a new layout, correct the sample's invoice values in Review first if they
were wrong. In the layout editor, enter only the mappings needing help:

- **PDF label** is the printed label, not its value: Number → `Reference`,
  Date → `Issued`, Total → `Invoice Value`, for example.
- **Start heading / End heading** restrict the field to a party/metadata
  section. Seller GSTIN → `Registration ID`, between `VENDOR` and `BILLING
  PARTY`; Buyer GSTIN → the same label, between `BILLING PARTY` and `DELIVERY`.
- **Column** selects Both, Left or Right for side-by-side panels.
- **Read** normally uses After label. Use First line to read a party name on
  its own line after a heading; a name merged with its address still needs a
  supported structural anchor or review.
- **Item columns** accepts alternative printed table headings, separated by
  semicolons: Quantity → `Pieces; Count`, HSN → `Tariff`. This maps headers,
  not fixed column numbers, quantities, units or rates. Pipe-separated or
  consistently spaced table cells are supported. Wrapped/complex tables may
  still require review.
- **Layout headings** are stable identifying text separated by semicolons;
  they must appear in future PDFs. Use headings such as `TAX BILL; VENDOR`,
  never an invoice number, date or amount.

Preview shows the newly extracted parties, identifiers, classification, totals,
GST and item values. Compare them with the original PDF before saving. A sample
that does not balance or differs from already checked invoice/item values is
blocked. The mapping stores labels, sections, header aliases and supplier/mode
identity; sample invoice numbers, amounts and buyer values are not copied into
future invoices. New PDFs are independently read and validated. Mappings cannot
create missing data or replace explicit export treatment.

Layouts are kept in `.invoice_app/supplier_layouts/`, scoped to the printed
seller GSTIN and real/dummy mode, and reused across source client folders. Each
layout requires its headings and configured labels. Overlapping layouts require
editing/narrowing instead of guessing which one to use. The selected invoice's
details show the applied layout name. Saving/editing/removing a layout refreshes
the extraction cache and triggers a scan. Existing PDF-specific corrections
remain retained; use Re-read selected PDFs if an old override is blocking the
new mapping. Company identity/history and import confirmations are preserved.
Reopen **Save supplier layout** to edit a saved layout or remove it; changes and
removals are archived in its `backups` folder. Back up `.invoice_app` with the
client data. This feature is used by the desktop workflow.

Every OCR invoice still requires human review. Supplier layouts reduce repeated
label/column corrections; they are not universal invoice recognition or tax
classification rules. Unknown units need company unit/UQC configuration.

When a reader update recovers previously missing fields, unchanged fields from
an older native-PDF review refresh from the source; explicit human corrections
remain retained. Existing OCR approvals and older reviews without a baseline
are preserved as complete overrides. If one of those old overrides still blocks
a readable PDF, select its row(s) and use **Re-read selected PDFs**. This archives
only those saved reviews and extraction caches under `.invoice_app/review_backups/`
before re-reading. Company configurations, databases, import confirmations and
original PDFs are not reset or deleted.

Use the **Client folder** dropdown to inspect just CLIENT 8 or CLIENT 9 rather
than the older sample folders. **All clients** remains the default. Outputs are
still company-based retained pending batches: selecting a source folder does not
delete a company's other pending invoices or confirmed history.
The review form offers dropdown choices for GST classification, registration,
supply and export mode. These choices correct a particular invoice; they do not
teach the reader a new layout. Exports cannot be edited into domestic sales or
changed between LUT and IGST payment modes. Explicit exports generate accounting
vouchers, described below.

Each distinct seller GSTIN gets a retained independent company under
`.invoice_app/companies/`, with XML in that company's `imports` directory.
Use **Open selected XML folder** to locate it. Original client folders,
configurations, PDFs and histories are preserved. Source PDFs are copied into
the derived workspaces so their source/history survive moves; copies and JSON
reviews are not moved or deleted automatically. Correcting an already routed
PDF to a different seller/mode is blocked to avoid creating a duplicate invoice
in another company. Back up `.invoice_app` along with the original client data.
Run the desktop app separately from earlier watcher launchers.

The ten uploaded CLIENT 7 PDFs were checked end to end: eight domestic item
invoices and two LUT export accounting vouchers across three companies. The
domestic invoices have fourteen inventory lines; export accounting vouchers
debit the foreign customer and credit the same `Sales` ledger without stock movement.
Desktop company configurations default to `unified_sales_ledger: true`, so taxable,
exempt, nil-rated, non-GST and export sales share the configured taxable-sales
ledger. Their invoice/stock tax classifications remain separate. For a company
that explicitly needs separate sales ledgers, set this option to false; existing
explicit choices are preserved. Prior imported Tally vouchers are not changed by
replacing program files. Only pending XML is regenerated with the new ledger.
The table shows per-invoice preparation/import status; company batch totals appear
once in the selected invoice's details instead of being repeated as row statuses.
NOS, ROLL, KG and SET have explicit unit mappings; unknown units need review and
configuration. Export buyer country, LUT mode and shipping references are retained
in the records, voucher narration and manifest. The manifest explicitly marks
`gst_return_mapping_verified: false`: correct GSTR-1 classification and inventory
handling must be configured/checked per voucher in Tally; they are not established by these
accounting vouchers. Explicit exports with payment of IGST are supported as
accounting vouchers too: credit Sales for the taxable value, credit Output IGST
for the printed tax, and debit the foreign customer for the gross total. CGST
and SGST must be zero, IGST must be positive and reconcile to the item rates.
Exempt
classification follows the document's explicit printed
statement; this is not an independent HSN exemption determination.

The revised CLIENT 8 PDFs (all Western Trade Supplies) also generate all ten
vouchers in a single `Sales_Vouchers.xml`, totaling INR 200,934 in customer debits
and INR 187,800 in Sales credits. This layout supports wrapped GST-percent
headings, colon-delimited totals, pipe-separated currency/payment metadata,
buyer state from the printed GSTIN, an explicit exempt statement, and the
equivalent LUT wording "without payment of integrated tax". The export country
is read from the printed address when it is explicitly UAE/USA. Other missing
countries still require review.

The CLIENT 11 seller/invoice and buyer/supply panels also support wrapped
paragraphs and several labels separated by a single space. The reader keeps
left/right columns separate before reading fields. Seller names are corroborated
by the explicit signatory footer; buyer names use a repeated name/address anchor.
Absent or conflicting name anchors require review rather than a guessed name.
The explicit synthetic-document notice is recognized in dummy mode. A single
item with omitted GST percentages can recover component rates from its printed
tax totals only when its value reconciles to the invoice taxable total and the
calculated rates reproduce every component amount. This evidence is displayed
in the selected invoice's details. Multi-item totals without item rates still
require review. Neither calculation nor HSN alone establishes the legal rate.

All ten uploaded CLIENT 11 PDFs extract seller, buyer, GSTINs, dates, items and
totals. Eight prepare immediately, including LUT and IGST-paid exports. The
remaining two say "exempt / nil-rated" in their remarks: select/confirm the
classification in Review. After approving them as exempt, the verified XML has
ten vouchers: Sales INR 121,200, CGST INR 2,316, SGST INR 2,316, IGST INR 10,074
and customer debits INR 135,906. Replacing program files does not change vouchers
already imported in Tally.

The nine CLIENT 12 PDFs also prepare nine vouchers without manual corrections.
The reader now supports billed-to/consignee/header arrangements, wrapped table
headings and descriptions, reordered HSN columns, mixed GST rates, explicit
percentage discounts, a receipt's numbered item/HSN/quantity blocks, Indian
currency grouping and distinct printed exempt versus nil-rated treatments.
Seller identity comes from the banner/GSTIN and matching signatory, while billing
and shipping parties remain separate. The explicit software-test/fictional-data
notices are recognized in dummy mode. Seller display case differences do not
create another company; genuinely different names still require review.

For a printed percentage discount, the reader calculates the net unit rate and
checks quantity × net rate against the printed taxable value. Tally inventory
uses that **net rate**, with no separate discount ledger/column. Printed list
prices and discounts remain in item records, the Review form and voucher
narration; altered list prices/discounts that do not reconcile are rejected.
Other discount types remain unsupported. Discount and foreign-price fields are
included in duplicate comparisons; earlier verified hash formats remain readable
without changing retained import confirmations.

USD/AED export prices require the explicitly printed exchange rate and both
foreign/INR item values and foreign invoice total. Each item's foreign quantity
× price, foreign value × exchange rate and INR extension must reconcile, as
must the foreign subtotal and INR GST/gross total. Accounting currency stays
INR. The original currency/prices, foreign invoice value, exchange rate and
shipping references are retained in records/narration/manifest. These exports
remain accounting vouchers without inventory movement or verified GSTR-1 mapping;
foreign-currency Tally debtor balances are not generated by this adapter.

Built-in units now include BOX (BOX), PRS (PRS), REAM (RIM), PKT (PAC), KGS (KGS)
and DOZ (DOZ), without converting the printed quantities into individual pieces.
Missing built-in mappings are added to desktop company configurations while
explicit existing unit/UQC choices are retained. Check these UQC mappings in your
Tally release, particularly the printed packet/ream units, before filing.

The verified CLIENT 12 totals are Sales INR 1,662,326, CGST INR 3,558.55, SGST
INR 3,558.55, IGST INR 139,915.70, net round-off credit INR 0.20 and customer
debits INR 1,809,359. There are nineteen domestic inventory lines and two
export accounting vouchers. If a previous PDF-specific override still contains
missing fields, select those rows and Re-read selected PDFs; no client/history
reset is required. The supplier editor supports explicitly mapped labels with
spacing in place of a colon, including invoice metadata in side columns.

Duplicate comparison now uses validated accounting facts, not PDF layout or
extraction audit details. Older stored hashes are checked against their retained
data and read compatibly, preserving history and imported status. A changed
amount, buyer/seller identity, item, tax rate or supply treatment still conflicts;
corrupted stored hashes remain errors. Original extraction/adjustment records
and source copies remain retained.

Live TallyPrime import and the Windows desktop launcher are not validated in the
Linux onboarding machine. XML generation is preparation, never import confirmation.

A central Python engine for independent clients, following the supplied merged
rules and the user's updated folder location. Extract the contents of
**Sales_Invoice_Automation_XML.zip** directly into `F:\Downloads\dummy sales invoice`
on Windows, keeping `main.py` and `Common_Rules` alongside each other.
No drive letter or Client 1 dependency is embedded in the program. Run from any
working directory; paths default to the directory containing `main.py`.

## What works, and what is pending

Implemented: conservative text-PDF extraction, digest-bound reviewed records,
Decimal GST and accounting validation, inventory capture, persistent per-client
history, client discovery, master dependency planning, conflict checks, reliable
existing-company snapshot checks, and explicit import-result recording.

**Native Tally XML is the default output.** The engine generates Masters.xml
and Sales_Vouchers.xml without Excel templates, using Tally's documented
import envelope and item-invoice structure. See [XML import instructions](docs/TALLY_XML.md).
The official XML documentation is now accessible and was inspected. Automated
tests verify generated structures and accounting; a live dummy-company Tally
import has not been run here. The supplied 25 marked dummy PDFs were extracted
and generated as 25 vouchers in explicit demo mode; their printed totals sum to
Rs 255,054.79. They are not valid production invoice data. Validate GST reports
against your TallyPrime release before production.

The optional Excel adapter remains guarded behind verified source workbooks
and mappings; set output_format to excel only after completing that separate
mapping. XML does not depend on those Excel files.

This is an initial engine, not universal invoice OCR. Supported automatic layouts
use explicit labelled fields and a table separated by pipes, tabs or two or more
spaces. The supplied banner/BILL TO/invoice-grid layout is also supported.
Other layouts, scanned/encrypted PDFs and uncertain values go to review.
No OCR guesses or silent exemption classification are made. Discounts, cess,
exports with payment of IGST/SEZ, reverse charge and mixed taxable/exempt invoice rules need separate
implementation; they must not be forced through this phase's ordinary domestic
sales rules. No direct Tally connection, automatic production import or GSTR-1
filing is implemented.

## Install and start (Windows PowerShell)

### Automatic folder processing for the supplied dummy PDFs (Windows)

Double-click **Start_Automatic_XML.bat** once and leave its window open.
It uses `.venv` (creating it and installing dependencies if needed). Add any
number of client folders alongside `main.py`, and drop PDFs directly into each
folder or its `Sales Invoices (PDF)` inbox. No per-client CMD commands are needed.
After two unchanged scans, the watcher creates missing demo configurations with
fresh independent company IDs and the folder name as the disposable Tally
company name, then generates `imports/Masters.xml` and `imports/Sales_Vouchers.xml`.
It checks every three seconds and reruns only when inputs/configuration change.
Wait until copying finishes; slow or incomplete PDF copies may require attention.

This launcher explicitly selects the supplied synthetic demo profile:
Maharashtra seller state and Nos units. Other PDFs still undergo validation and
may require review. Real client configurations stop the demo watcher; use the
normal workflow for real invoices. Existing configurations/history are never
replaced. An existing history without its configuration requires restoration,
and a company identity mismatch requires the matching original configuration.
Do not copy another client's history or `client.json` into a new folder.

Generated XML is demo output, not a Tally import confirmation. Use a separate
disposable Tally company matching each client configuration. Closing the watcher
stops monitoring; double-click the launcher again to resume. To start it when you
sign in to Windows, put a shortcut to the launcher in the folder opened by
`shell:startup` in the Windows Run dialog.

The uploaded CLIENT 7 two-column seller/buyer layout is also
supported in demo mode, including multiple item rows, printed HSNs, NOS units,
item GST percentages and CGST/SGST/IGST amounts. Explicit fictional-document
markers are required. Buyer registration is assumed Regular for fictional B2B
buyers and fictional GSTIN checksums are adjusted; all substitutions and original
values are recorded in `reports/demo_adjustments.json`. The desktop workflow uses
a distinct checksum-adjusted fictional seller identifier for each printed seller.
Legacy demo configurations retain their configured seller/history and reject
mixed-seller folders. Taxable INTRA/INTER and explicit EXEMPT supplies are
supported. Explicit LUT exports without payment of IGST generate accounting-only
Sales vouchers; other export modes and reverse charge remain in review.

```powershell
cd "F:\Downloads\dummy sales invoice"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py init-client "client 1" --company "Your Company" --seller-gstin YOUR_VALID_GSTIN
.\.venv\Scripts\python.exe main.py
```

Python 3.10 or later is required. On Linux, from the repository:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r Automation/requirements.lock
.venv/bin/python Automation/main.py run
.venv/bin/python -m pytest Automation/tests -q
```

## Run the supplied dummy PDFs in company abc (Windows CMD)

The supplied PDFs print seller GSTIN `NOT ASSIGNED`, omit units, use synthetic
customer GSTINs (17 fail checksum), and repeat products with varying illustrative
GST rates. Normal `init-client` intentionally requires a valid seller GSTIN.
Use the explicit demo command below for these test documents, with the user's
selected unit `Nos` and printed seller state Maharashtra:

```bat
cd /d "F:\Downloads\dummy sales invoice"
.venv\Scripts\python.exe main.py init-demo-client "client 1" --company "abc" --state "Maharashtra" --unit "Nos"
.venv\Scripts\python.exe main.py run
```

Install dependencies once using the steps above. To update an existing extracted
program, close any running automation command and replace its program files from
the new ZIP. Keep `.venv`, client folders, PDFs, configuration and history. Do not
repeat `init-demo-client` after a successful setup; it refuses to overwrite an
existing client configuration. If you already initialized a real client, create
a separate demo client folder instead of reusing its history.

This profile accepts only the marked synthetic, single-item B2B/B2C layout with
seller GSTIN `NOT ASSIGNED`. It supplies a synthetic checksum-valid seller
identifier, adjusts synthetic buyer checksums where needed, assumes Regular for
dummy B2B customers and buyer state equal to place of supply for dummy B2C
customers, and supplies zero for omitted tax components. It uses the explicitly
selected `Nos` unit and separates stock names by HSN/GST rate to avoid conflicts
between illustrative test rates. Every changed value and the extracted original
are retained in `client 1/reports/demo_adjustments.json`, bound to each PDF digest.
It still validates quantities, amounts, tax rates and state treatment.

XML comments, voucher narration, configuration and the manifest identify the
data as **DEMO ONLY**. Use a disposable Tally company named `abc`; these test
identifiers do not establish registration and must never be used for GST filing.
Normal clients keep strict validation, and cannot accept demo invoices. Use a
separate client configuration and history for real invoices.

To inspect PDFs before any setup, without generating XML:

```bat
.venv\Scripts\python.exe main.py inspect-invoices "client 1"
```

This writes extracted invoice fields and findings to
`client 1/reports/inspection.json`. It requires no GSTIN or client.json and does
not change existing import files or transaction history.

Your existing invoice folder is supported directly:

```text
F:\Downloads\dummy sales invoice\
  main.py
  Common_Rules\
  requirements.txt
  client 1\
    invoice-001.pdf
    invoice-002.pdf
    client.json
  client 2\
    invoice-001.pdf
    client.json
```

Put PDFs directly in any configured client folder. The optional
`<client>/Sales Invoices (PDF)/` inbox is also supported, including its nested
source folders. Both locations can be used together; duplicate checks still
apply. The program never moves or deletes originals and does not scan PDFs in
generated reports, imports, or review folders. Running `python main.py` defaults
to processing; `python main.py run` remains equivalent. This is a per-run scan,
not continuous background watching.
Add clients using `init-client`, with any folder name. A folder containing direct
PDFs or an invoice inbox is discovered even if it needs one-time configuration.
Different clients
must have distinct company IDs. Renaming a client preserves its local database;
deleting a client does not affect any other client or common code.

Set the correct company name, GSTIN, distinct ledger names and unit formal names,
UQC codes and precision in that client's `client.json`. `Nos` is an editable
initial unit configuration, not an automatic substitute for unknown units.
Stock group `Primary` uses Tally's built-in group; configured custom groups are
planned separately. Do not change company identity on an existing history.
Protect and back up client data: it contains customer/GST information.

## Extraction and review

Example supported text labels:

```text
Invoice No: INV-001
Invoice Date: 2026-04-01
Seller: Seller legal name
Seller GSTIN: <valid seller GSTIN>
Buyer: Customer legal name
Buyer GSTIN: <valid buyer GSTIN, or omit when explicitly unregistered>
Buyer Registration: Regular
Buyer State: Maharashtra
Place of Supply: Maharashtra
Tax Treatment: taxable
Taxable Value: 2000
CGST (9%): 180
SGST (9%): 180
IGST: 0
Grand Total: 2360
Item | HSN | Qty | Unit | Rate | Value | CGST % | SGST % | IGST %
Product A | 8418 | 2 | Nos | 1000 | 2000 | 9 | 9 | 0
```

Invoice dates use ISO or Indian day/month/year formats. GSTIN format, state and
checksum are checked. Registration types supported: Regular, Composition,
Unregistered, Consumer. Supply classification must be explicit: taxable,
exempt, nil_rated or non_gst. A missing buyer GSTIN never implies exemption.
Every item needs HSN/SAC, unit, quantity, rate, value and each GST component rate.
Each component total must be explicit, including zero where absent. Item GST
rates and taxable values must reconcile within one paisa, and the final accounting
entry must balance exactly. This conservative
policy sends borderline rounding or discounts to review rather than changing
accounting amounts. Round off up to Rs 1 needs a separate mapped ledger.

`reports/review_drafts/<PDF SHA256>.json` identifies the source and missing fields.
Copy it to `reviews/<same SHA256>.json`, correct its canonical `invoice` fields,
remove extraction_warnings after resolving them, and set `approved` to true.
Keep `source_sha256` unchanged. Review never bypasses accounting validation.
For scanned PDFs, install the optional OCR dependencies used by the desktop
launcher or fill the canonical record from the PDF manually. OCR records require
approval. `Automation/examples/review_record.example.json` is a blank record and
`validated_invoices.json` shows the canonical format after parsing.

## Outputs, duplicates and imports

Each client gets:

- `reports/validation.json`: current errors and processing counts/history.
- `reports/validated_invoices.json`: extracted records and balanced sales entries.
- `reports/master_plan.json`: units, stock groups, ledgers and stock items in order.
- `.automation/history.sqlite3`: durable transactions and events.
- `imports/`: Masters.xml, Sales_Vouchers.xml, and the current import manifest.

These JSON reports are analytical data, not Tally import formats. Masters and
sales are separate XML files. Import masters successfully before sales, using
TallyPrime's Import menu. Never import an old XML file
without a current `manifest.json` with `valid_for_import: true`. Each new run
withdraws previous generated files before creating a current export. Import
results invalidate that batch so it cannot be mistaken for fresh output. See
docs/TALLY_XML.md for dummy-company setup, GST checks and release limitations.

Duplicates use seller GSTIN, invoice number (case insensitive) and Indian
financial year, per client. Content differences are flagged. The database is
retained when PDFs move or disappear. Reruns regenerate the pending batch without
adding repeated transactions; imported invoices are omitted. Invoice number
reuse in another financial year or another client is independent.

Generation means **pending/generated**, never imported. After importing masters
and vouchers in Tally, record results using:

```sh
python main.py confirm-import "Client 1" "Client 1/import_results.json"
```

The results file contains `company_id`, the manifest's exact `generated_at`,
`tally_result_reference` (the actual log/report reference), `masters` and
`vouchers`. Master entries are `{"master": <exact planned master>, "status":
"imported"}`. Voucher entries are `{"invoice_key": <manifest key>, "status":
"imported"}`. Statuses can also be `rejected` or `pending`. Confirm dependent
masters first or together with sales; otherwise sales confirmation is refused.
Rejected invoices remain visible in history and are not silently resubmitted.
Do not report success from XML generation alone.

For an existing company, set `company_mode` to `existing` and supply a normalized
`tally_snapshot.json` from a reliable full export. It must have the matching
`company_id`, `seller_gstin`, ISO `exported_at` with timezone, `complete: true`,
`masters` (same essential fields as the master plan), and `vouchers` containing
`{"invoice": <full canonical invoice>}` records. Default freshness is 24 hours,
configurable using `snapshot_max_age_hours`. This normalized adapter does not
pretend to parse arbitrary Tally exports. Without the full verified snapshot,
existing-company processing is blocked. Matching masters are reused; conflicts
are never overwritten. A matching voucher in the snapshot confirms it exists;
conflicting transaction details go to review.

No running service is required. If a crash leaves `.automation/run.lock`, confirm
no process is using the client before removing that empty lock directory.

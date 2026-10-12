# Sales invoice automation

## Desktop workflow: inspection, corrections and seller grouping

On Windows, double-click `Open_Invoice_App.bat` alongside `main.py`. Select the
parent folder containing the client folders. Leave **Watch for new PDFs** enabled
to process stable file changes automatically. The **Dummy PDFs** checkbox is for
the supplied fictional documents; uncheck it for real invoices. Real invoices
must contain valid GSTINs and explicit registration/tax details, or require review.
The application reads supported text layouts, not every possible invoice style.
Image-only pages are rendered locally and read with bundled RapidOCR models.
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
Exports remain blocked even if their reviewed supply type is edited to domestic.

Each distinct seller GSTIN gets a retained independent company under
`.invoice_app/companies/`, with XML in that company's `imports` directory.
Use **Open selected XML folder** to locate it. Original client folders,
configurations, PDFs and histories are preserved. Source PDFs are copied into
the derived workspaces so their source/history survive moves; copies and JSON
reviews are not moved or deleted automatically. Correcting an already routed
PDF to a different seller/mode is blocked to avoid creating a duplicate invoice
in another company. Back up `.invoice_app` along with the original client data.
Run the desktop app separately from earlier watcher launchers.

The ten uploaded CLIENT 7 PDFs were checked end to end: eight domestic invoices
produced eight vouchers with fourteen inventory lines across three companies.
NOS, ROLL, KG and SET have explicit unit mappings; unknown units need review and
configuration. Two LUT export invoices retain their buyer/country/shipping fields
for inspection but do not generate XML: export-specific GST handling is not yet
implemented. Exempt classification follows the document's explicit printed
statement; this is not an independent HSN exemption determination.

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
exports/SEZ, reverse charge and mixed taxable/exempt invoice rules need separate
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
supported; EXPORT and reverse charge remain in review.

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
For scanned PDFs, fill the canonical record from the PDF manually; no OCR is
bundled. `Automation/examples/review_record.example.json` is a blank record and
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

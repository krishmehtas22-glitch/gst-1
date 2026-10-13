# Sales invoice automation

## Reader 7.6: date-only repair from retained source evidence

Invoice dates now normalize short years (13-Oct-26), numeric day/month dates,
compact YYYYMMDD, written months and ISO timestamps before writing Tally
DATE/EFFECTIVEDATE as YYYYMMDD. Invalid calendar dates are not accepted.
If the retained AI date is missing/invalid, a digest-verified local extraction
or source PDF invoice-date label can recover it. Due/shipping dates and today
are not substituted. Recovery affects only date/audit fields; working seller,
buyer, quantity, unit, rate and stock logic is unchanged.

Use **Scan and generate XML** to repair saved results without another API
request. Date evidence is retained in Batch_Report.json and narration. A date
not present in any verified source remains unresolved, rather than invented.
Import Units.xml → Masters.xml, then retry only rejected vouchers.


## Reader 7.5: correct inventory buyer/tax ledger structure

Inventory vouchers now use LEDGERENTRIES.LIST for the buyer and taxes, matching
the native inventory exporter. Sales credit stays inside each inventory item
(no duplicated standalone Sales posting). Each item includes godown/batch
allocations. Accounting fallback vouchers retain ALLLEDGERENTRIES.LIST.
A serialized-output verifier checks voucher view, buyer-ledger identity,
item/godown allocation amounts and exact total debit/credit balance.

Regenerate from saved reads using Scan and generate XML; no API call is needed.
Import Units.xml → Masters.xml first, then retry only rejected vouchers in Tally.
Quantities, unit/master names and stable voucher GUIDs remain retained.
This fixes a batch-export structure error; it is not a new buyer-extraction
accuracy claim or a verified live Tally import.


## Reader 7.4: units before stock masters; preserve quantity precision

The complete batch exporter now creates **Units.xml** separately. Import
**Units.xml → Masters.xml → Sales_Vouchers.xml** in the SAME selected Tally
company. Units use catalog formal names/UQC labels (KG → KGS-KILOGRAMS,
ROLL → ROL-ROLLS), and decimal places accommodate source quantities. Stock
BASEUNITS and inventory references are checked against these definitions.
Ledgers precede stock masters within Masters.xml.

Quantities, unit rates and GST rates keep their full decimal precision; only
currency amounts round to paise. Cached AI results are reused: choose your
client and **Scan and generate XML** to regenerate files without another API
request. For existing missing-unit/stock exceptions, import the new Units.xml,
import Masters.xml again ignoring duplicates, then retry only rejected vouchers.
Existing successful vouchers/history/GUIDs are retained. Verify unit/master
import results in Tally; live import has not been tested from this environment.


## Reader 7.3: GitHub Models replaces Cerebras

Use **Read client batch with GitHub Models → XML** after privately setting
`GITHUB_MODELS_TOKEN` (a token with Models read permission). The app does not
reuse repository/Git credentials. Run **Check_GitHub_Models_API.bat** to check
your model access; initial model `openai/gpt-4o`, optional override
`GITHUB_INVOICE_MODEL`. See [setup](docs/GITHUB_MODELS_SETUP.md).

The chosen provider runs first, then other configured providers among GitHub
Models, Groq and Gemini, then Python. Cerebras is no longer an active fallback
or desktop action; its old source caches are retained. Shared unit reasoning,
buyer-master verification, complete XML output and history preservation apply
to GitHub Models too. The quoted 15 RPM/150 RPD is not verified for your account.


## Reader 7.2: Cerebras and shared buyer-master rules

Use **Read client batch with Cerebras → XML** after privately setting
`CEREBRAS_API_KEY`. Run **Check_Cerebras_API.bat** to verify your current model
access; optional `CEREBRAS_INVOICE_MODEL` overrides the initial `llama-3.3-70b`.
See [Cerebras setup](docs/CEREBRAS_SETUP.md). The pasted free-tier table is not
verified for your account; request and token quotas both apply.

All AI prompts share party and unit instructions. Buyer/Bill To is separated
from seller, Ship To, bank and signatory. Each voucher ledger reference must
match an exported master, and buyer plus exact buyer_ledger are recorded in
Batch_Report.json. Assumed units retain their reasoning and never scale amounts.

Batch fallback uses the chosen provider first, then other configured providers
among Cerebras, Groq and Gemini, then Python/OCR. Complete XML output, source
cache reuse, client/seller isolation and preserved financial history continue.
Cerebras reads extracted text/OCR, not a raw PDF. No billing change is enabled.


## Reader 7.1: AI selling-unit reasoning

Gemini and Groq may infer missing selling units from product/packaging context
(e.g. pens → PCS, explicitly sold boxes → BOX). Their response includes a
printed/inferred basis and a reason. Assumptions remain visible in the quantity
column, voucher narration and Batch_Report.json; they do not block output.
Printed source units and existing manual corrections take priority. Qty is
treated as a heading, and medicine strength does not become sold mass/volume.
Numeric quantities, rates and values are never scaled. Successful old caches
remain usable without a new request; ambiguous Qty units receive local reasoning.
Reader 7.0 complete-output/fallback rules remain in force.


## Reader 7.0: every batch invoice gets XML for Tally review

**Read client batch with Gemini/Groq → XML** now enables a retained complete-output
policy for that client. Each scanned invoice gets a voucher element, even when
seller, GSTIN, unit, item-rate, or reconciliation details are uncertain. These
are retained in narration and `Batch_Report.json`, rather than blocking XML.
Successful AI reads survive quota expiry. Remaining invoices switch to the
other configured provider and then local Python/OCR. No billing is enabled.

Usable inventory entries have stock-master names keyed by unit/HSN/tax treatment,
avoiding collisions with earlier unit variants. Other invoices use accounting
vouchers and retain extracted items in the report. Printed invoice GST amounts
are posted separately, including explicit zero tax. An unreconciled amount is
posted visibly to **Invoice differences - review**, without replacing printed
amounts. Missing dates or other essential facts can still cause Tally to reject
a voucher; XML creation is not proof of import or correct GST reporting.

**Open client XML folder** opens the current complete run, containing exactly
one `Masters.xml` and `Sales_Vouchers.xml` per seller. Import masters first into
the matching selected Tally company; ignore duplicate existing masters. Multiple
sellers use separate subfolders. Older output runs remain retained. Financial
history/manual corrections are preserved; existing voucher GUIDs are reused
where recoverable. XML generation does not mark anything imported.

The separate exporter does not use old company processing markers; it retains
an OS guard against simultaneous writes. Future batch implementations must
follow the repository `AGENTS.md` contract.


## Reader 6.10: distinguish Groq access and gateway failures

Groq requests identify the client explicitly and accept JSON, rather than
using Python urllib's default user agent. JSON error reasons remain visible
with keys redacted. HTML/Cloudflare denial pages are classified without
printing their contents. A 403 alone does not establish quota exhaustion.
Run **Check_Groq_API.bat**: it now identifies whether the model-list request
or the small JSON generation request failed. Live account access still
requires this Windows diagnostic; a gateway/permission failure cannot be
guaranteed fixed by a client-header change.


## Reader 6.9: partial AI batches still prepare XML

Quota/access/model failures stop new API requests, but the queue continues
applying successful cached results and then prepares XML. Successfully read
PDFs are retained across runs; no fresh request or key is needed to reuse them.
When **Test invoices** is enabled, the batch confirmation explicitly confirms
the successfully read PDFs as fictional test data, avoiding an extra per-PDF
confirmation. Real mode saves no such confirmation. Both Gemini and Groq use
this workflow. Fiscal, missing-field and history checks remain active.


## Reader 6.8: Groq alongside Gemini

Set `GROQ_API_KEY` privately in Windows User environment variables and reopen
the app. Use **Read client batch with Groq → XML** for one client folder, or
**Read selected with Groq** for an invoice requiring desktop review. Groq reads
local PDF text/OCR, not raw PDFs. Both providers retain separate caches and
the most recently successful provider supplies extraction for that source.
Existing manual corrections, history and fiscal validation remain active.

The initial Groq model is `llama-3.3-70b-versatile`; run **Check_Groq_API.bat**
to check your own model access, and set `GROQ_INVOICE_MODEL` if needed. Free
request/token limits vary by model/account. No billing change, automatic paid
fallback, retries or guaranteed extraction accuracy is implied. See
[Groq setup](docs/GROQ_SETUP.md).


## Reader 6.7: client batch with Gemini → XML

Choose one client folder, scan it, then click **Read client batch with Gemini → XML**.
One click queues every invoice shown for that client. Successful API fields are
applied automatically for XML; compare the vouchers in Tally. Manual corrections
and saved transaction/import history are retained. This explicit batch choice
removes only the Gemini comparison warning, not GST, reconciliation, missing-field
or duplicate checks. The single-invoice Gemini button still requires Review.

Calls start at least 13 seconds apart (up to 5 per minute), successful cached
results need no new request, and HTTP 429 stops the queue. Failed invoices are
recorded alongside successes in `.invoice_app/gemini_batch_results.json`; they
are not silently skipped. The account limit shown by the user is 20 requests/day,
so 20 uncached invoices require that much remaining quota. There is no automatic
retry or promise of 20 successful responses. PDF response timeout is now 120 seconds.


## Reader 6.6: Gemini connection diagnostics

The title bar shows **Reader 6.6** so a replaced installation can be identified.
Google errors now show the actual provider reason and model used, with the key
redacted, instead of labelling every 404 as an unavailable model. If connection
still fails, double-click **Check_Gemini_API.bat**. It checks the model list using
the privately saved key, then makes one small text request only if that model
is listed. It uploads no invoice and does not change billing/model settings.
The pause keeps the result visible so it can be shared for diagnosis.
The Gemini PDF reader now defaults to **gemini-2.5-flash**, which appears in the
account model list supplied by the user. Set `GEMINI_INVOICE_MODEL` to that value
if an older override still exists. Keys remain private Windows environment
variables. Use **Read selected with Gemini**, then verify the result in Review
before preparing XML. The application still validates GST, quantities and
totals; this model change is not a live API accuracy benchmark. See
[Gemini setup](docs/GEMINI_SETUP.md).
When an item omits quantity, use the requested default **1**. If it also omits
its unit, use **Units**. These defaults are marked assumed/estimated in the
table and details and recorded in XML narration. Printed quantities, suffixes
and unit headings take priority; zero or invalid printed quantities are not
replaced. Numeric quantities still reconcile to the printed rate and amount.
Accepting the item's units also confirms its assumed quantity; Review can
correct a number. Headers without Qty and numeric/symbolic Units columns are
handled separately.

Explicit zero CGST/SGST/IGST totals, or a clear `GST: 0` / `No GST charged`
declaration, produce zero component rates when no item rates are printed. No
GST ledger entries are generated. Printed exempt/nil/LUT/export treatment is
preserved. Blank tax fields do not mean zero; positive printed amounts/rates
must reconcile and contradictory no-GST declarations remain blocked. Exports
with payment of IGST still require positive IGST. GSTR-1 classification is not
invented merely because tax is zero.
Click **Accept / change units** to inspect printed quantities and units. Tick
individual item rows and use **Accept checked items**, choose an invoice and use
**Accept this invoice**, or use **Accept all shown invoices** for the current
client filter. You can change the unit before accepting it. Acceptance removes
the estimated marker for those items and remembers their units; it does not
change numeric quantities, prices, GST, seller details or financial history.
Use Review to correct a numeric quantity. Missing/unmapped units remain unresolved.

The reader now tolerates newly recovered addresses that older versions left
blank, only when the source PDF bytes match and all transaction facts still
match. Saved transaction data, voucher IDs and confirmed import status remain
unchanged. Recovery is logged and shown in the details pane. Actual changes to
quantities, units, rates, GST, identities or existing addresses still require
review. The supplied eight CLIENT 17 PDFs reproduce and verify this upgrade case.

Shared labels cover supplier GSTIN, document IDs, references, transaction
categories and alternate GST total names. Paired form cells are processed as
label/value pairs while full item tables retain their column positions. Numeric
`Units` columns represent quantity when Qty is absent; percentage and footnote
rate evidence is retained. The four supplied 166–185 layouts now prepare all
20 XML vouchers with all 38 item rows. This batch was used to improve the code,
so it is a regression result rather than proof about unseen layouts.

The optional **Read selected with Gemini** button sends one selected PDF to
Google after confirmation, caches the result, and requires verification in
Review before XML. No API calls happen during normal scans. See
[Gemini setup](docs/GEMINI_SETUP.md) for private Windows key configuration,
model availability, quota handling and verification limits. No live API accuracy
test has been performed; the cloud environment does not have your key.
Colon-free form rows such as `Invoice number    DM/26-27/0126` are read as
label/value pairs without treating a multi-column table header as a form row.
Buyer/value rows remain separate from side-by-side party headers. GST rate
footnotes such as `0*` preserve the printed evidence while using numeric zero;
sentences describing intra-state supply are not interpreted as supply fields.

In demo mode, conflicting fictional buyer identities with the same printed name
receive separate output ledger names containing `[DEMO ...]`. Their printed
names and GSTINs remain in the invoice evidence. Ledger bindings are retained in
`.automation/demo_party_ledgers.json`; existing financial history and confirmed
masters are preserved. This rule does not bypass production master conflicts.
The supplied 126–145 batch generates 20 balanced XML vouchers with 46 item rows;
its omitted units remain editable estimates. Import `Required_Masters.xml`
successfully before `Sales_Vouchers.xml` into the matching test company.

The reader recognizes explicit supplier/vendor/exporter and customer/billing
roles, standalone or inline names, and separate party columns. A seller banner
can be recovered from a single business name and GSTIN before the billing party,
or a matching printed signatory. Ambiguous banners/signatories remain blocked.
When geometric PDF spacing loses key fields, ordered embedded text is compared
and used if it recovers more complete printed facts. Supplier names are read from
the document; there is no list of sample seller names or guessed spelling.

Reader 5 also accepts checked legacy demo reviews whose original layout name
is missing, using their seller, state, supply and item facts. The old paired-layout
configuration gate no longer rejects an otherwise valid review. Source identity,
GST, unit and total checks still run. To confirm several fictional PDFs at once,
click the invoice table, press **Ctrl+A**, then **Confirm test PDF**. Read the
confirmation and accept only when every selected PDF contains fictional data.
The declaration is bound to each complete source PDF's exact bytes.

The table shows the actual outstanding action: **Choose quantity unit**,
**Confirm test PDF**, **Choose invoice mode**, **Choose GST treatment**,
**Check seller details**, **Check GSTIN**, **Check amounts / GST**, or
**Verify scanned invoice**. Successful rows show XML prepared/import status.
The header reports how many invoices have XML prepared and counts each pending
action, rather than saying XML is prepared when every row is blocked. The first
outstanding row is selected automatically, exposing its detailed reason below.

**Auto-fill units** is enabled by default. Printed units in item cells,
quantity suffixes (such as `12 pcs`) and quantity/rate headings take priority.
For missing/ambiguous units the reader uses product and packaging keywords:
pens → Nos, loose rice → KG, box of pens → BOX, tools described as a set → SET.
Medicine strength such as `500 mg` is not treated as the unit sold. A printed
quantity of `150 mg` does use MG. No quantity, rate or amount is converted.

The table shows quantity and unit, marking automatic suggestions **estimated**.
Click **Check / change units** for a prefilled list of all items and the reason
for each suggestion. Save a correction to regenerate an unimported voucher with
the same identity. Your correction is remembered for the same supplier, product,
HSN and invoice mode. Already estimated documents keep their saved choices.
Confirmed imported vouchers require correction in Tally. Corrections do not
approve other tax/OCR warnings or overwrite confirmed stock masters.

Without a reliable clue, whole quantities receive a low-confidence Nos estimate;
fractional quantities receive a generic Qty unit (OTH), visibly marked for checking.
These are estimates rather than knowledge of the actual selling unit. Untick
**Auto-fill units** to require manual choice for missing units. Unknown explicit
units remain unresolved until configured. Older reviews and import history stay
intact; unit choices and learned preferences are stored locally in `.invoice_app`.

Unit aliases and GST UQC references were checked against the public
[India Compliance unit map](https://github.com/resilient-tech/india-compliance/blob/develop/india_compliance/gst_india/constants/__init__.py)
and [ERPNext unit definitions](https://github.com/frappe/erpnext/blob/develop/erpnext/setup/setup_wizard/data/uom_data.json).
Official GST/Tally pages were inaccessible from the current environment.
Custom mg, microgram and packaging units use OTH rather than invented GST codes.

The original supplied 61 distinct PDFs contain 80 invoices. All seller names were read;
all 80 vouchers were checked in isolated audit runs after explicit test-data,
unit and exempt-treatment choices. These checks verify accounting XML, not a
live Tally import or every possible future PDF layout. CLIENT 16's SI-0029 style
was shown only in a screenshot and requires its source PDFs for verification.

Reader 5.1 reads per-item `GST rate: 18%` continuation lines below table rows,
including reordered columns and separate supplier/buyer headings. `Supply type:
INTRA/INTER` supplies the state split rather than becoming a tax classification.
City/state place-of-supply values and `INR (Indian Rupees)` are normalized.
Zero omitted GST components are derived only when every recognized item has
an explicit zero component rate. Missing per-item rates and conflicting rates
remain blocked. Explicit paired fictional-testing and fictional-identity notices
are recognized automatically; a generic word such as “sample” is insufficient.

The eight uploaded `Sales_Invoice_46` through `53` PDFs now generate eight
vouchers with all 20 printed item rows and their distinct GST rates, with no
seller re-entry or fictional-data declaration. Their printed PCS/BOX units stay
unchanged. Old unbaselined reviews with empty item lists can recover newly read
rows; nonempty manual item corrections remain preserved. The screenshot's
SI-0026–0045 documents were not uploaded, so those exact files are not verified.

## Desktop workflow: inspection, corrections and seller grouping

On Windows, double-click `Open_Invoice_App.bat` alongside `main.py`. Select the
parent folder containing the client folders. Leave **Watch for new PDFs** enabled
to process stable file changes automatically. The **Test invoices (fictional data)** checkbox selects invoice mode. Leave it
checked for fictional PDFs and use **Confirm test PDF** when their fictional
marker is missing. Uncheck it for real business invoices and re-read the PDFs. Real invoices
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

### Missing units and PDFs containing multiple invoices

The supplied `Sales_Invoice_11` through `Sales_Invoice_25` layouts are read using
ordered embedded text, avoiding word breaks introduced by PDF layout spacing.
Seller/buyer, GSTIN, date, invoice number, HSN, quantity, rates and totals are
extracted. Their printed `Unit: Nos / Kg (as applicable)` leaves the actual unit
unspecified. Reader 5 estimates units from item descriptions and shows them
beside each quantity. Use **Check / change units** to correct them, or turn off
**Auto-fill units** for the manual workflow. `SYNTHETIC TEST DATA - NOT A VALID TAX DOCUMENT OR GST REGISTRATION`
is recognized as an explicit fictional marker.

The desktop reader expands the supplied twenty-page `GSTR1_Test_Invoices.pdf`
into twenty separate invoice rows with original PDF/page references. Splitting
requires every page to contain a complete recognized invoice header with a
unique seller/number/date. Continuations, covers, repeated headers or unsupported
mixed documents are not blindly split. Ordinary multi-page invoices remain one
source. Generated page copies are retained under `.invoice_app/source_pages/`;
the original PDF is unchanged. Review and layout saves verify both the page and
the original PDF. Keep this directory with the company's other retained data.
The desktop header counts original PDFs separately from invoice rows.

A title such as “GSTR-1 Test Page” does not by itself authorize fictional GSTIN
substitutions. If this entire PDF is fictional test data, select one of its rows
and click **Confirm test PDF** once. The confirmation applies only to those exact
source bytes and all their invoice pages. Real documents must use real-invoice
mode; a test-confirmed document is blocked in that mode. The first five invoices
in this bundle omit units: Reader 5 estimates them and makes them editable. The other
pages retain their printed Nos, Units, Vials, Packs, Tubes or Liters. Supported
LUT invoices use zero payable GST even when a statutory product rate is printed;
source tax totals must still reconcile.

Fictional suppliers may share a made-up GSTIN. A different fictional supplier
name gets a separate retained demo workspace when that GSTIN already belongs to
another demo supplier. Existing company IDs, PDF routing and import history are
preserved. Real GSTIN identities continue to require consistent supplier names.

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
remain retained. Existing OCR approvals remain complete overrides. Older reviews without a
baseline retain every nonblank correction and tax decision; empty identity
fields can recover from newly readable native text. If one of those old overrides still blocks
a readable PDF, select its row(s) and use **Re-read selected PDFs**. This archives
only those saved reviews and extraction caches under `.invoice_app/review_backups/`
before re-reading. Company configurations, databases, import confirmations and
original PDFs are not reset or deleted.

Use the **Client folder** dropdown to inspect just CLIENT 8 or CLIENT 9 rather
than the older sample folders. **All clients** remains the default. Desktop XML
batches are separated by source client folder, even when two folders share the
same seller. CLIENT 14's ten invoices and CLIENT 15's fifteen invoices therefore
produce separate ten- and fifteen-voucher XML files. Scanning just CLIENT 15
exports only its current source invoices; scanning All clients prepares each
folder's batch separately. Company IDs, duplicate checks, pending history and
import confirmations remain shared for the same seller and are not reset.
The review form offers dropdown choices for GST classification, registration,
supply and export mode. These choices correct a particular invoice; they do not
teach the reader a new layout. Exports cannot be edited into domestic sales or
changed between LUT and IGST payment modes. Explicit exports generate accounting
vouchers, described below.

Each distinct seller GSTIN gets a retained independent company under
`.invoice_app/companies/`, with each source folder's XML under that company's
`imports/by_client/<folder-name>_<id>/` directory. Use **Open client XML folder**
to locate the selected row's folder-specific `Masters.xml`, `Sales_Vouchers.xml`
and `manifest.json`. Its manifest records `source_client` and `export_scope`.
The displayed voucher count is for that source folder's batch. The old top-level
`imports` location is mirrored only when a single source folder contains the
entire eligible batch; an older mixed company XML is withdrawn on the next scan.
Keep any unrelated combined invoice PDF out of a client folder: a PDF containing
twenty invoices contributes twenty rows in addition to that folder's other PDFs. Original client folders,
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
`export_scope` (copy it from a desktop folder-specific manifest; omit it for the
legacy top-level output), `tally_result_reference` (the actual log/report reference), `masters` and
`vouchers`. Master entries are `{"master": <exact planned master>, "status":
"imported"}`. Voucher entries are `{"invoice_key": <manifest key>, "status":
"imported"}`. Statuses can also be `rejected` or `pending`. Confirm dependent
masters first or together with sales; otherwise sales confirmation is refused.
Rejected invoices remain visible in history and are not silently resubmitted.
Do not report success from XML generation alone. A folder-specific confirmation
updates the retained company history. Other folders keep their pending invoices;
any other export containing a handled invoice is invalidated to prevent importing
that same company invoice from a second batch.

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

## Reader 5.3: export and exempt XML from generic tables

The primary workflow is **Scan and generate XML**. New stable PDFs are processed
when **Watch for new PDFs** is enabled. Excel inspection no longer runs as the
default scan output. Generic item tables now use printed export/LUT/IGST and
exempt/nil-rated treatment before splitting each item's GST:

- Domestic intra-state: CGST and SGST from each printed combined item rate.
- Domestic inter-state and export with payment: IGST from each printed item rate.
- Explicit LUT without payment: zero payable GST, retaining printed product rates.
- Explicit exempt/nil-rated: zero payable GST; exemption wording does not become
  a second supply field.

Printed overseas GSTIN placeholders, country and outside-India place of supply
are read without requiring an Indian buyer state. Missing or conflicting payment
mode, tax totals, identities or confirmed master data still produce a specific
review error. The generated accounting export vouchers need GST reporting
configuration checked in Tally, as described above.

Regression coverage includes a batch of 16 invoices: the eight uploaded
Sales_Invoice_46 through 53 PDFs plus eight generated LUT/IGST/exempt/nil-rated
variants. The batch generates 16 balanced vouchers and a repeat scan retains
voucher identities. This does not establish a live Tally import or verify PDFs
which have not been supplied.

## Reader 5.4: the twenty uploaded invoices and missing buyer ledgers

All uploaded Sales_Invoice_66 through 85 PDFs are covered together, including
Singapore/Canada exports. Printed country names and two-letter identifiers use a
bundled ISO 3166 lookup, preserving the earlier UK/UAE/USA aliases. It requires
no extra package or network connection. Unregistered/Consumer buyers serialize
as Tally's `Unregistered/Consumer` GST registration label in both ledgers and
vouchers; accounting/source registration stays unchanged.

The twenty-source regression verifies 20 vouchers, all 20 buyer ledger masters,
matching invoice gross debits, individual CGST/SGST/IGST credits, balanced
allocations and repeat-scan identities. Totals: taxable INR 401,911.00, CGST
14,360.25, SGST 14,360.25, IGST 33,493.74, gross INR 464,125.24. These are XML
checks; the application cannot observe the user's Tally import result directly.

Import Masters.xml before Sales_Vouchers.xml from the same client output folder.
The additional Required_Masters.xml contains every dependency needed by that
batch, including ones previously confirmed. For Tally's “Referenced master is
missing” exception, import this recovery file with duplicate masters ignored,
check that master creation has no errors, then retry the rejected vouchers.
These master records use Create. This recovery file is recorded and hashed in
manifest.json but is separate from the normal import_order.

Screenshots containing SI-0026 through SI-0045 refer to an earlier batch; these
uploads contain SI-0066 through SI-0085. Select the matching client in the app
and open its XML folder to avoid importing another batch's master/voucher files.

## Reader 5.5: crashes, source names and visible units

Processing is guarded by an OS lock (flock on Linux, msvcrt on Windows). The OS
releases the guard after a process dies. Markers owned by this new protocol are
recovered on the next run. The old empty run.lock directory has no process
identity, so it is not automatically removed. Close other invoice-app windows,
click **Recover processing lock**, and confirm once to archive that old marker.
An active new-protocol guard prevents recovery. Source copies/config/reviews
are staged under the same company lock, preventing a busy second app from
modifying a company's completed data. A blocked scan cannot open its previous
XML folder through the app.

Seller banner matching tolerates punctuation, Pvt/Ltd spelling, Authorized
Signatory suffixes, and non-business 'For testing only' footers. Genuine
conflicts retain the printed name as a visible **Candidate** while requiring
identity review. A uniquely read header name can be displayed even if its GSTIN
is missing. Previously verified supplier identities may supply a missing name
when the GSTIN matches (real invoices), or an exact prior PDF routing/proven
candidate supports that identity (demo invoices). Buyer names are never used as
seller fallbacks.

The generic table recognizes additional description, HSN/SAC, unit, rate and
net-value headings. Quantity/unit columns remain populated for recognized items;
**Items not extracted** identifies table extraction failure. Equivalent printed
Unregistered/Consumer/N/A buyer labels do not create false GSTIN conflicts;
different actual GSTINs still require review.

For exports with payment, each source's charged IGST posts to Output IGST. LUT
without payment retains zero payable GST and belongs in the GSTR-1 export
section. An accounting XML check cannot certify Tally's GST-return classification.
The latest Tally register is short by 18,031.34: SI-0079 (5,303.00) and SI-0081
(12,728.34). The twenty supplied 66–85 PDFs remain regression-covered. CLIENT 21
source PDFs have not been supplied; its exact masthead/item layout is unverified.

## Reader 6: new structural logic

See [EXTRACTION_LOGIC.md](docs/EXTRACTION_LOGIC.md) for the complete pipeline:
separate scalar fields from their neighboring metadata, preserve party columns,
recognize invoice headings, interpret semantic table headers, and validate
printed facts before XML generation. The 106–125 uploaded batch previously
produced 0 XML; it now extracts 20 invoices and 39 items. Five prepare XML automatically; fifteen need item GST rates under the requested default.

**Summary GST accounting** is off by default, following your choice to require item-rate review for inventory XML. When every item's GST rate is
omitted but invoice-level CGST/SGST/IGST amounts are printed, it uses the printed
invoice amounts in an accounting voucher without stock movement. The status and
narration state this explicitly. Leave the option off when inventory posting is
required; missing item rates then need review. Printed exemption/LUT zero GST
is handled separately. Units omitted by the PDF stay visibly estimated.

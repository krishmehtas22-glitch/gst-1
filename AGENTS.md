# Buyer ledger role guard — latest user authorization, 17 October 2026

The user accepts the proposed buyer-ledger name/group check. Validate imported
buyer assignments in Python, regardless of AI confidence/GSTIN. Reserved system
names and non-party/unverified parent groups cannot be buyer references. Hold
new client XML on role conflicts, retaining previous output and source facts.
Also reject occupied system ledger names whose existing group conflicts with
its generated accounting role. Expose explicit local buyer-ledger review to
select a verified party or use current invoice-buyer creation; no AI calls.
Do not alter existing Tally masters, currency, quantities, unit/UQC, stock GST
matching (a separate issue), duplicate-warning policy, GUIDs or Import ALL.
Keep backups and historical lock hashes; record this narrow exception separately.
No live AI requests or Tally writes during tests.

# Optional duplicate warning — latest user request, 17 October 2026

The user wants a warning only, comparing invoice number and invoice date, with
permission to keep/upload/process both documents. Scope comparisons to one client
workspace; seller/GSTIN/amount/source digest must not decide business duplicates.
Detect only known analysed/manual fields; no startup/upload/refresh AI or OCR.
Show a visible review warning and include it in the report/narration, without
blocking uploads/XML/import, removing files, changing GUIDs or auto-merging.
Clear stale warnings when number/date or the set of invoices changes. Preserve
currency and quantity locks, unit/UQC, master assignment, Import ALL and budgets.
Record the narrow UI/export warning additions separately and back up prior code.
No live AI/Tally writes in tests. This supersedes A01's earlier proposed block.

# Currency lock and exact quantity precision — latest user request, 17 October 2026

Lock the foreign-currency release at 7a52bc33fe7e7972e2425a5f23139f1e493c1fd6.
The user authorizes only exact fractional quantities such as 2.4877 KG in XML,
adequate generated unit precision, and batch-wide validation of reused unit
precision. Preserve quantities without rounding/scaling, UQC/formal names,
monetary values/currency conversion and Import ALL transport/protocol. Do not
silently alter an existing Tally master. Insufficient existing precision must
request correction in Tally; unsupported >6 significant decimal places must
hold XML rather than round. Back up code and record new exceptions separately;
retain original lock hashes and all customer data. No live AI/Tally writes.

# Foreign-currency invoice conversion — latest user request, 17 October 2026

Authorize only currency identification, printed exchange-rate extraction, explicit
per-invoice manual currency/rate entry, and deterministic INR conversion before
review XML and refund display. AI extracts source facts, Python uses Decimal.
Keep original source/caches/amounts, stable GUIDs, quantities, GST percentages,
unit/UQC, imported-master method, Import ALL dispatch and explicit AI budgets.
Never guess ambiguous currency/rate or exchange direction. Missing/invalid rates
hold new XML, retaining previous output. Rate entry is INR per one source unit;
manual overrides are client/source/fact scoped. Preserve old locks and record
new file-hash exceptions, with Backups/Before_Foreign_Currency.zip. No live AI or
Tally writes during tests. Other audit findings remain separate work.

# Apply imported Tally masters — latest user request, 17 October 2026

The user now authorizes AI to assign imported Tally party/inventory/unit masters
to uploaded invoices, falling back to the existing creation method for unmatched
entries. This supersedes the earlier snapshot-review-only restriction narrowly.
Bind snapshots explicitly to client and company; match only on explicit processing,
retain the existing shared AI budget, caches and manual corrections. Preserve
invoice source values, GST, quantities, rates, GUIDs and document conversion.
Allow optional Groq matching context/sidecar, an AI-first matching hook and a
post-generation XML reference adapter. Reused masters must not be recreated or
altered; validate company-bound external dependencies before import. This allows
only prerequisite/company checks in tally_import.py, preserving dispatch order,
Import ALL button, unit creation protocol, receipts and retry behavior. Record
changed-file exceptions separately; retain all original lock fingerprints and
back up prior code. No live AI requests or Tally writes for automated checks.

# Export country and refund-review addition — 17 October 2026

The user explicitly requests export country in Tally and a refund column, and
chooses Show IGST estimate + review status. Authorize a narrow export-country
hook in Common_Rules/tally_review_export.py plus a helper, and UI/local refund
review tracking. Export country must be valid before new export XML is generated;
missing/conflicting country must not be fabricated. Reuse known Tally country
fields; do not claim GST-return nature mapping is verified. Preserve financial
allocations, GUIDs, invoice values, domestic XML, AI prompts, import transport,
unit/UQC and PDF/JPEG/PNG processing. Preserve the original fingerprints; record
this one-file export-metadata exception separately with its baseline hash and
verify unchanged domestic XML against the archived exporter. Refund is an
unverified invoice-IGST estimate, not confirmed entitlement or tax-payment proof.
Keep manual claim/review data separate from invoice amounts/XML. LUT input-ITC
refund is not calculated from a sales invoice. Retain existing files/backups.

# Implement approved BillSync design — latest request, 16 October 2026

The user now explicitly says to make the planned app. Implement the locked
professional upload design in the presentation layer: larger drop zone, complete
status cards, adjacent New client control, side-by-side processing/Tally toolbar,
full-width table and on-demand inherited review editor. Preserve all controls
through toolbar/menu/Settings and truthful status. Back up current UI. Preserve
Document_Upload.py, Tally snapshot modules, Invoice_Desktop.py and Common_Rules
byte-for-byte. No changes to AI costs/consent, input processing, PDF/JPEG/PNG,
XML, units, masters, import logic or hidden accounting default. Provide updated
source-only installer (prior EXE download was blocked) and tested Windows build.
Record implementation separately without replacing original design fingerprints.

# Approved design lock and document format audit — 16 October 2026

The user approved and locked the latest professional upload design preview
(reference 8a7d33f, recorded in Automation/APPROVED_UI_DESIGN_LOCK.json). This locks
the design reference; the preview has not been applied to runtime UI. Do not
claim otherwise or redesign it without later explicit authorization.
The user authorizes checking PDF/JPG/JPEG support and necessary format-specific
fixes only, preserving current PNG processing. Prefer actual upload/OCR/input
verification. No paid AI requests or live Tally imports for this audit. Existing
AI prompts, XML/accounting/master/unit handling and Import ALL remain locked.

# Authorized UI refinement and incoming Tally snapshot — 16 October 2026

The latest user explicitly requests smaller fonts, slightly rounded visible action
boxes, an improved client section, and Import masters from Tally including units.
Implement incoming ledgers, stock items and units as a separate, read-only local
snapshot with explicit source-company selection. Do not feed these snapshots into
current extraction/master/unit generation yet. Preserve Invoice_Desktop.py and
all Common_Rules bytes, inherited AI/XML/Import ALL methods, accounting defaults
and no automatic AI calls. Keep original backup and add a code-only UI backup.
Build/test the Windows artifact using the existing read-only workflow.

# Invoice batch contract

## Authorized BillSync presentation / upload / EXE work — 16 October 2026

The user explicitly approved the supplied UI concepts and requested an EXE with
only those changes, unchanged processing/output and a backup. Add a separate
BillSync_UI subclass over the original InvoiceApp and a local Document_Upload
adapter for PDF/PNG/JPEG. Preserve Invoice_Desktop.py and every Common_Rules file
byte-for-byte, including the complete Import ALL method/dispatch and source
revision. Inherit AI/review/XML/import actions without replacements. Uploads and
listing send no AI/XML/Tally requests. Preserve PDF bytes, original images,
duplicate detection, client isolation, caches/history and all financial values.
Hide Summary GST accounting without forcing a new default/mode. Keep technical
storage under Settings, no Advanced button. Keep the original source launcher,
provide a code backup and build the EXE on Windows with an offline frozen smoke
check. Packaging/new UI dependencies and the existing read-only artifact workflow
may change; do not expand workflow permissions or publish releases without
specific authorization. Earlier freezes remain for all processing behavior.

## Final freeze reaffirmed — latest user instruction, 16 October 2026

"NOW LOCK IT NO CHANGES SHOULD BE MADE."

Freeze the entire current implementation at commit
`6541b8531832b1fc1a3ebec5894e8721be5754cd`, including the completed plain-name
patch and both already-published desktop variants. Do not make further runtime,
UI, AI, XML, unit/UQC, voucher-numbering, import, packaging or dependency changes
without a later explicit request authorizing the specific change. Earlier
completed change permissions do not authorize continued modifications.
The proposed app check/automatic configuration of Tally voucher numbering was
only discussed and is NOT authorized or implemented. Do not change Tally settings.
Preserve existing lock fingerprints, recorded exceptions and customer data.
This reaffirmation changes maintenance records only; no runtime update or user
download is required. Older sections below are historical constraints, not open
work items or permission to resume previously completed changes.

## Authorized name-only change — latest user instruction, 16 October 2026

The user explicitly requested removal of generated `[batch ...]` suffixes from
party/stock names while keeping the correct output otherwise. This narrowly
allows `tally_review_export.py` name selection and a `plain_master_names.py`
helper. Update master names and all corresponding voucher/report references
together. Use printed names for ordinary cases; incompatible same-name GSTIN,
unit, HSN or tax variants must remain distinct using readable source details,
never batch hashes. Preserve extracted fields, quantities, rates, amounts, GST,
dates, voucher GUIDs, actual inventory batch/godown allocations, unit/UQC XML and
Import ALL transport/button. Do not rename existing Tally masters automatically
or alter old exports/caches/history. Preserve both desktop versions/UI unchanged.
Record this exception separately in WORKING_READER_LOCK.json; do not replace the
original stable fingerprints. All other parts remain frozen.

## Freeze working reader — latest user instruction, 16 October 2026

The user selected **Lock current version** because the output is correct. The
confirmed screenshot shows Reader 7.29 (`bb29b1ef057cb14def34fb4377c435bad02d6e7c`).
Preserve that release, including desktop controls, explicit AI consent, Groq
prompts/extraction, caches, manual review/save, unit/UQC handling, all XML output,
client isolation and Tally import. Do not change these for cleanup, new features,
dependency upgrades or an inferred launch request. Only a later explicit user
request authorizing the affected change may override this freeze.

`Automation/WORKING_READER_LOCK.json` records the source fingerprints. The already
published Reader 7.30 one-PDF UI variant is also recorded; its backend matches
7.29. Preserve the current checkout and both release artifacts without forcing
the user to upgrade or rolling back code. Do not silently regenerate fingerprints
to hide changes. The earlier Import ALL lock still applies independently.
Documentation/lock records may be maintained without changing runtime behavior.
This is a maintenance contract, not an OS-level lock or a future-accuracy claim.

## Explicit single-PDF action — user correction, 16 October 2026

Expose Analyse ONE PDF with Groq separately from selected-PDF/client batches.
Use the focused row only when it is selected; otherwise require exactly one
selected row. Never promote this action to all selected rows or the client.
Confirm the source filename and a one-attempt cap before dispatch. Preserve the
existing frozen-path/shared budget and cached/approved result reuse. Status must
distinguish this action's new requests from complete-client XML voucher counts.
Do not change Groq prompts/extraction, XML writers, UQC or the locked Import ALL.

## Desktop review controls — user instruction, 16 October 2026

The desktop exposes Groq actions only. Remove Gemini, OpenRouter and GitHub
controls, provider picker, Accept/change units, Recover processing lock and
Confirm test PDF buttons. Keep their shared/backend code and extraction behavior
unchanged. Double-click opens the existing invoice editor, including editable
units/items. Save changes to XML persists the human review and regenerates only
that client's complete XML locally, with no new AI request; preserve other clients
and all AI caches. Test-data confirmation for a manual edit lives in this save
action when Test invoices is enabled, with explicit wording in the editor.
Keep startup/list-only behavior and the locked Import ALL/UQC/XML writers.

## Explicit AI control — user correction, 16 October 2026

Startup, folder watching, refresh, choosing folders/clients and changing settings
must only list PDF filenames/metadata. No PDF/OCR analysis, API calls or XML
generation may run automatically. Only an explicit AI button followed by the
user's confirmation can analyse selected PDFs or a chosen client batch. Support
one file or multiple selected files (including 100). Freeze confirmed source paths
and cap fresh attempts across all providers to that confirmed PDF count. New files
arriving during a run must stay queued. Reuse successful caches/approvals. Stop
must prevent further calls. Manual correction/revalidation may use Python locally
without AI. This overrides earlier automatic AI-on-scan/watch instructions below.
Keep the working Import ALL/UQC/XML transport lock unchanged.

## Locked working Import ALL baseline — user instruction, 14 October 2026

Later explicit authorization: the user supplied the Tally UQC dropdown and
requested expansion of unit mappings/aliases only, while preserving the button.
`unit_catalog.py` may receive this expansion and UQC classification aliases.
Preserve custom printed symbols while assigning their UQC. Keep existing unit
normalization in `unit_inference.py` unchanged. The desktop import method,
`tally_import.py`, `tally_units.py`,
company routing, HTTP/XML creation protocol and dispatch order remain locked.
Keep the original fingerprints and record this authorization separately.

The user confirmed that the current Import ALL button is error-free and explicitly
requested that this part be locked. Baseline commit:
`f7fae39b29e0f992ef471a9adca44904a8acadc4`.

- Do not change `Invoice_Desktop.py`'s `import_tally` method, the import-button
  command, its company selection, dispatch, sequence or result handling.
- Do not change `Common_Rules/tally_import.py`, `tally_units.py`, or
  `unit_catalog.py`. Preserve current UQC assignments, plain formal names,
  existing-unit reuse, destination routing and Units → Masters → Vouchers order.
- Do not bypass this lock through changes in callers, generated XML or new
  transport helpers. Unrelated tasks must preserve this working behavior.
- Only an explicit later user instruction authorizing changes to this locked
  part can override the lock. General cleanup, refactoring, UI redesign or
  suggestions are not authorization to alter it.
- `Automation/IMPORT_ALL_LOCK.json` records the baseline fingerprints. Verify
  them before/after unrelated work; do not silently regenerate them to conceal
  changes. This lock takes precedence over older implementation recommendations
  below. It is a maintenance rule, not filesystem access control.

- For every current and future unit, keep the selling symbol, formal description,
  and UQC code in their own fields. The formal description must not equal the
  symbol or short/full UQC code (ignoring case/extra spaces). Repair only the
  description via shared unit_formal_name in generation and legacy transport.
  Preserve valid UQC codes, stock BASEUNITS, quantity/rate values and vouchers.
  This naming rule is not proof that a pending Tally exception is repaired.
  Use plain natural descriptions: Packs has formal name Pack and UQC PAC-PACKS;
  never append '(selling unit)'. Distinguish descriptions from the UQC's display
  label as well as its short/full code. Assign the catalog UQC to known units
  with absent/generic codes; retain explicit custom codes, using OTH-OTHERS for
  unmapped custom units. Apply this to legacy transport and future generation.

The user explicitly requires complete XML batches for review in Tally.

- The user authorized a separate coordinate-aware reading prototype and
  comparison before replacing the existing reading approach. Reading_V2 and
  Read_Invoice_V2.py must remain isolated from the active desktop/provider/XML
  code. Evaluation must be read-only with respect to source PDFs, existing
  caches, financial history, approvals, UQC policy and Import ALL. Report source
  coordinates, explicit legacy fallback, conflicts and validation. Benchmark
  completion/agreement is not accuracy. Do not promote the prototype until
  independently reviewed layout coverage and quality support the change.

- The Goods description/HSN/Qty/UOM/Rate/Taxable/GST %/GST amount family must
  support both vertical PDF token streams and positioned rows. Read printed
  invoice identifiers/dates, explicit buyer panels, corroborated seller names,
  totals and supply declarations. Never read SUPPLY DETAILS as a buyer or a
  seller address number as the invoice number. Recover missing saved-AI identity
  from verified source evidence without overwriting valid AI/human values.
  Reading fixes must preserve the locked Import ALL method/transport and reuse
  saved AI data without new API calls. Keep parser revision dependencies and
  Windows bundled sources aligned. Complete XML output is not live import proof.

- All future Cerebras, Gemini, Groq, or other AI batch integrations must use the complete
  batch workflow (`read_with_fallback`, then `process_sources` with the saved
  client batch policy). Never let API quota expiry discard successful reads.
  Later explicit user instruction (16 October 2026): normal desktop Scan and
  watched-folder processing must be AI first. Python prepares source text/OCR,
  AI extracts invoice fields, then Python converts them through the existing XML
  writers. For this desktop flow, complete the AI stage before invoking the XML
  writer; durable AI caches replace the older starting/in-progress XML checkpoints.
  Retain approved source reviews without another AI call. Clearly report local
  fallback when AI cannot finish. This does not authorize changing Import ALL or
  promoting the separate V3 prototype/teaching pipeline into production.
- Switch to other configured active providers (GitHub Models, Groq, Gemini, OpenRouter free-only) for remaining sources; use local
  Python/OCR when configured APIs cannot finish. Do not enable billing, add
  paid providers, or request secrets in chat.
- Cerebras has been replaced in the active user workflow. Retain old cache
  support, but do not use it in automatic fallback or expose new Cerebras actions.
  GitHub Models uses the explicitly configured GITHUB_MODELS_TOKEN only; never
  reuse Git/GitHub repository authentication or another provider's credential.
- Produce one XML voucher element per scanned invoice, including incomplete
  ones. Keep uncertainties in narration and Batch_Report.json rather than
  blocking XML for GSTIN, seller, unit/master, or reconciliation issues.
- Use accounting vouchers when inventory cannot be reconstructed. Preserve
  printed GST components and amounts; record any explicit unresolved values,
  placeholders or difference ledger postings. Do not claim fabricated fields
  are extracted facts or AI batch acceptance is individual human approval.
- AI may infer missing selling units from product/packaging context. Retain
  the reason, mark the unit assumed, and include it in narration/report.
  Printed units and human corrections outrank assumptions. Qty is a heading,
  not a selling unit. Never scale quantities/rates or confuse medicine strength
  with sold weight/volume. Retain explicit custom printed units.
- Keep separate clients and sellers isolated. Each client must have one stable current XML folder containing
  Units.xml, Masters.xml and Sales_Vouchers.xml with an exact input/output count.
  Keep one managed previous-output backup, without creating timestamp/seller
  directories on each checkpoint. Preserve historical exports. Open client XML
  folder must show the complete current folder. Route genuinely distinct sellers
  to explicitly selected companies in memory, preserving all voucher fields.
- Export unit definitions separately before any stock masters. Use the unit
  catalog's formal names/UQC labels and sufficient quantity decimal precision.
  Check stock BASEUNITS against Units.xml and inventory names/quantity suffixes
  against their stock masters. Do not round quantities/rates to currency cents.
- Inventory invoices must use LEDGERENTRIES.LIST for buyer/tax entries, with
  sales credits inside item ACCOUNTINGALLOCATIONS.LIST and matching godown
  BATCHALLOCATIONS.LIST. Accounting vouchers use ALLLEDGERENTRIES.LIST.
  Verify the serialized view, party identity and exact debit/credit balance
  before publishing XML; arithmetic alone cannot validate the Tally structure.
- Apply shared `ai_invoice_rules.RULES` to every provider prompt. Resolve Buyer/
  Bill To separately from Supplier/Seller, Ship To, bank and signatory. Preserve
  the buyer name and exact buyer ledger in the report. Every referenced buyer,
  sales, tax and difference ledger must have a matching exported master.
- Gemini, GitHub Models and OpenRouter must use Groq's shared prepare_invoice_payload
  text/OCR recipe. Preserve Groq's validated prompt/input behavior; adapt only
  the provider API envelope/output token cap. Do not force API rereads of saved
  successful results or change working seller/quantity/date/Tally logic.
- Preserve prior financial/import history and manual corrections. Keep stable
  voucher GUIDs and do not force-release another live process's OS lock.
- Date repairs must only change date/audit fields. Normalize actual calendar
  dates to YYYY-MM-DD and write Tally YYYYMMDD. Recover missing AI dates only
  from verified source invoice-date evidence, not due dates or today's date.
  Keep working seller, buyer, quantity, rate, unit and stock logic unchanged.
- XML generation is not proof of successful Tally import or correct GSTR-1.
  Test partial-provider exhaustion, all-local fallback, master-unit variants,
  missing fields, zero GST, updated output paths, and unchanged retained history.

- A verified successful selected AI cache is terminal for batch scheduling: do not
  reread it with another provider. Recover cached successes after bookkeeping
  errors. Stop AI processing cancels pending/paced requests and fallback, retains
  completed reads and generates XML using Python for remaining invoices. An
  in-flight request may finish; never discard it or change the Tally writer.

- Direct Tally import must send existing current XML in dependency order through
  localhost only, after explicit destination-company selection. Do not regenerate
  output, change financial fields/GUIDs, or infer import success from file creation.
  Preserve generated files and all voucher fields; set SVCURRENTCOMPANY only in
  the transport copy. Combine existing sets only for case/space-equivalent seller
  names with matching GSTINs, deduplicating compatible prerequisite masters.
  A missing GSTIN may share a routing group only when the normalized seller name
  has exactly one known GSTIN in that client batch; never fill missing invoice
  GSTIN fields or merge distinct known GSTINs. Report
  actual server counters and retain rejections. Import ALL must attempt later XML
  stages once after definite Tally rejections; stop on unknown responses or
  connection failures, and never retry an
  ambiguous timed-out import automatically. Keep import receipts separate from
  financial/import history; do not mark all invoices imported from aggregate counts.

- Letter case alone must not exclude part of a seller batch from direct import.
  Discover matching sets only from the selected current run manifest, display
  their total invoice count, and retain a selected-set-only option for importing
  the remaining set after a partial earlier import. Never combine different
  GSTINs/clients, alter existing vouchers, or silently resend already imported data.

- The direct-import default must cover EVERY XML folder listed in the current
  selected client run report, not just the selected invoice's group folder.
  Show the total invoice count. Case/space-equivalent names with matching GSTINs
  share one destination; distinct sellers have explicit destination selections.
  Validate that all manifest folders are covered and inside the current run.
  Preserve selected-set-only import as an explicit option for completing earlier
  partial imports. This rule applies to all current and future AI/Python output.

- Windows packaging must preserve working financial/extraction/output behavior.
  Frozen data roots must use the executable folder or the user's chosen folder,
  never __file__ inside a bundled/temporary directory. Bundle parser-revision
  source data, lazy provider modules, OCR models and native DLLs. Never package
  invoice/client data, caches or API secrets. A Windows EXE requires a Windows
  build and frozen smoke test; do not claim a Linux build is a Windows executable.

- Large AI batches must share one conservative fresh-attempt budget across all
  providers, defaulting to the number of source invoices. Verified saved successes
  (including orphaned provider caches) consume no new attempts and are terminal.
  Do not multiply a 50-source batch into 150 new attempts. Invalid/failed reads
  count conservatively toward the budget; local Python prepares remaining XML.
  Use run_batch_to_xml to checkpoint starting output, the first/every tenth saved
  AI success, and final output even after Stop or worker/report errors. Reporting
  failures must not block export. Distinguish skipped queue entries from actual
  new attempts and show success/failure reasons. Preserve all existing invoice,
  unit, buyer, date, XML and Tally import code. EXEs must be rebuilt for fixes.

- OpenRouter is supported only with OPENROUTER_API_KEY and free-only models:
  openrouter/free or explicit :free IDs. Reject paid model IDs and alternate
  model/plugin routing before requests; cap provider prompt/completion prices
  at zero. Never enable billing or request key values in chat. Apply the same
  Groq text/OCR prompt, normalizer, cache proof, attempt budget, Stop/checkpoint
  workflow and unchanged Tally output to OpenRouter and future providers.

- Incomplete AI results must not erase verified local invoice numbers or buyer
  identity. Overlay only missing fields before manual reviews; preserve all valid
  AI/human values, sellers/items/units/amounts, source caches and stable GUID rules.
  Retain identity-recovery evidence. Never invent a missing date/buyer from a file
  name, today's date, seller identity or another invoice. Diagnose Tally missing
  units using the actual current XML and import receipts, not screenshot guesses.

- Direct unit import must query units in the explicitly selected Tally company,
  coalesce repeated definitions by symbol using sufficient maximum precision,
  and reuse compatible existing units without overwriting them. Preserve selling
  symbols, stock BASEUNITS, quantity/rate values and saved XML. Disambiguate only
  colliding formal/original names in the transport copy for new symbols. Never
  hide a DUPLICATE ORIGINAL NAME error. For Import ALL, retain that reported
  rejection and attempt remaining masters/vouchers once for Tally exception
  review; do not claim acceptance. Preserve real server counters and stop on
  ambiguous connection/response failures or unsafe local precision conflicts.

- Unit creation must follow the official Simple Unit creation sample at
  https://help.tallysolutions.com/sample-xml/: UNIT Action="Create" without
  NAME/RESERVEDNAME attributes; NAME is the child selling-symbol field. The official documentation confirms ORIGINALNAME carries the formal description (e.g. NAME=KG, ORIGINALNAME=Kilograms). Do not
  put the symbol into ORIGINALNAME or emit the unsupported ADDITIONALNAME. Correct legacy unit envelopes
  in a transport copy; do not guess physical measures or alter voucher values.
  Send each new unit once and retain per-unit request/response diagnostics and
  real counters, identifying the exact failing symbol. Existing unit reuse and
  multi-folder coalescing remain mandatory; retain line errors while Import ALL
  attempts later stages once, and never retry ambiguous requests. Mock tests do not certify live Tally acceptance.

- Unit formal names must not repeat their own symbol. Always write an explicit,
  distinct ORIGINALNAME using unit_formal_name; omission
  can allow Tally to default the description back to the symbol. Apply this to
  generated XML and legacy transport copies for every AI/Python integration.
  Disambiguate descriptive formal-name collisions against other current symbols
  and existing target names/descriptions without changing NAME,
  stock BASEUNITS, quantities, rates or voucher fields. Preserve fetched existing
  unit definitions in import receipts for diagnosis; do not treat server
  LINEERRORs as success. Import ALL must submit remaining XML stages after
  reported rejections so vouchers can reach Tally exception review.

- The desktop import dialog must expose one full import action:
  Import ALL: Units + Masters + Vouchers. Always run the full dependency sequence
  in the explicitly selected company; compatible existing units are reused.
  Do not expose a units-skipped or masters-only bypass button. The action must
  enable submit_all: reported unit/master rejections are retained and subsequent
  XML files and seller groups are attempted once. Unknown responses/connection
  losses stop dispatch without retries. Log each stage, actual unit requests,
  full master/voucher request and response, and requested voucher count. Never
  claim all requested vouchers were accepted from submission alone.
  Preserve exact current XML snapshots, financial fields and seller routing.

- Native unit lookup must fetch MailingName and ignore scalar <UNIT>count</UNIT>
  response summaries. Use the real native export schema in regression checks,
  rather than mocks asserting ORIGINALNAME equals the selling symbol. Preserve
  the EXCEPTIONS counter even when ERRORS is zero and retain all server replies.

- Use shared tally_units helpers for unit creation and symbol lookup. Exported
  unit NAME attributes are read-compatible, but must not be reused as creation
  identity attributes. Do not include MAILINGNAME/ADDITIONALNAME in the documented
  simple-unit creation packet. Support all UNIT children in a TALLYMESSAGE.
  Preserve stock masters and sales vouchers exactly while correcting only Units
  XML/transport. Python reads first; printed custom symbols and quantity suffixes
  outrank AI inference. Retain inferred custom selling units with their reasoning
  and numeric values unchanged; Qty is a heading, not an inferred selling unit.

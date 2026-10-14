# Invoice batch contract

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

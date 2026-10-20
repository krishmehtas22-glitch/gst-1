# BillSync — Main Rules

**Purpose:** The main reference for developers and AI assistants maintaining the
invoice-to-Tally app. Covers the current BillSync UI 4.0 / Reader 8.0 workflow
for TallyPrime 6.2. Consolidated and clarified on 20 October 2026.

Read this file before changing the app. This document consolidates approved
requirements; it does not itself change application behavior or prove that every
invoice will be read correctly.

**Status:** The user explicitly authorized an entire invoice-structure overhaul
on 20 October 2026. The active V2 model, prompt and migration are documented in
[INVOICE_STRUCTURE_V2.md](Automation/docs/INVOICE_STRUCTURE_V2.md). The companion
[BillSync_Extraction_Prompt.md](BillSync_Extraction_Prompt.md) describes the active
new contract. Existing accounting/editor components consume validated compatibility
views of the nested domain; old caches/reviews are retained and migrate locally.
Section 17 separates implemented additions from remaining proposals. This is not
a claim of universal extraction accuracy or statutory acceptance.

## 1. Authority and change control

1. The user's latest explicit instruction takes precedence over earlier rules.
2. Apply that authorization only to the requested area. A UI change does not
   authorize changes to extraction, units, amounts, XML or Tally transport.
3. Use this consolidated reference together with [AGENTS.md](AGENTS.md), which
   retains dated authorizations and historical locks. Older feature documents
   describe their release, and may have been superseded as identified below.
4. Before a code change, preserve the working version and identify affected
   locks. Retain original lock fingerprints; record authorized exceptions in a
   separate change manifest with baseline and resulting hashes.
5. Never rewrite an old manifest to make an unrelated change appear compliant.
6. Preserve customer documents, caches, manual reviews, master snapshots,
   financial history and existing backups. Do not overwrite unfamiliar local
   modifications or include unrelated files in a release.
7. General cleanup/refactoring is not authorization to change locked behavior.

## 2. Complete workflow

1. Select/create the client workspace and upload invoices.
2. Read Tally masters before or after upload, if the user chooses to use them.
3. List documents without AI processing.
4. The user chooses the provider and explicitly processes one invoice, selected
   invoices or the client's batch.
5. AI extracts invoice facts and considers relevant imported master candidates.
6. Python validates the structured facts, applies compatible master references,
   performs deterministic calculations and prepares XML.
7. The user reviews and can edit the invoice. Saved manual edits regenerate XML
   locally without requiring another AI extraction.
8. On explicit import, check the destination company, source/input integrity,
   dependencies, workflow issues and voucher-numbering configuration.
9. Send **Units.xml → Masters.xml → Sales_Vouchers.xml** to the selected company.
10. Record Tally's actual responses. XML prepared, request sent and voucher
    accepted are separate states.

AI-first extraction is the approved approach. Python-first template learning or
silent local extraction fallback is not the current extraction policy. Python
still prepares text/OCR input and performs validation, matching checks and XML
serialization after AI extraction or an authoritative saved human review.

## 3. Uploads, supported files and client isolation

- App upload/drag-and-drop supports **PDF, PNG, JPG and JPEG**. Preserve originals;
  use the established image-to-PDF/OCR preparation without changing PNG behavior.
- Support text PDFs, scanned PDFs and multipage documents through the existing
  reading path. Keep individual invoice/page identities separate where needed.
- Folder listing/watch follows the current PDF-listing behavior. Do not promise
  direct watched-folder image ingestion just because app image upload works.
- Explicit PDF upload performs local structural/readability checks. Report
  corrupt, unreadable, password-protected or zero-page PDFs clearly. Keep valid
  documents from a mixed upload. This check is not OCR or invoice extraction.
- Retain existing path, size, file-type and identical-byte intake safeguards.
- Opening the app, uploading, refreshing the list, changing clients and watching
  folders must not start AI, invoice OCR/extraction, XML generation or Tally writes.
- Keep each client's files, reviews, master binding and outputs correctly scoped.
  Do not apply another client's snapshot, currency setting or approval.

## 4. AI providers, consent and cost limits

- The visible processing choices are **Groq**, **Gemma (local)** and **OpenRouter (free)**.
  OpenRouter was explicitly restored on 20 October 2026. Gemini and GitHub Models
  remain hidden. OpenRouter permits only free model routes and no provider fallback.
  Legacy modules can remain; their presence does not authorize background use.
- One-invoice processing must restrict fresh AI requests to that source. Selected
  processing must restrict them to the selected sources. Client-batch processing
  must use only the confirmed client batch.
- Show and honor the confirmation/request limit. Extraction and any additional
  matching requests share the confirmed budget; no hidden extra matching calls.
- Reuse valid saved reads and approved reviews. Re-reading must remain explicit;
  cache reuse is not a new provider request.
- Fresh requests under the AI-first policy go only to the chosen provider. No
  silent cloud fallback, billing activation, model downloads or retry storms.
- At most **two extraction tasks** may be in flight. Groq retains its existing
  **13-second request-start pacing**; concurrency does not remove rate limits.
- Keep budgets atomic, same-source caches serialized and results in source order.
  Stop/quota/access failures prevent further new requests; in-flight work may finish.
- Gemma uses installed **gemma3:4b** through Ollama at
  `127.0.0.1:11434/api/chat`, without an API key, proxy, redirect or cloud fallback.
  Local inference has no per-request provider charge; hardware and electricity
  are still required, and Ollama can queue requests internally.
- Keep credentials private. Do not commit keys, invoice contents or snapshots to
  a public repository or expose secrets in logs.

## 5. Invoice extraction and source facts

Extract/review seller and buyer names, GSTINs, addresses and states; invoice
number/date; place of supply; supply/classification; item descriptions, HSN,
quantity, unit, rate, value and GST components; totals/round-off; and applicable
export country, LUT/IGST treatment, currency and exchange-rate details.

- Never fabricate a GSTIN, invoice number, date, exchange rate, country or amount.
  Do not replace a missing date with today or a missing number with a serial.
- Preserve printed identity and source evidence. Normalization must not silently
  change the economic meaning or merge different parties/products.
- Distinguish absent/invalid fields from an explicitly printed zero.
- OCR uncertainty, such as `Penci1` versus `Pencil`, must retain evidence and a
  review warning. Do not blindly rewrite names, codes or numbers.
- Supplier state, buyer state and place of supply are separate facts. A valid
  GSTIN prefix may resolve absent state metadata using existing rules; a printed
  disagreement needs review. Do not substitute buyer state for missing POS.
- An AI confidence score is not measured extraction accuracy. Unknown layouts,
  unclear scans, conflicting labels and incomplete pages may require human review.

### 5.1 Reading labels and party roles

- Identify seller from issuer evidence and buyer from Bill To/Buyer/Customer/Sold
  To. Do not use a bank, signatory, transporter or Ship To/Consignee as the buyer
  merely because that block is prominent. A GSTIN/company disagreement requires
  review; it does not by itself prove which party the AI swapped.
- Use the invoice-labelled number/date. Do not substitute PO/order/challan,
  due/delivery/acknowledgement dates, IRN, e-way bill or page numbers.
- Preserve the number's meaningful case, punctuation and leading zeros. XML
  escaping must preserve the value. Regulatory or technical restrictions, where
  applicable, are separate review findings, never permission to truncate it.
- Use the established date normalizer and Indian day/month/year convention;
  conflicting conventions need review. Do not define a new rule that all
  two-digit years use the current century: the implementation has its own
  normalization behavior and must not be changed by a prompt document.
- A future date or a date outside a selected reporting period is contextual
  evidence for review, not proof of a wrong date. Do not infer a Tally company's
  allowed posting range, financial year or locked periods without actual facts.
  Automatic company-period enforcement is a proposed feature in Section 17.

### 5.2 GSTIN, HSN, tax and line interpretation

- Validate GSTIN shape/state without changing it. As requested on 20 October 2026,
  check-digit rejection is disabled; this does not verify registration. A checksum-valid spelling is
  not proof of a real registration or of the right party. Multiple OCR edits can
  produce valid checksums. Proposed alternatives require evidence and explicit
  human confirmation; automatic checksum repair is not approved behavior.
- Missing buyer GSTIN is not automatically an error for an unregistered buyer
  or foreign buyer. It also does not prove a B2C classification if other evidence
  indicates a registered party whose GSTIN was not read.
- Read HSN/SAC from the appropriate printed column/group; do not confuse it with
  a product code or generate it from a description. Missing or unusual length
  needs contextual review, not a universal 4/6/8-digit hard block. A compatible
  existing master is a separate source, not evidence that HSN was printed.
- Supplier state, buyer state and POS stay separate. A GSTIN prefix can resolve
  the corresponding party state; **it must not be used to invent POS**.
- Ordinary intra/inter-state tax patterns help identify disagreements, but SEZ,
  exports, reverse charge, jurisdiction and other special cases need context.
  Do not silently rewrite tax amounts to force the ordinary pattern.
- Validate quantity/rate/value only after accounting for rate basis (such as per
  100), percentage versus fixed discounts, tax-inclusive prices, allowances and
  rounding. A mismatch is review evidence; do not assume which value is wrong.
- Freight/packing/insurance can be charges or actual goods/services sold. Preserve
  source meaning and tax treatment; never remove them categorically from item
  rows or convert unsupported charges into invented stock. Separate charge
  allocation/schema support is a proposed extension, not a current guarantee.
- Bill of supply can represent a legitimate exempt/composition sale. It must
  not be rejected just because it is not headed Tax Invoice. Documents outside
  the supported sales flow (purchase bills relative to this company, credit/debit
  notes, proformas, quotations, challans, receipts) require explicit handling;
  a reliable automatic document-type gate is not yet established by these rules.

## 6. Manual review and accounting values

- Double-click/review opens the exact invoice for editing, including its parties,
  items, quantities, units, tax, export and currency fields.
- Manual corrections are authoritative for subsequent local XML preparation.
  Preserve their source/client association and invalidate stale matching decisions.
- Use decimal arithmetic for currency conversion and the existing accounting
  rounding policy. Preserve original foreign/source values separately.
- Check item totals, taxable value, tax components, round-off and total. Show
  disagreements rather than silently balancing or replacing the printed figures.
- Preserve numeric quantities and rates independently from currency-cent rounding.
- Keep the current built-in accounting configuration; do not reintroduce a visible
  Summary GST accounting switch or change its configured behavior in a UI task.

## 7. Units / UTS / UQC — current and future units

These rules apply to existing and newly encountered units, not just examples.

- Keep the **selling symbol**, **formal description**, and **GST UQC** separate.
- Preserve the selling measure in stock/voucher references. UQC classification
  must never silently convert quantities or rates.
- Use the shared catalog and all **45 Tally dropdown UQCs**, including known
  aliases such as metre/meter, litre/liter, gram and bundle.
- A custom spelling such as `bundleee` is not guaranteed to match. Use evidence,
  offered candidates and validation; expose uncertainty instead of claiming
  that arbitrary typos are always understood.
- Assign the correct catalog UQC to known units with missing/generic codes.
  Retain explicit valid custom codes. Unmapped custom measures use the existing
  **OTH-OTHERS** fallback; do not invent a standard UQC or guess a conversion.
- Formal descriptions must be plain and distinct from the selling symbol and
  the short code, full code and displayed UQC label, ignoring case/extra spaces.
  Example: symbol **Packs**, formal description **Pack**, UQC **PAC-PACKS**.
  Do not use artificial suffixes such as `Pack (selling unit)`.
- Apply shared `unit_formal_name` handling to generation and legacy transport.
  This is the project's compatibility rule, not a universal claim about every
  Tally version's naming constraints.
- Preserve Tally's working simple-unit protocol: selling symbol in the child
  `NAME` field and a distinct formal description in `ORIGINALNAME`. Do not
  casually replace it with UNIT `NAME`/`RESERVEDNAME` attributes.
- Reuse an existing unit only if it represents the same measure and supports
  the required precision. Do not alter an existing Tally unit silently.
- **2.4877 KG must remain 2.4877 KG.** Use sufficient generated precision across
  the batch. More than six significant decimal places must hold XML rather than
  round; insufficient reused-unit precision requires correction in Tally.
- Preserve the existing symbol/name-collision handling. A code update does not
  remove existing exceptions inside Tally or prove they have been repaired.

## 8. Importing and applying Tally masters

- Masters include ledgers, stock items (for example pens/pencils) and units.
- Reading masters is a read-only Tally operation: no AI, XML generation or writes.
  Bind the chosen snapshot explicitly to the client and source company.
- Keep the full imported catalog available for local indexing/validation. Supply
  relevant bounded candidates to AI; do not send an unlimited catalog in every
  prompt or claim that a non-retrieved master was considered.
- AI can propose only offered IDs. Python validates identity, role, confidence,
  unit/precision, HSN and individual GST components before applying a reference.
- Ignore case/spacing differences for compatible identity matching. Minor
  spelling differences require unique, strong evidence and no known conflicts.
  Do not merge numeric product variants or competing party identities.
- Exact GSTIN, exact name and fuzzy similarity identify candidates; none can
  bypass the remaining checks. Every reused master must pass all applicable
  role, identity, variant, HSN, GST, unit and precision checks. Multiple competing
  candidates require review/fallback, not first-match selection.
- A major GSTIN/state/identity disagreement must be visible. Do not silently
  overwrite an existing master to force the invoice to match.
- A buyer must use a verified party ledger. Sales, CGST, SGST, IGST and other
  system/non-party ledgers cannot become buyer accounts merely because AI chose
  them or their names/GSTINs look similar. Retain the buyer-ledger role guard.
- Stock reuse requires compatible HSN, selling unit, precision and known GST
  components. Equal total GST alone is insufficient: 8% + 10% is not 9% + 9%.
- Use the exact accepted Tally master name/symbol in XML references. Do not
  recreate or silently alter reused definitions.
- For unmatched, unknown or incompatible entries, retain the existing new-master
  creation method. Avoid overwriting conflicting names using its readable
  disambiguation. Do not add batch/hash suffixes to ordinary party/item names.
- Preserve sales/tax ledger selection; do not substitute arbitrary AI-picked
  accounting ledgers.
- A matched batch must target the company owning its dependencies. Changed
  snapshots or deleted/renamed live masters need refresh/reprocessing/review.

## 9. Foreign-currency invoices

- AI extracts the printed currency/rate; Python performs deterministic INR
  conversion. Currency symbols, codes and spelling variants need unambiguous
  identification. An ambiguous symbol or typo is not permission to guess.
- Use a valid printed exchange rate or the client's explicit per-invoice entry.
  Manual rate entry means **INR per one foreign-currency unit**.
- Validate exchange direction and any quoted unit count. Determine whether
  printed amounts are already INR before converting; never convert them twice.
- Missing, conflicting, nonpositive or unclear rates/currency hold new XML and
  retain previous output. Do not fetch a market rate automatically.
- Retain original foreign amounts and conversion provenance. Convert the
  applicable monetary fields while preserving quantities, GST percentages,
  units, source identity and stable voucher identifiers.
- Manual currency settings are client/source/fact scoped; changed invoice facts
  require renewed review. A UI-only task must not change the locked conversion.

## 10. Export invoices and refund estimates

- Preserve actual foreign country and printed LUT/IGST treatment. Require a valid
  export country before generating new export XML; do not invent one.
- Use the established export country/state/POS fields, including **Outside India**
  for export POS. Keep supplier registration separate from the foreign buyer.
- **Exports include inventory items, quantities and stock reduction** when the
  item data is complete and reconciled. This supersedes historical notes saying
  exports are always accounting-only. Do not invent opening stock or quietly
  remove stock movement to avoid a validation problem.
- LUT exports may reuse compatible normally taxable stock without changing that
  stock master's standard GST rate or charging invented invoice tax.
- Preserve printed IGST where applicable. Do not infer that missing GST text
  proves LUT status, exemption, actual payment or refund entitlement.
- The Potential IGST refund column is an **unverified invoice-IGST estimate in
  INR**, subject to the existing export/payment/country/amount checks.
- Keep manual refund status, claim amount/reference and review notes separate
  from invoice amounts and XML. Do not automatically post a refund receivable,
  submit a claim or label an estimate as government-approved money.
- Do not calculate LUT input-ITC refund entitlement from a sales invoice alone.
- Tally's export Sales-ledger GST nature/GSTR-1 treatment needs destination-company
  verification. Valid XML/country tags do not certify statutory reporting.

## 11. Duplicate invoices

- Business-duplicate warnings compare **invoice number + invoice date**, scoped
  to the same client. Seller, GSTIN, total and file digest are not extra business
  duplicate conditions requested by the user.
- Compare available analysed/manually reviewed fields without background AI/OCR.
- Show a warning, not a compulsory block. The client may retain/process/import
  both; do not delete, auto-merge or change GUIDs to hide the warning.
- Identical-byte intake deduplication is a separate existing safeguard. Different
  bytes can still represent the same business invoice.
- Clear stale warnings when the number/date or invoice set changes. Do not claim
  that Tally will always detect/reject a duplicate sent to it.

## 12. XML and Tally numbering

- Prepare units, new masters and sales vouchers with consistent references.
  Keep internal validation/dependency metadata local; strip it from the transport
  copy without changing financial voucher content.
- `VOUCHERNUMBER` and `REFERENCE` use the source/app invoice number, preserving
  meaningful letters, separators and leading zeros. Do not use serial 1/2/3.
- `DATE`/`EFFECTIVEDATE` use the actual normalized invoice date, with existing
  Indian day/month/year handling for numeric ambiguous dates, not today's date.
- Keep supplier company GSTIN/state fields separate from buyer party GSTIN/state
  fields. Carry valid buyer state to the appropriate new ledger and voucher;
  preserve separate POS and export-country handling.
- Validate references and reused-unit precision before generating/replacing XML.
  Preserve existing output when generation fails; do not call it newly ready.
- Before dispatch, read the selected company's voucher-type configuration.
  Require unambiguous **Manual Sales numbering** so Tally retains invoice numbers.
  Automatic/unknown/missing configuration must show corrective instructions.
- Do not change Tally's numbering configuration or renumber/reimport existing
  vouchers automatically.

## 13. Review errors, overrides and cancellation

- Show the invoice, affected field, invoice value, Tally value and complete reason.
  Link each issue to the original source/read identity, even if its invoice number
  is missing or duplicated. Identify the destination and scope of the review.
- **Open source PDF / image** opens that exact document. **Edit invoice** cancels
  remaining imports and opens the exact editor. Save corrections to XML and
  start import explicitly again; editing itself makes no AI request.
- **Import to Tally anyway** requires explicit acknowledgement. It permits
  sending the existing values despite invoice-data validation issues, including
  acknowledged missing/invalid data. It does not invent replacements or make
  invalid data acceptable to Tally. This supersedes the earlier blanket rule
  that every missing mandatory invoice field was nonoverrideable.
- Bind/log the decision to exact XML, original/read source hashes, saved
  reviews/caches/currency/master choices, master snapshot and destination facts.
  Changed facts invalidate that decision.
- Changed/missing source, altered XML, stale saved inputs/snapshot and unfinished
  AI extraction cannot be bypassed by the acknowledgement. Company/dependency,
  numbering, generation and transport prerequisites remain in force.
- **X / Cancel import stops every remaining seller group**, without opening the
  next review or reporting user cancellation as a Tally failure.
- Earlier completed groups are not rolled back. State that clearly, retain their
  receipts and do not claim nothing was sent when earlier writes occurred.
- Keep source/reason content scrollable and action buttons visible on smaller
  screens. Keep Tk widget/variable lifecycle work on the UI thread.

### Review decision matrix

| Finding | Current policy |
| --- | --- |
| Missing/unreadable invoice number or date | Correction required; where reviewable XML exists, latest user-authorized import-anyway can acknowledge existing data errors. Never fabricate a replacement. Generation prerequisites still apply. |
| GSTIN, state/POS, tax or amount disagreement | Compare source and Tally; correct or explicitly acknowledge existing values where supported. Tally can reject them. |
| Missing/changed source, altered XML, stale saved facts/snapshot, unfinished extraction | No acknowledgement bypass; restore/review/reprocess and prepare current XML. |
| Wrong dependency company, unverified destination, unavailable connection, non-Manual/unknown numbering | Resolve the applicable prerequisite; import-anyway is not a transport/company/numbering bypass. |
| Unsupported generation data, missing currency rate/country, insufficient unit precision | Resolve generation prerequisite; preserve previous output and do not label it newly ready. |
| Duplicate number + date | Warning only; user can keep/process/import both. |
| X / Cancel import | Stop remaining groups; preserve and disclose any earlier completed writes. |

These are behavioral categories, not a claim that the current UI exposes a
universal BLOCK/REVIEW/INFO field-status API. Do not introduce a new nonoverrideable
number/date policy from an attached draft. Such a policy needs explicit user
authorization and matching code, UI and test changes.

## 14. Tally connection, dispatch and receipts

- Use the local Tally HTTP/XML connection, normally `127.0.0.1:9000`, with explicit
  destination-company selection. Do not route financial XML through a remote
  endpoint or HTTP proxy.
- If connection fails, explain opening the company/enabling the HTTP/XML server
  and checking its port. Do not fabricate a company list or successful import.
- Preserve **Units → Masters → Sales vouchers** and the established unit creation
  protocol. An approved review rechecks prerequisites before the first write.
- Unticking the complete client batch imports the selected invoice and its
  prerequisites, not neighbouring invoices or drafts.
- Dispatch each intended request once. In ALL mode, the existing policy can
  continue after a definite reported stage rejection while retaining errors.
  An unknown/ambiguous result stops further dispatch; no automatic write retry.
- Preserve actual returned counters/errors and attempted-request information in
  `Last_Tally_Import.json`. Check Tally before a manual retry after uncertainty.
- A successful HTTP exchange, generated XML or “request sent” message is not
  proof that every voucher was created. Report partial imports truthfully.

## 15. UI and operational records

- Preserve the approved navy/royal-blue/amber design, readable fonts, rounded
  cards, larger upload/drop area, full-width workspace and on-demand invoice
  details. Keep processing and Tally actions clearly grouped with visible XML access.
- Keep one/selected/client-batch processing, Stop, client selection/creation,
  review, source viewing, XML viewing/folder access and Tally master/import actions.
- Do not restore removed Accept/change units, Recover processing lock, Confirm
  test PDF or Advanced buttons without explicit authorization. Retain required
  functionality through the approved editor/menus/settings.
- Keep test-invoice handling explicit. Do not silently label real invoices as
  fictional data or hide a material warning to make status cards look successful.
- Logs/history should identify source, action/provider, cache reuse, request
  counts, review reasons, XML output, destination and actual Tally result where
  available. Do not expose credentials or present technical diagnostics as invoice facts.
- Preserve the separate `.invoice_app` caches, reviews, master snapshots/bindings,
  matching decisions, currency/refund settings and code backups. Never treat a
  cache file's existence as proof that it matches the current source.

## 16. Release verification and honest limits

- Use checks appropriate to the changed area: real generated XML, exact quantities,
  money/currency, source integrity, master compatibility, duplicate policy,
  explicit AI scope/budget and the desktop import/cancel/edit event loop.
- Use mocked providers/Tally for automated tests. Do not spend AI credits, import
  real vouchers or modify a live company merely to run a regression test.
- Validate installer payloads against repository files, allowed baseline hashes
  and automatic backups. Preserve known LF/CRLF variants deliberately.
- For EXE changes, build on Windows and check the bundled UI, OCR, drag-and-drop,
  providers/resources and the actual packaged runtime.
- Report actual tests passed/failed/skipped. Do not disable a meaningful failing
  check or rewrite its expected financial output just to obtain a pass.
- Passing offline tests does not establish live AI accuracy on every layout,
  live TallyPrime acceptance, government GSTIN registration, GSTR-1 correctness
  or refund eligibility. Verify the relevant live result before claiming it.
- Documentation-only work must not change runtime code, extraction output,
  AI request behavior, XML or Tally imports.

## 17. Structure V2 additions and remaining proposals

| Capability | Current status and limits |
| --- | --- |
| Versioned nested extraction and domain | Implemented: schema_version 2; separate seller, buyer, ship_to, items, charges, totals, export and evidence. Strict parser rejects unsupported shapes/types instead of silently dropping fields. |
| Per-field evidence and status | Implemented with missing/unverified/source_observed/uncertain/derived/human_reviewed/human_corrected statuses. A quote/value match is not factual verification or independently verified page geometry. |
| Raw and normalized date | Implemented: separate raw/ISO fields, disagreement findings, source review. Does not add automatic company-financial-year enforcement. |
| Delivery and reverse charge | Delivery retained in the domain/editor; current XML country mapping remains buyer-based. Reverse-charge accounting is held where unsupported, rather than silently posted as ordinary sales. |
| Document-type gate | Implemented for explicit model document types: tax/sales invoices and bill of supply can enter this sales path. Unsupported types hold XML; model classification still needs source review. |
| Multiple invoices/continuations/copies | Existing source preparation remains. Each prepared model response must contain one invoice; uncertain/multiple responses require splitting/review. Arbitrary automatic segmentation is not claimed. |
| Charges and discounts | Ordinary explicitly allocated charges and typed discounts are represented through XML. Ambiguous inclusion/discount/rate basis, TCS and unsupported special treatment hold generation; destination ledger GST reporting still needs review. |
| Existing reads and manual reviews | Local migration/reuse; no automatic paid re-analysis, deletion of old approvals or installation-time XML rewrite. Raw extraction and effective reviewed facts remain distinct. |
| Company posting-period validation | Proposed: needs actual company/date restrictions and approved blocking semantics. Do not guess a period. |
| Near-duplicate notices | Proposed only; preserve the current number+date warning-only duplicate policy. |
| GSTIN OCR correction suggestions | Proposed only; no automatic checksum-based identity repair. |

The V2 exception is recorded in
[INVOICE_STRUCTURE_V2_CHANGE.json](Automation/INVOICE_STRUCTURE_V2_CHANGE.json).
Historical locks remain unchanged; this explicit authorization covers the listed
new structure/integration changes, not unrelated monetary, unit or Tally changes.

### Accuracy measurement plan

- “Never silently wrong” is a design objective, not an achievable guarantee for
  arbitrary invoices. Wrong values can look plausible, have valid checksums and
  reconcile arithmetically. Evidence can also be misattributed.
- Build a consented/anonymized golden set with human-checked expected facts:
  ordinary/exempt/export/foreign-currency sales, diverse suppliers/layouts,
  poor scans, ambiguous dates, complex rate bases, charges and multipage cases.
  Keep customer data out of public commits.
- Keep held-out suppliers/layouts separate from examples used to tune the prompt.
  Compare old and candidate prompt/model outputs on the same source fixtures.
- Measure per-field correctness, critical-field silent errors, missing/abstained
  fields, false warnings, master-match precision, review rate, request count,
  latency and cost. Include the denominator and test-set scope.
- A useful silent-error metric is wrong accepted critical fields divided by
  evaluated critical fields; report abstentions/review coverage separately so
  mass rejection cannot masquerade as high accuracy.
- Final XML/reference/amount correctness and actual Tally acceptance need their
  own checks. Offline mocked-model tests verify pipeline behavior, not live
  extraction accuracy. Live provider benchmarks require explicit cost/data scope
  and must not bypass the existing consent or request budgets.
- A new prompt version requires regression checks and deliberate cache/revision
  compatibility handling. Do not silently replace a locked production prompt,
  reinterpret old caches as new evidence, or add automatic retries.

## Reference map

| Topic | Reference |
| --- | --- |
| Active V2 extraction contract and prompt | [BillSync_Extraction_Prompt.md](BillSync_Extraction_Prompt.md) |
| Dated instructions and locks | [AGENTS.md](AGENTS.md) |
| Original Import ALL lock | [IMPORT_ALL_LOCK.json](Automation/IMPORT_ALL_LOCK.json) |
| Original reader lock | [WORKING_READER_LOCK.json](Automation/WORKING_READER_LOCK.json) |
| Approved UI design record | [APPROVED_UI_DESIGN_LOCK.json](Automation/APPROVED_UI_DESIGN_LOCK.json) |
| AI-first workflow, historical 3.4 description | [AI_FIRST_WORKFLOW.md](Automation/docs/AI_FIRST_WORKFLOW.md) |
| Nested model/schema, migration and structured editor | [INVOICE_STRUCTURE_V2.md](Automation/docs/INVOICE_STRUCTURE_V2.md) |
| Machine-readable extraction schema | [invoice-v2.schema.json](Automation/schemas/invoice-v2.schema.json) |
| Current review/override/cancel behavior | [IMPORT_REVIEW.md](Automation/docs/IMPORT_REVIEW.md) |
| Master matching, historical initial release | [TALLY_MASTER_MATCHING.md](Automation/docs/TALLY_MASTER_MATCHING.md) |
| Local Gemma | [LOCAL_GEMMA.md](Automation/docs/LOCAL_GEMMA.md) |
| Document formats | [DOCUMENT_FORMAT_VERIFICATION.md](Automation/docs/DOCUMENT_FORMAT_VERIFICATION.md) |
| Invoice voucher numbering | [INVOICE_VOUCHER_NUMBERS.md](Automation/docs/INVOICE_VOUCHER_NUMBERS.md) |
| Export country/refund estimate | [EXPORT_COUNTRY_REFUND.md](Automation/docs/EXPORT_COUNTRY_REFUND.md) |
| Current unit/UQC implementation | [unit_catalog.py](Automation/Common_Rules/unit_catalog.py) |
| Exact quantity limits | [quantity_precision.py](Automation/Common_Rules/quantity_precision.py) |
| Currency conversion implementation | [foreign_currency.py](Automation/Common_Rules/foreign_currency.py) |
| Workflow integrity and review checks | [workflow_validation.py](Automation/Common_Rules/workflow_validation.py) |
| Authorized AI-first changes | [AI_WORKFLOW_CHANGE.json](Automation/AI_WORKFLOW_CHANGE.json) |
| Authorized 3.5 review changes | [IMPORT_REVIEW_UX_CHANGE.json](Automation/IMPORT_REVIEW_UX_CHANGE.json) |

Historical statements that mandatory data can never be overridden, or that
exports always have no inventory movement, do not describe the current workflow.
Use Sections 10 and 13 and the latest dated authorization for those decisions.

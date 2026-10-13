# Invoice batch contract

The user explicitly requires complete XML batches for review in Tally.

- All future Cerebras, Gemini, Groq, or other AI batch integrations must use the complete
  batch workflow (`read_with_fallback`, then `process_sources` with the saved
  client batch policy). Never let API quota expiry discard successful reads.
- Switch to other configured active providers (GitHub Models, Groq, Gemini) for remaining sources; use local
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
- Keep separate clients and sellers isolated. Fresh output paths must contain
  Units.xml first, then one consolidated Masters.xml and Sales_Vouchers.xml per seller, with an exact
  input/output count. Open client XML folder must show this latest run.
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
- Gemini and GitHub Models must use Groq's shared prepare_invoice_payload
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
  names with matching GSTINs, deduplicating identical prerequisite masters. Report
  actual server counters, stop dependent imports after errors, and never retry an
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

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
- Preserve prior financial/import history and manual corrections. Keep stable
  voucher GUIDs and do not force-release another live process's OS lock.
- Date repairs must only change date/audit fields. Normalize actual calendar
  dates to YYYY-MM-DD and write Tally YYYYMMDD. Recover missing AI dates only
  from verified source invoice-date evidence, not due dates or today's date.
  Keep working seller, buyer, quantity, rate, unit and stock logic unchanged.
- XML generation is not proof of successful Tally import or correct GSTR-1.
  Test partial-provider exhaustion, all-local fallback, master-unit variants,
  missing fields, zero GST, updated output paths, and unchanged retained history.

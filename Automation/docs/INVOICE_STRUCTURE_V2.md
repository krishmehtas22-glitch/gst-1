# BillSync UI 4.0 / Reader 8.0 — invoice structure V2

The invoice processing structure now has a versioned nested domain. This is a
runtime update, not simply a replacement Markdown prompt.

## Processing boundaries

1. Explicit upload/listing remains local and starts no AI.
2. Explicit Groq/Gemma extraction requests the V2 envelope in `invoice_prompt.py`.
3. `invoice_document.py` validates its version, types, keys, numeric strings and
   prepared-invoice count. Parties, delivery, dates, items, charges, totals,
   exports, evidence and flags stay separate.
4. A source-bound `document` is saved alongside a checksum-checked compatibility
   view. The original extracted nested facts remain in `raw_extraction`. Model, contract
   and prompt hashes identify the producer without claiming measured accuracy.
5. Existing matching/accounting components consume a local projection; candidate
   IDs still pass the existing company, role, identity, HSN, component GST and
   unit/precision checks. New structure does not loosen master validation.
6. Inspection/review retain the domain and field statuses. The ordinary editor
   keeps familiar fields. Its **Details & evidence** button opens document and
   delivery fields, charges, item treatment and source-evidence tabs.
7. Manual changes save an approved nested document plus the established review
   view. New charges/discount choices are preserved through regeneration.
8. Before XML is replaced, structural/accounting-support checks run. Domain
   findings reach the source-linked import review. The batch report and local
   validation metadata retain the nested document; Tally receives native XML.

## Schema

See `Automation/schemas/invoice-v2.schema.json`. Provider scalar facts are strings
or null, not floating-point money/quantities. The model envelope is:

```json
{
  "schema_version": 2,
  "invoices": [
    {
      "document_type": "tax_invoice",
      "invoice_number": "INV/0042/26-27",
      "invoice_date_raw": "05/04/2026",
      "invoice_date_iso": "2026-04-05",
      "seller": {"name": "Example Supplier"},
      "buyer": {"name": "Example Customer"},
      "ship_to": {"name": "Separate delivery recipient"},
      "items": [],
      "other_charges": [],
      "totals": {"grand_total": "1000.00"},
      "evidence": [],
      "flags": []
    }
  ]
}
```

This example shows shape only; incomplete facts are not an import-ready invoice.
A prepared source must produce one invoice. Multiple/zero invoices in a response
are rejected with a split/review message, rather than silently choosing or dropping
invoices. Arbitrary multi-invoice/continuation/copy segmentation is not claimed.

When a master snapshot is supplied, optional `_tally_matches` stays at the envelope
root, with party and indexed stock/unit proposals containing id/confidence/reason.
There are no competing buyer_master_id/stock_master_id aliases. Python validates
that IDs were offered and compatible; confidence is not accuracy. Candidate retrieval also uses complete primary source
text when local layout parsing has not found the right item names. The actual
offered IDs are retained; optional master context cannot masquerade as invoice
evidence. Matching retained reads sends nested facts without private cache metadata.

## Evidence and review

`source_observed` means a supporting quote/value was found in supplied text. It
is not independent proof of the extraction or page. AI page hints are labelled
unverified. Missing critical quotes and unsupported quotes generate review
findings. Fields can be missing, unverified, source-observed, uncertain, derived,
human-reviewed or human-corrected. Normalization is distinguished from source
observation, and manual review does not overwrite the retained raw extraction.

Printed and normalized dates remain separate. Contradictions are reviewed; no
current date or serial number is invented. A checksum-valid guessed GSTIN is not
adopted. Source/client/read digests remain bound to documents and cache projections.

## Charges and supported treatment

Physical goods remain items. Separately identified ordinary charges have a named
ledger, amount, kind and explicit yes/no indication of inclusion in the printed
taxable total. Included charges reduce the item-sales allocation; excluded charges
are added once outside it. Source aggregate GST is not posted a second time.
Charges are converted with other source monetary amounts for foreign invoices.
Their ledger GST nature/reporting requires destination-company review.

Explicit percentage discounts and amount discounts can supply a corresponding
DISCOUNT allocation without changing the printed item quantity/rate/value.
Unclear inclusion/discount basis, non-unit or tax-inclusive rate bases, TCS and
reverse-charge accounting are held for review where no safe serializer exists.
They are retained in the document and not silently treated as ordinary sales.
This release does not claim complete statutory handling for every special case.

## Existing data and unchanged controls

- Existing Groq/Gemma V1 reads migrate locally when loaded. No automatic paid
  re-analysis, cache deletion or loss of human reviews is required.
- Fresh reads save V2 documents. Existing current XML is not silently rewritten
  by installation; deliberate processing/manual saving prepares current output.
- Local Gemma retains its 16,384 context setting. Optional master context is
  bounded and the response allowance is conservatively sized; overlength input
  is rejected before a request rather than truncating invoice text or expanding
  the model memory setting silently. There is no cloud fallback.
- One/selected/client selection, two-task bounds, Groq pacing, stop, request caps,
  local-only Gemma and source verification remain in place.
- Import remains Units -> Masters -> Sales with Manual numbering, source invoice
  number/date, existing unit/UQC rules and exact quantities such as 2.4877 KG.
- The approved explicit invoice-data override policy remains; stale sources/XML,
  dependency/company/numbering and generation prerequisites are not bypassed.
- Closing a review cancels remaining groups. Existing receipts/partial results
  remain truthful. No automatic Tally retry was introduced.

Backups/Before_Invoice_Structure_V2.zip and INVOICE_STRUCTURE_V2_CHANGE.json record
the prior source and explicit authorized exception. The source installer also
backs up files it replaces. Tests use fake providers/Tally; no live-model accuracy
or TallyPrime statutory reporting is certified by these tests.

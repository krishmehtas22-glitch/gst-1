# Position-aware invoice reader — separate evaluation

This is a shadow reader. The desktop app, Groq request/prompt, AI caches, UQC
rules, financial XML writers and Import ALL button are unchanged. Nothing in
this directory is imported by the existing application. No AI requests, XML
generation, cache updates, human approvals or Tally imports are performed.

Run with the reader's existing Python environment:

```text
.venv\Scripts\python.exe Read_Invoice_V2.py "F:\Downloads\dummy sales invoice"
```

The separate installer `Start_Reading_V2_Evaluation.py` selects that environment
automatically and installs only new evaluation files. `Report.html`,
`Comparison.csv`, `Summary.json` and per-document evidence JSON are written to a
new `.invoice_app/reading_v2_evaluations/` folder. Existing reports are never
overwritten. Open Report.html and click a field to highlight its source words.
The view reconstructs positioned text; the source PDF remains authoritative.

## Implemented

- Read PDF glyphs into words with normalized top-left page coordinates, page
  numbers and stable source-token identifiers. Keep PDF word boundaries instead
  of guessing spaces from glyph widths. OCR scanned/rotated pages while retaining
  OCR boxes and recognition scores.
- Identify label/value relationships and adjacent party panels from geometry.
  Keep buyer and seller GSTIN ownership scoped to the latest matching panel.
  Use shared invoice field/header names rather than supplier-name templates.
- Reconstruct item rows from column anchors and retain source evidence per cell.
  Support repeated table headers across pages; incomplete/contradictory tables
  stay in the review queue.
- Use the existing local parser as an explicitly reported fallback. Retain
  conflicts rather than overwriting nonempty existing facts. This is a staged
  replacement, not a claim that the legacy parser has already been eliminated.
- Check core fields, quantity/rate/value and available printed totals using
  Decimal. Do not convert quantities, invent missing tax or scale financial
  values. Ambiguous decimal-comma notation needs review.
- Prepare proposed structured AI input with geometry using `--ai-input`; no
  request is sent. Exceeding the input budget raises a visible routing note,
  with no silent truncation. PDFs with multiple invoice identifiers need grouping
  before any future AI integration.

## Evaluation limits and promotion

Running without exceptions, matching the old reader, and passing arithmetic
checks are coverage/agreement measurements, not extraction accuracy. Measure
against independently reviewed ground truth, including complete invoice-level
accuracy, on the user's actual 30 layouts and unfamiliar suppliers before
promotion. Audit incorrect totals, identities, dates, units and item rows
separately. Existing successful AI results must remain terminal for scheduling.

Still required before replacing the production reading path: verified held-out
results, document/invoice grouping, calibrated acceptance criteria, bounded AI
integration using the existing shared provider budget and Stop/cache contracts,
and tests of scanned, rotated, multilingual and damaged invoices. The locked
UQC/import/writer code must remain intact. No change to financial history or
approved corrections is authorized by running this comparison.

# Document format verification — 16 October 2026

The approved design reference is locked in `APPROVED_UI_DESIGN_LOCK.json`.
This is a design approval record, not a claim that the latest mockup is already
implemented in BillSync UI 1.1.

The existing upload adapter already supports PDF, PNG, JPG and JPEG. No runtime
format changes were necessary. `Document_Upload.py`, the reader, Common_Rules,
AI input/prompt recipe, PNG handling and all output/import code remain unchanged.

| Input | Verification |
| --- | --- |
| Text PDF (.PDF) | Original bytes retained; printed text reaches existing Groq input preparation. |
| Scanned PDF | Original bytes retained; real local OCR reads the invoice. |
| PNG | Original retained; deterministic one-page conversion and real OCR succeed. |
| JPG / JPEG | Original retained; one-page conversion and real OCR succeed. |
| Rotated JPEG (EXIF orientation) | Existing orientation correction restores upright dimensions and readable text. |
| CMYK JPEG | Existing colour conversion produces readable invoice text. |
| Grayscale JPEG | Existing conversion and OCR produce readable invoice text. |
| Two-page PDF | Both original pages retained, with readable continuation text. |

The new tests prepare a synthetic invoice with known seller/buyer, invoice
number, item, unit and totals, then call actual upload, PDF reading/OCR and the
unchanged `prepare_invoice_payload` function. They assert those printed facts
reach the provider input, originals remain unchanged, duplicate re-upload is
reused and no XML is generated during intake/input preparation. PNG/JPG/JPEG
are uploaded through Upload invoices or drag-and-drop; the stored PDFs enter the
existing reader. Folder listing itself still lists PDFs only and starts no AI.

This verifies the supported formats and local provider-input path. It does not
measure live Groq response accuracy on arbitrary invoice layouts or poor-quality
photographs. No provider requests or Tally imports were sent by these checks.
There is no new program update required for format support.

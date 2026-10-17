# BillSync 2.2 input/output audit — 17 October 2026

**The audit found 8 issue types. The app should not yet be treated as ready for unattended real-client use.**

Audited source: [`79dcfc4a5bcde30c9ece54194e47bfe7e0d2430e`](https://github.com/krishmehtas22-glitch/gst-1/tree/79dcfc4a5bcde30c9ece54194e47bfe7e0d2430e).
The existing tests passed, but the additional acceptance checks exposed gaps.
No runtime code, installed app, customer documents or Tally company was changed.
158 tracked Python files were verified unchanged. Only audit tests and reports
were added. Findings below remain **unfixed** in the audited version.

| Verification | Result | What it establishes |
|---|---:|---|
| Existing regression suite | 884 passed, 0 failed, 0 skipped | Existing extraction, queue, unit, XML, consent, history, recovery and GUI contracts still pass |
| New independent acceptance suite | 25 passed, **27 failed**, 0 skipped | 52 checks; failed variants belong to 8 issue types, not 27 unrelated bugs |
| Real desktop navigation probe | 14 functional checks passed | Startup, client creation, upload, dashboard, clients, settings, activity, filters and three window sizes |
| Controlled financial oracle | 500 distinct invoice records / 1,000 item rows passed | Decimal amounts, tax allocations, quantities, numeric rates, source preservation and repeat GUID stability across five treatments |
| Upload → text/OCR → controlled correct AI response → XML → cache | 12/12 passed | Three layout families × PDF, PNG, JPG and JPEG; source bytes retained and reruns use no new AI request |
| Exact raster OCR fidelity | **9/9 strict checks failed** | The tested Courier font's `Pencil` text was misread before AI; see A08 |
| Published Windows build at the audited revision | Success | EXE build and frozen OCR/UI smoke check passed; it did **not** run these new acceptance checks |

The 500 records are generated accounting fixtures, **not** 500 real-world invoices
successfully read by live AI. Confidence scores are not measured accuracy. The
three input layout families are stacked parties, paired parties and reordered
item columns; they do not represent every possible supplier design.

## Findings requiring correction

### A01 — High: same invoice, different PDF bytes, separate vouchers

Two records with the same seller GSTIN, date and invoice number but different
source digests generate two distinct voucher GUIDs. The batch has no duplicate
warning, even with checksum-valid synthetic GSTINs and complete amounts.

**Impact:** rescanning or changing PDF metadata can bypass byte-level upload
deduplication. This creates a risk of duplicate posting; the audit does not claim
that live Tally accepted both vouchers.

**Location:** [source-based GUID selection](../../Common_Rules/tally_review_export.py#L127).
**Reproduction:** `test_duplicate_business_invoice_with_different_source_bytes_requires_review`.
**Required fix direction:** detect business-identity duplicates and require an
explicit resolution before importing. Preserve existing voucher identities and
history; do not silently discard legitimate corrections or sources.

### A02 — High: a matched party can take a system ledger name

Controlled AI selections of debtor masters named `Sales`, `CGST`, `SGST`, `IGST`
or `Round Off` are accepted. For `Sales`, `CGST` and `SGST`, the example already
has corresponding sales/tax postings in the same voucher. The party and another
accounting role therefore share one ledger name. Arithmetic balance still passes.

**Impact:** a balanced voucher can have the wrong accounting classification or
net party balance. Name/group/role compatibility must be checked together.

**Locations:** [party validation](../../Common_Rules/tally_master_matching.py#L171),
[reference transformation](../../Common_Rules/tally_master_xml.py).
**Reproduction:** `test_matched_buyer_cannot_take_a_system_ledger_name` (5 variants).
**Required fix direction:** reject role collisions; if a required system name is
already occupied by a different type of ledger, block or obtain an explicitly
validated alternative rather than merging accounting roles.

### A03 — High: matching total GST does not prove matching components

An intra-state invoice requiring 9% CGST + 9% SGST accepts a stock master with
8% + 10%, 10% + 8%, or 0% + 18%, when the overall rate remains 18%.

**Impact:** the selected existing stock master's GST settings conflict with the
invoice's components. The app preserves the printed XML tax amounts, but the
existing master can give incompatible treatment inside Tally/GSTR-1.

**Location:** [total-rate comparison](../../Common_Rules/tally_master_matching.py#L207).
**Reproduction:** `test_equal_total_gst_does_not_hide_conflicting_components` (3 variants).
**Required fix direction:** validate the applicable component rates against the
transaction's supply type, while allowing a normal master to carry both domestic
component rates and its valid IGST rate.

### A04 — High: shared unit precision is checked only for matched rows

The snapshot contains `KG` with zero decimal places. An integer-quantity row
selects it successfully. A second unmatched row needs `5.5 KG`. The generated
unit definition is then removed because `KG` appears in the external-unit list,
and the complete batch does not recheck that every reference fits its precision.

**Impact:** an unsupported fractional quantity reaches XML/import planning.
Live Tally may reject it or handle the precision differently; rounding was not
tested live and should not be assumed safe.

**Location:** [global removal of external units](../../Common_Rules/tally_master_xml.py#L96).
**Reproduction:** `test_external_unit_precision_covers_every_item_not_only_the_ai_matched_item`.
**Required fix direction:** check the maximum required precision across all
references before reusing/omitting a unit. Retain the original protocol's safe
conflict handling and never silently scale or round the quantity.

### A05 — High: foreign-currency values lack sufficient guards

With `currency=USD`, `AED` or `EUR`, and no conversion evidence, the active review
writer emits plain numeric accounting amounts without a currency/conversion
warning. The refund helper also accepts foreign-currency IGST `18` and presents
it as an INR reference because it checks `foreign_currency` but not `currency`.

**Impact:** unqualified amounts can be interpreted as the company's base
currency, and a refund reference can be given the wrong currency label. The
refund remains unverified; no refund receivable or government claim was posted.

**Locations:** [amount handling](../../Common_Rules/tally_review_export.py),
[refund currency check](../../Export_Refund_Review.py#L39).
**Reproductions:** `test_refund_estimate_is_not_labelled_inr_for_unconverted_foreign_currency`
and `test_unconverted_foreign_invoice_does_not_silently_post_as_base_currency`
(6 variants combined).
**Required fix direction:** distinguish confirmed INR accounting values from
foreign prices. Require conversion evidence or hold the financial import for
review; never invent an exchange rate or silently relabel foreign amounts.

### A06 — Medium: installer backup exists, but failure does not roll back

Injecting a write error after the new UI file is installed leaves that new file
alongside older files. The previous source backup exists, but the installer does
not automatically restore the pre-installation state.

**Impact:** disk/permission/file-lock failures can leave an incomplete upgrade.
This test does not show customer-document loss. Manual recovery or a successful
rerun is still possible.

**Location:** [source installer](../../../Install_BillSync_Source.py#L24).
**Reproduction:** `test_source_installer_rolls_back_if_a_write_fails_mid_install`.
**Required fix direction:** stage and verify all files, then install with rollback
of already replaced files when any write fails.

### A07 — Medium: PDF signature alone is accepted as a valid upload

A file containing `%PDF-1.7` and invalid content, with no usable PDF object tree
or trailer, is reported as uploaded. Failure is deferred to later reading.

**Impact:** invalid files reach the queue and can lead to wasted processing or
placeholder review XML. This is an input validation gap, not evidence of a PDF
code-execution exploit or a successful Tally import.

**Location:** [signature-only validation](../../Document_Upload.py#L70).
**Reproduction:** `test_bad_pdf_header_is_not_sufficient_proof_of_a_valid_upload`.
**Required fix direction:** validate document structure/readability at intake and
give a specific corrupt/encrypted-file result without analysing it with AI.

### A08 — Medium: exact OCR item text can differ from the image

For the generated Courier-font sample, `Pencil` is not preserved exactly in the
OCR text sent to AI; an `l`/`1` confusion appears. All 9 raster variants fail this
strict check. They share one font/fixture design and are not 9 independent
real-world accuracy samples.

**Impact:** scans can send corrupted product text to the model. Live AI may or
may not correct it. This is not proof that all PNG/JPEG invoices fail.

**Reproduction:** `test_raster_input_exact_text_fidelity_before_ai` (9 variants).
**Required fix direction:** preserve uncertainty/evidence, improve or selectively
retry OCR where justified, and review uncertain identity/product fields. Do not
equate XML generation with accurate reading.

Importantly, all 12 upload-to-XML checks pass when a controlled correct AI result
is returned. The audit deliberately separates OCR input fidelity from later field
transfer; it does not claim that Python overwrote a correct AI item name.

## Additional behavior verified

- 100 controlled invoices each for intra-state, inter-state, exempt, LUT export
  and IGST export; 1,000 total item rows and stable GUIDs on rerun.
- Uploads preserve source documents; controlled successful reads are reused on
  the next processing action without a new AI request.
- Connection loss at each of Units, Masters and Vouchers stops further dispatch
  without retries and preserves current XML bytes.
- A failed XML publication restores the previous current output.
- Oversized files are rejected before reading their payload; animated PNG is
  rejected while another valid upload in the same batch succeeds.
- Linked upload directories cannot write outside app storage. XML escapes
  ampersands and angle brackets while preserving numeric values.
- Real desktop client creation, upload, dashboard, client list, settings,
  activity, explanatory empty-state actions, filtering and three window sizes.
- Existing regression checks cover explicit one-PDF/batch consent, shared API
  budgets, Stop/quota behavior, retained caches, manual edits, source tampering,
  client separation, units/UQC, export country and refund review.

## Limits and release decision

No paid/live AI extraction or live Tally import was run. AI/Tally responses in
new integration tests are controlled fixtures and network connections are
blocked. Actual model accuracy, real TallyPrime 6.2 acceptance, duplicate handling
inside Tally, voucher numbering configuration and final GSTR-1 return treatment
still require live verification after the high-priority findings are corrected.

The [published Windows build](https://github.com/krishmehtas22-glitch/gst-1/actions/runs/39001998961)
passed its existing verification and frozen smoke check at the audited revision.
It did not include these new acceptance checks. A successful build does not
resolve the findings above.

Evidence: [Summary.json](Summary.json), [regression JUnit](regression_junit.xml),
[acceptance JUnit](acceptance_junit.xml), [desktop probe](ui.json),
[actual OCR excerpt](ocr_excerpt.txt).
Reproduction instructions: [audit README](../README.md).

**Recommendation:** correct A01–A05 before unattended real-client use, then rerun
the full regression and acceptance suites and validate a small batch in a Tally
test company. This audit made no runtime fixes or new app release.

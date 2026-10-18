# BillSync UI 3.4 — AI-first invoice-to-Tally workflow

This update keeps AI-first extraction. No Python-first/template-learning mode was
introduced. Upload PDF/PNG/JPG/JPEG, select a client, optionally read Tally ledgers,
stock items and units before or after upload, choose Groq or local Gemma, then
explicitly process one invoice, selected invoices or the client batch. Startup,
upload, refresh and watching do not analyse invoices or consume AI requests.

The full imported catalogue remains available to Python for indexing/validation;
relevant bounded candidates go to the chosen AI with the original invoice text.
A single giant prompt is not used for every Tally master. Compatible references
reuse the exact existing master names. Otherwise the existing new-master method
remains. Case-only differences are normalized. A high-confidence AI party choice
with a close unique spelling may match without GSTIN only when other known
identity facts do not conflict; numeric name variants and competing names are
not silently merged. GST components are checked individually, not just by total.

The UI enables the new policy for its storage root. Older standalone Reader
entry points without that policy retain their existing behavior. Existing XML
must be processed again once to carry the validation metadata; saved reads and
human reviews are reused where possible. Installation does not process files.

## Drafts, correction and review

Every generated invoice carries source-bound workflow metadata and a ready/review
status. Missing invoice number/date, names, invalid/missing required state/POS,
missing exact quantities and incomplete export stock data need correction. A
missing invoice number is not replaced with a made-up voucher serial/reference.
Draft XML is not ready for dispatch. Use invoice review and save changes to XML.

Invalid/conflicting GSTINs, conflicting master facts, amount/GST reconciliation
and export reporting checks are shown side by side before any writes for that
company. The client can explicitly tick the review acknowledgement and choose
**Proceed with invoice details**. Printed invoice facts and incompatible-master
fallback are retained; an existing Tally GSTIN is not overwritten to force a
match. Tally's own acceptance is independent and may reject invalid data.
Acknowledgements are logged in `Workflow_Review_Decisions.json`, bound to exact
voucher content, source files, reviews/AI caches/currency settings/master choices,
master snapshot and the selected company's returned registration details.
Changes invalidate acknowledgement. Mandatory missing/changed data cannot be
bypassed. No import was sent when a prerequisite review is first presented.

The selected company's registration is read from Tally before dispatch. If Tally
does not return GSTIN fields, the app shows that verification is unavailable
and requires explicit review; it never invents the company registration. This
local check does not prove registration status against the government portal.

## XML and import

The printed invoice number is emitted in VOUCHERNUMBER and REFERENCE. The invoice
calendar date is emitted in DATE/EFFECTIVEDATE; numeric ambiguous dates retain
the existing Indian day/month/year rule. Supplier and buyer GSTINs occupy
separate company/party fields. Domestic buyer state reaches the new buyer ledger
and voucher; valid GSTIN prefixes can resolve absent state metadata. Explicit
printed state disagreements require review. Buyer state is never substituted
for a missing place of supply. Existing Tally masters are not altered silently.

Export invoices now include item quantities and stock allocations when complete
and reconciled, so the imported voucher records stock movement. Printed LUT/IGST
mode, country, tax amounts and foreign-currency-to-INR conversion are retained.
LUT transactions may reuse a compatible normally taxable stock master without
changing that master's standard tax rate. The app does not invent opening stock.
Missing export inventory data blocks dispatch rather than quietly switching to
an accounting-only export. Review/confirm the destination Sales ledger's export
GST nature/GSTR-1 treatment in Tally; no undocumented export-nature override tag
has been invented. Live TallyPrime 6.2 export/reporting acceptance still requires
verification in the destination company. Refund estimates remain unverified.

Import ALL still sends Units -> Masters -> Sales with explicit destination
selection and the existing one-attempt/error/unknown-result behavior. Exact
quantities, rates and source amounts are preserved. If only one invoice is to be
imported, untick the complete client batch; the selected invoice's prerequisites
are filtered without importing neighbouring drafts. Metadata is removed from
the transport copy, with vouchers unchanged. XML creation, acknowledgement and
successful Tally import are distinct; review the returned import counters.
Existing imported vouchers are not renumbered or reimported automatically.
Manual Sales numbering remains required to retain source invoice numbers.

## Concurrent requests

Groq and Gemma support at most two in-flight extraction tasks. Groq retains the
existing request-start pacing; on short responses there may be no overlap.
Quota/access failure prevents more new requests; already running requests may
finish. Shared request budgets are atomic, identical source caches are
serialized, results keep source order and callbacks/checkpoints run sequentially.
Local Gemma stays on localhost with no cloud fallback. Under the new policy fresh
requests go only to the chosen provider; saved valid reads can still be reused.
Ollama may queue internally depending on hardware; speedup is not guaranteed.

Development tests use mock AI/Tally responses and generated XML. They do not
establish real-model extraction accuracy or live statutory reporting correctness.
The original release is retained in Backups/Before_AI_Workflow_Validation.zip;
the cumulative installer also backs up the user's replaced source files.

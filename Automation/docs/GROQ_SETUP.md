# Groq invoice extraction (Reader 6.8)

Current complete-batch import order (Reader 7.4): **Units.xml → Masters.xml → Sales_Vouchers.xml**, in the same selected Tally company. For missing-unit/stock exceptions, regenerate from cached reads, import units, retry masters, then retry only rejected vouchers.

Groq is separate from xAI's Grok. Create an account at https://console.groq.com
and create an API key under API Keys. Free access has model-specific request
and token limits; availability and limits must be checked in your own console.
No paid plan, billing change, or automatic fallback is enabled by this reader.

Press the Windows key and search **Edit environment variables for your account**.
Under **User variables**, click **New**. Set the name to `GROQ_API_KEY` and paste
your key in the value. Save and close all invoice app/CMD windows, then reopen
**Open_Invoice_App.bat**. Never paste a key into chat or save it in source code.

The initial text model is `llama-3.3-70b-versatile`. Its availability for your
account is not assumed: run **Check_Groq_API.bat** to list/check access and test
one small JSON response. If unavailable, set the optional User variable
`GROQ_INVOICE_MODEL` to an available text/chat model supporting JSON responses,
then reopen the app. The diagnostic does not change your model or billing.

Choose one client folder and scan. Click **Read client batch with Groq → XML**
to queue its invoices, apply successful extraction, and attempt XML generation.
Review the prepared vouchers in Tally. The single-invoice **Read selected with
Groq** option requires desktop Review, like Gemini. Existing manual corrections
and saved financial/import history are retained. GST, reconciliation,
missing-field, source-change and duplicate checks remain active.

Groq receives locally extracted PDF text, not a raw PDF. Scans first use local
OCR. It can interpret the resulting text but cannot recover details OCR has
lost or see logos/colour/visual geometry. Text over 24,000 characters is rejected
explicitly rather than truncated. Missing information stays missing; the normal
quantity/unit defaults still apply. Explicit zero tax and LUT are preserved.

Successful results are cached separately from Gemini. The most recently
successful provider is used for each PDF, without erasing prior provider caches.
Calls start at least 13 seconds apart; request/token quotas can still cause
HTTP 429, which stops the batch. Authentication/access/model errors (401, 403,
404) also stop the queue instead of spending requests on the same failure.
No automatic retries or fallback calls spend
additional quota. `.invoice_app/groq_batch_results.json` records every queued
source, including failed/not-attempted ones. A quota/access/model stop prevents
new requests but still applies successful cached extractions elsewhere in the
batch and proceeds to XML processing. When Test invoices is enabled, the batch
confirmation explicitly confirms the successfully read PDFs as fictional, so
they do not need an additional Confirm test PDF click. With Test invoices off,
no fictional confirmation is saved. Batch acceptance defers comparison
to Tally and does not falsely record individual human approval.

Tests use simulated responses. Live Groq invoice accuracy and your account's
remaining free quota have not been verified from the development environment.

## Access denied (Reader 6.10)

HTTP 403 means access denied, not proof that free quota is exhausted. Requests
now use an explicit application User-Agent and JSON Accept header. HTML or
Cloudflare blocks are distinguished from JSON API reasons. Run
**Check_Groq_API.bat** and share its result lines: the diagnostic identifies
model-list versus small-generation failure without uploading an invoice or
printing your key. No client change can guarantee account or gateway access.

## Complete output and fallback (Reader 7.0)

The client batch option now retains successful reads, tries the other configured
AI for remaining sources, then uses Python/OCR. The saved client policy produces
XML for all scanned invoices on subsequent scans. Warnings are retained in
Batch_Report.json and voucher narration. One Masters.xml and Sales_Vouchers.xml
pair is produced per seller in a fresh run, and Open client XML folder points
to that run. Inventory requires usable fields; otherwise an accounting voucher
retains extracted items in the report. Missing dates or identity can still be
rejected by Tally. Inspect differences posted to Invoice differences - review.
This does not enable billing or claim successful import/correct filing.

## Unit reasoning (Reader 7.1)

The AI prompt now permits missing selling units to be inferred from item and
packaging context. It returns unit_basis and unit_reason. Printed evidence and
manual corrections take priority. Qty is not a selling-unit token. Inferred
medicine strength is rejected as the sold unit. Assumptions remain visible
in narration and Batch_Report.json without blocking the complete XML output.
No numeric quantity/rate/value conversion is performed. Existing caches are
retained without requiring new API requests.

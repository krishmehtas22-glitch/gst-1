# GitHub Models (Reader 7.3)

Current complete-batch import order (Reader 7.4): **Units.xml → Masters.xml → Sales_Vouchers.xml**, in the same selected Tally company. For missing-unit/stock exceptions, regenerate from cached reads, import units, retry masters, then retry only rejected vouchers.

GitHub Models replaces Cerebras in the active desktop/fallback workflow.
Cerebras source caches remain readable, but automatic fallback never calls it.

Create a GitHub fine-grained personal access token at
https://github.com/settings/personal-access-tokens/new with the **Models**
account permission set to **Read-only** (`models:read`). Do not grant repository
write access for invoice inference. Keep the token private and never paste it
in chat or source code. See the current GitHub Models quickstart if account
eligibility or permission labels differ:
https://docs.github.com/en/github-models/quickstart

On Windows, search **Edit environment variables for your account**. Under User
variables create `GITHUB_MODELS_TOKEN` with the token as its value. Close the
invoice app and old CMD windows, then reopen **Open_Invoice_App.bat**.
The app never reuses `GITHUB_TOKEN`, Git credentials or another provider's key.

Run **Check_GitHub_Models_API.bat**. It queries the model catalog and, if the
configured model is listed, makes one small JSON request without an invoice.
The initial model is `openai/gpt-4o`. Current availability/free access is not
assumed: if absent, set optional `GITHUB_INVOICE_MODEL` to an available suitable
text/chat model ID shown by the diagnostic and reopen the app. The diagnostic
does not enable billing, change the model automatically, or print your token.

Choose the client folder, scan, then click **Read client batch with GitHub Models
→ XML**. Selected-invoice reading is also available. The service receives local
PDF text/OCR, not raw PDFs. Shared buyer/seller and unit rules apply: retain
printed units, reason about missing units, mark assumptions, and never scale
quantity/rate/value or use medicine strength as sold mass. Every referenced
buyer ledger must have a matching exported master, with the exact ledger name
recorded in Batch_Report.json.

Quota/access/model stops retain successful reads. Remaining invoices try the
other configured providers among GitHub Models, Groq and Gemini, then Python.
All batch invoices receive XML for review in Tally. Incomplete facts remain in
the report/narration and may cause Tally rejection. Import Masters.xml first,
then Sales_Vouchers.xml into the matching selected Tally company.

Calls start at least 4.1 seconds apart, below the user's quoted 15 RPM. Actual
limits can differ by account/model and also include input/output token limits.
The quoted 150 RPD is not independently verified for this account and is not
a guaranteed invoice allowance. Requests cap output at 4,000 tokens; an
incomplete/truncated extraction is not cached as success and falls back.
No paid model/tier switch or billing change is enabled by this app.

Tests simulate API responses. Run the diagnostic with your own token to verify
live access. Share result lines if needed, never the token.

## Unreadable catalog response (Reader 7.7)

The HTTP decoder now supports bounded gzip/deflate decoding, and classifies
HTML, empty or other non-JSON pages without printing response contents. If the
catalog request fails, the diagnostic still tests the configured model with
ONE tiny JSON generation request. No invoice is uploaded. A successful tiny
request verifies model inference access even if the catalog remains blocked.
If generation returns 401/403, check token expiry and Models read permission
privately; a catalog parse failure alone does not establish an invalid token.

## Shared Groq-style reading (Reader 7.7)

Fresh GitHub Models requests reuse Groq prepare_invoice_payload messages
exactly, adapting only GitHub model/output-token transport fields. Source
verification, invoice normalization and complete Tally output remain shared.
Cached successes are retained. Correct input formatting does not bypass
GitHub authentication, access or response/network failures.

# Optional Gemini extraction

The local Python reader remains the default. No API request is made by scanning
or watching folders. **Read selected with Gemini** sends only the selected PDF,
after its confirmation dialog. This may use free-tier quota or paid usage,
depending on your Google project and model. The app cannot determine your
billing plan. Check current pricing, availability and data-use terms at
https://ai.google.dev/gemini-api/docs/pricing before sending customer documents.

## Windows setup

1. Create your private key at https://aistudio.google.com/apikey.
2. Search Windows for **Edit environment variables for your account**.
3. Under **User variables**, click **New**. Name: `GEMINI_API_KEY`.
   Value: your private key. Do not put it in chat, source files or a ZIP.
4. Close existing application and CMD windows, then reopen `Open_Invoice_App.bat`.
5. Scan your client folder. Select one unsuccessful invoice and click
   **Read selected with Gemini**. Read the upload confirmation before proceeding.
6. Click **Review selected invoice**, compare the result with the source PDF,
   correct missing/incorrect fields and save. Scan again to validate and prepare
   XML. Python still checks GST rates, component totals, invoice totals and
   company identity. It does not approve API output automatically.

The default model identifier is `gemini-2.5-flash`, which appears in the model
list supplied from your account and supports generateContent. Successful PDF
extraction and free-tier eligibility have not been verified live here. Flash
thinking is disabled for this structured extraction request to limit extra work.
If your project offers a
different PDF-capable model, add `GEMINI_INVOICE_MODEL` as another user variable
using its model ID from AI Studio, then reopen the app. Never use an untrusted
API proxy or put the key in a URL.

If you previously configured `GEMINI_INVOICE_MODEL`, edit its value to
`gemini-2.5-flash` or remove that variable to use the new default. Both
`gemini-2.5-flash` and `models/gemini-2.5-flash` are accepted. Close the app and
existing CMD windows before reopening the BAT.

If a key was pasted into chat or another public/shared location, revoke that
key in AI Studio and create a replacement. Save only the replacement in your
Windows `GEMINI_API_KEY` variable. The application does not embed supplied keys.

## Cost and failure handling

Successful extractions are cached against the PDF digest and model. Reusing the
same cached result does not call the API, even if the key is no longer present.
A changed PDF or model requires a new request. Failures are not automatically
retried; quota exhaustion, missing keys, model access and connection errors are
shown. Supported PDFs are up to 8 MiB. A multi-invoice PDF must be split into
individual invoices; the API must not merge them into one voucher.

The key is read from your environment and excluded from cache files and update
packages. The PDFs and extracted data themselves may be confidential: both the
provider and your local workspace receive them. Check the provider's current
terms when choosing a free or paid project.

## Verification limits

Offline tests verify request construction, cache reuse, key handling, source
changes, malformed responses and the approval requirement. **No live Gemini
request or accuracy benchmark has been performed in this cloud environment:**
it has no API key. Passing those tests is not evidence that Gemini correctly
reads the 166–185 batch or every future layout. Those 20 invoices now pass the
local Python reader independently of this optional API.

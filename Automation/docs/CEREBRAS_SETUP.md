# Cerebras invoice reader (Reader 7.2)

Current complete-batch import order (Reader 7.4): **Units.xml → Masters.xml → Sales_Vouchers.xml**, in the same selected Tally company. For missing-unit/stock exceptions, regenerate from cached reads, import units, retry masters, then retry only rejected vouchers.

Create an account/key at https://cloud.cerebras.ai. Keep the key private.
Do not paste it in chat or put it in a Python file.

On Windows, search **Edit environment variables for your account**. Under
**User variables**, create `CEREBRAS_API_KEY` with your key as its value. Close
the invoice app and old CMD windows, then reopen **Open_Invoice_App.bat**.

Run **Check_Cerebras_API.bat**. It lists available models and, if the configured
model is listed, makes one small JSON text request without uploading invoices.
The initial model ID is `llama-3.3-70b`; its current availability is not assumed.
If unavailable, set the optional User variable `CEREBRAS_INVOICE_MODEL` to a
listed text/chat model supporting JSON output. Reopen the app after changing it.
Do not select a model that requires billing unless you independently authorize it.

Choose the client folder and scan, then click **Read client batch with Cerebras
→ XML**. Cerebras receives extracted PDF text or local OCR, not a raw PDF.
Successful reads are cached separately. The latest successful provider supplies
the invoice fields; prior caches/manual corrections/history remain retained.

All providers use the same party and unit rules. Bill To/Buyer stays separate
from seller, Ship To, bank and signatory. Missing selling units can be inferred
from product/packaging context, with a reason and an assumed marker; printed
units and manual corrections take priority. Quantity/rate/value are not scaled.
Every referenced buyer ledger is exported in the consolidated Masters.xml and
recorded as buyer_ledger in Batch_Report.json. Import masters before vouchers.

If the selected API cannot finish, the queue tries other configured providers
among Cerebras, Groq and Gemini, then Python/OCR. All scanned invoices receive
XML; uncertainty remains in narration/report for review in Tally. XML creation
does not guarantee successful Tally import or correct GST filing.

Cerebras calls start at least 2.1 seconds apart, below the pasted table's 30 RPM.
Actual account/model request AND token limits govern acceptance. The user's
14,400 RPD / 1M-token table has not been independently verified for this account
or current model. A daily request limit is not a guaranteed invoice allowance.
HTTP 429 stops new calls to that provider while retaining successes. No billing
change, automatic paid tier, or repeated retries are enabled by the app.

Tests simulate provider responses. Live access and invoice accuracy require
your own account diagnostic and source comparison. Share diagnostic result
lines if needed, never your key.

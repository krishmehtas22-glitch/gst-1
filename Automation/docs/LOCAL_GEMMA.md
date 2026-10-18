# Free local invoice reading with Gemma

Install Ollama on Windows and download the local model with:

```
ollama pull gemma3:4b
ollama run gemma3:4b "Reply with: Gemma is working"
```

In BillSync UI 3.3, select **Gemma (local — free)** under Invoice processing.
Select an invoice and use **Process this invoice**, select several and use
**Process selected**, or use the process menu's **Process all client invoices**.
Each action retains the existing confirmation and selected-source limits.
Uploading, opening the app, refreshing and watching folders do not call Gemma.
Groq remains available; its payload, scheduling and existing behavior are unchanged.

Keep Ollama running. BillSync contacts only `127.0.0.1:11434/api/chat`, with no API
key, proxy or redirects. The model is fixed to `gemma3:4b`. BillSync does not
pull models, send cloud requests or fall back to cloud providers in local mode.
There is no per-request local API charge; your computer provides the processing,
memory and electricity. It does not connect to the unrelated Apps listed in Ollama.

Local batches keep at most **two requests in progress**, one invoice per request.
No unbounded queue of 100 requests is submitted to Ollama. Results remain in
source order, caches for the same source are serialized, budgets are shared
atomically, and result/checkpoint callbacks run sequentially. Stop prevents new
requests; requests already running can finish and retain their results. Ollama
may queue a request internally depending on its parallelism settings and your
hardware; two client requests do not guarantee two simultaneous model executions
or twice the speed. The app does not change Ollama's system settings.

The existing PDF text/local OCR recipe supplies document text and uncertainty
hints; the app does not send a raw PDF attachment or use new image/OCR code.
Gemma output passes through the same normalizer, master matching and Python XML
writer. Exact units, currency conversion and Tally import/numbering checks are
unchanged. Local candidates retain a source-review warning. A smaller local
model can misread invoices; compare seller, buyer, items, quantities, GST and
amounts before importing. Successful JSON is not proof of financial accuracy.

A source-matched local cache is reused. Confirmed human reviews stay authoritative.
Existing Groq caches are not substituted for an explicit new Gemma selection.
If local extraction fails, the existing pipeline retains available local/Python
fields and review diagnostics; a failed AI request is not a verified invoice.
No existing human review, source file or Tally voucher is changed automatically.

Development checks use mocked model/HTTP responses, including two overlapping
requests, stop, failures, budgets, cache reuse and exact field transfer. The
user's Windows Gemma runtime is not accessible from the cloud environment, so
live extraction speed and accuracy have not been measured here.

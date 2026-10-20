# OpenRouter in BillSync UI 4.1

Select **OpenRouter (free)** in Invoice processing. One invoice, selected invoices
and a confirmed client batch use the selected provider. Upload/list/refresh do not
start AI. No automatic switch to Groq, Gemma or another API is introduced.

Create an API key in your OpenRouter account. Set `OPENROUTER_API_KEY` privately in
Windows Environment Variables, then restart CMD and BillSync. Do not share the key
in chat or commit it. Existing Groq credentials are not used for OpenRouter.

The default is `openrouter/free`. An optional `OPENROUTER_INVOICE_MODEL` must be
an explicit `vendor/model:free` identifier or `openrouter/free`. Paid model IDs,
alternate model lists and plugins are rejected. Requests enforce zero prompt and
completion pricing. Free model availability, context limits and quotas are controlled
by OpenRouter and may change; unlimited access is not promised. The free router
can select different underlying free models, so output quality must be reviewed.

The current versioned extraction prompt, source checks, evidence, exact quantities,
currency conversion, unit/UQC rules and XML/Tally flow remain. Candidate masters
are included in fresh reads. Retained-read matching uses OpenRouter too, sharing
the confirmed request budget. Two-task cloud batching keeps 13-second request-start
pacing; provider access/quota failures stop new requests and cause no automatic retry.

Verified V1 OpenRouter saved reads migrate locally; new reads save checksummed V2
documents. These cache checksums are file-integrity controls, unrelated to GSTIN
checksum validation. The accompanying user-authorized GSTIN policy removes check-digit rejection,
while retaining shape/state checks and printed identities. A missing Tally company
GSTIN is a review warning, not evidence the company is unregistered. Incomplete AI
extraction still requires processing or a saved human review before import.

The separate `Test_MD_Extraction.py` also accepts `--provider OpenRouter --run-ai`.
It uses the uploaded MD prompt and returns raw AI output without GSTIN validation,
master matching, production-cache changes, XML or Tally import.

Installation backs up prior source. Offline tests use fake provider/Tally replies;
they do not prove live free-model extraction accuracy or solve local Ollama crashes.

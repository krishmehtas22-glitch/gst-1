# Uploaded-MD output experiment

This standalone experiment uses the uploaded extraction MD's system-prompt block
verbatim and supplies its JSON output example in the user message. It tests one
selected PDF/PNG/JPG/JPEG. Master candidates are omitted in this initial test.

It does not implement every rule in the main rules MD. It shows model output before
the application's validators: no GSTIN checksum validation/correction, accounting
normalization, production cache updates, XML generation or Tally writes. The working
app and its GSTIN checks remain unchanged. Financial/XML accuracy is not measured.

From the existing reader source folder, use its Python environment:

```bat
.venv\Scripts\python.exe Test_MD_Extraction.py --provider Groq --run-ai
```

Choose one document in the file picker. Groq uses the existing private environment
key and may consume credits. At most one request is attempted; no retry is made.
For installed local Gemma, substitute `--provider Gemma`. Neither command downloads
models or falls back to another provider. Omit `--run-ai` to prepare a request only.

Results are stored in a new `MD_Output_Tests` subfolder and opened in Explorer:

- `Request.json`: actual submitted messages, including the source text.
- `AI_Response.txt`: exact returned model content, including malformed JSON.
- `AI_Output.json`: parsed output only if the returned text is valid JSON.
- `Provider_Response.json`: provider response and completion status.
- `Test_Report.json`: provider, source fingerprint, request attempt count and limits.

The embedded MD is reference data. Its Python-postprocessing/retry instructions are
not executed in this raw-output experiment. A valid JSON response is not evidence
that invoice facts were read correctly. Inspect against the original document.

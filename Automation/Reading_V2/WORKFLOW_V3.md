# Separate invoice reading / AI / review XML workflow

The desktop app, working UQC/import button, provider recipe used by that app,
and existing financial XML writers are unchanged. This workflow is experimental
and produces separate review files. It never contacts Tally or modifies current
client exports, financial history or saved source approvals.

Run using the existing reader virtual environment:

```bat
.venv\Scripts\python.exe Read_Invoice_V3.py "F:\Downloads\dummy sales invoice\CLIENT 32" --xml
```

Opt-in AI (maximum 50 requests, no retries after unknown connection failures):

```bat
.venv\Scripts\python.exe Read_Invoice_V3.py "F:\Downloads\dummy sales invoice\CLIENT 32" --xml --ai-provider Groq --max-ai-requests 50
```

Use `--ai-provider Gemini` instead or append it after Groq to use an already
configured Gemini key after a definite primary quota failure. Do not paste keys
in chat; existing private environment variables are used. No provider is added
or billing enabled. The default request limit is zero.

Existing matching human reviews and selected successful AI caches are read
without updating them or consuming quota. New evidence-checked AI results have
a separate cache and remain proposals. Partial or rejected answers retain local
reading. An inferred unit must include its reason; missing numerical quantities
and amounts remain missing. Every printed numerical AI value requires matching
source tokens. Evidence presence does not prove party/row completeness.

CII attachments are considered only after visible-source agreement checks.
Schema-valid sample attachments can contain different invoices: those are
rejected and retained in the report as disagreements. Foreign VAT is not relabelled
as CGST/SGST/IGST. Non-unit price bases are retained without inventing rates or
scaling quantities. Currency conversion/tax treatment remain explicit review work.

A new `.invoice_app/reading_v3_runs/` folder contains per-document evidence JSON,
Workflow_Summary.json and a separate XML workspace. Units, stock references,
voucher count, buyer ledgers and debit/credit balance are checked. The summary
also lists date-recovery and missing-total concerns. Structural success does
not prove complete financial correctness or live Tally acceptance. These XML
files are not approved for automatic import. Separate source clients stay separate.

## Public evaluation limits

The 50-case suite was downloaded from public GitHub sample collections, screened
visually and frozen with source URLs and SHA256 hashes. It includes language,
currency and scan variations sharing template families; it does not establish
50 unrelated layouts. The dedicated FATURA layout dataset download was blocked
by proxy 403 from Zenodo/Hugging Face even after network permission was granted.

Only 17 cases supplied usable independent publisher annotations (75 measured
header fields). The other cases have incomplete/manual references; embedded
XML alone is not independent visual ground truth. Arabic names and ambiguous
currency/date information still need work. Actual AI extraction was not tested
because this cloud session has no provider key; transport tests are contract
checks, not AI-accuracy measurements. No 95% full-invoice accuracy claim is made.

To complete live AI validation here, configure GROQ_API_KEY privately in cloud
environment settings. The required binding/domain draft was saved; review/save
and publish the environment to apply it. Access to zenodo.org/huggingface.co
must also be added without removing existing allowed domains. Until those
prerequisites are available, keep this workflow separate from production.

# Desktop Reader 7.27: AI first, Python XML second

Superseded by the user's explicit cost-control correction in Reader 7.28:
startup/refresh/watching only list PDFs. AI-first processing applies only after
the user chooses files/a client batch and confirms the request scope. See
`MANUAL_AI_READER_7_28.md`. Do not restore automatic AI analysis.

The desktop's normal Scan action and folder watcher now use this order:

1. Python discovers source PDFs and prepares their text/OCR for the chosen AI.
2. AI extracts invoice meaning into the existing structured JSON schema:
   seller/buyer names, addresses, GSTINs, states/country, invoice number/date,
   line descriptions, quantities, selling units, rates, tax treatment and totals.
3. Python uses the saved AI result, preserves human corrections, validates and
   maps units, and calls the existing Units/Masters/Sales XML writer.
4. The existing Import ALL action remains a separate explicit user action.

AI is asked for source fields, never Tally XML. The shared provider text/OCR
recipe and prompts remain unchanged. Printed units outrank inferences; missing
units can carry the AI's product-context reasoning. Ambiguous/missing buyer,
seller or tax facts must remain explicit review work, not invented identities.
PDF text/OCR preparation may use the existing local parser for evidence/fallback;
local parsing is not represented as AI semantic extraction.

The main button is `AI read and generate XML`. Folder watching calls this same
method. `Automatic AI` selects the primary provider, default Groq, and saves that
choice in the selected root's `.invoice_app/ai_first_settings.json`. Existing
configured providers are the only fallbacks; OpenRouter remains free-only and
no billing is enabled. Their private environment-variable keys are unchanged.
No new runtime dependency or API-key setup is installed by this change.

Successful digest-bound AI caches are terminal; they do not consume another
request. Approved source reviews are terminal too and are reported separately
as human review, not AI. New PDFs or changed PDF contents need AI extraction.
One shared conservative new-attempt budget covers the pending sources across
all providers. Confirmed existing source approvals and financial history are
not overwritten. An invalid saved review requires attention and is not uploaded
to AI to replace it.

Normal Scan/folder watching do not silently confirm documents as fictional just
because the test-mode checkbox is on. Explicit selected/batch AI dialogs retain
their existing test-data confirmation. Selected reading spends a fresh attempt
only on the selected PDF, with other client sources using retained/local data.
Batch reading and automatic scans process all sources in the selected scope.

For these desktop actions, the AI stage finishes before the Python XML writer
starts; no starting placeholder XML is emitted while new AI reads are pending.
Successful AI cache writes remain durable throughout the stage. Stop, quota or
provider failure preserve those reads, then Python prepares complete review XML
for the source scope. Local/review fallback is identified in the UI, the existing
Batch_Report.json/narration, and `.invoice_app/AI_First_Last_Run.json`. It is not
called an AI extraction. This report separates attempts, AI reads, manual reviews,
fallbacks, prepared vouchers and zero Tally imports.

If no AI key/service is available, the app cannot perform AI analysis. It reports
that fallback instead of claiming AI success. XML availability/structural checks
do not prove financial accuracy, 95% extraction accuracy or live Tally acceptance.

The watcher acknowledges its own cache/unit-estimate writes, avoiding a repeated
AI scan caused only by those writes. PDFs arriving during processing still
trigger the next stable scan. Manual Scan remains available for another attempt.

Close the app and run `py Apply_AI_First_Reader_7_27.py` in the existing source
folder. It upgrades known Reader 7.25/7.26 files, supplies the earlier production
goods-table and selected-AI fixes where needed, backs up replaced source, and
refuses unknown local edits. It does not itself read/upload invoices or generate
XML. Restart `.venv\Scripts\python.exe Invoice_Desktop.py` and verify the title
is `Reader 7.27`. A frozen EXE requires a Windows rebuild.

The locked Import ALL method/button, Tally transports, unit catalog/normalizer,
XML writers and routing/GUID rules are unchanged. The separate experimental V3
reader/teaching workflow remains separate; this change uses the established
production provider and XML code, not the prototype extraction pipeline.

Tests cover actual provider-wrapper contracts with fake generation responses,
AI-before-XML ordering, new-file-only calls, saved/manual reuse, limited-provider
fallback, Stop, worker/report failure, client scope and watcher triggers. Live
provider extraction accuracy is not measured by those tests.

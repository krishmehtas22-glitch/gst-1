# OpenRouter: free-only invoice reading

Create a private key at https://openrouter.ai/settings/keys. In Windows search,
open **Edit environment variables for your account**, then add a **User variable**:

- Name: `OPENROUTER_API_KEY`
- Value: your privately copied OpenRouter key

Never paste the value into chat, source files or a ZIP. Close/reopen the reader or
CMD after saving. Optionally run **Check_OpenRouter_API.bat** from the program
folder: it lists free catalog models and sends one small free JSON test, not an
invoice. Share only the diagnostic lines, never your key.

The default model is **openrouter/free**, OpenRouter's free-model router. To select
one fixed free model, set `OPENROUTER_INVOICE_MODEL` to its exact catalog ID ending
in **:free**. Paid model IDs are rejected locally before a request. Request routing
also caps prompt/completion provider prices at zero, with no paid model alternatives
or plugins. No billing, credit purchase or automatic paid-model fallback is enabled.
A free key does not mean unlimited access: model availability, your account quota
and provider limits still apply. Check those in your OpenRouter account.

Use **Read client batch with OpenRouter (free) → XML**, or its selected-invoice
button. The reader uses Groq's shared text/local-OCR prompt and the existing
invoice normalizer, stock/unit rules and Tally XML writer. Successful caches are
retained at `.invoice_app/openrouter_extraction`, including after quota expiry.
Batch attempts share the same maximum of N fresh attempts total for N batch invoices across
ALL configured providers; unused budget may go to other configured APIs, then
Python. Press Stop to keep completed reads and prepare XML for the rest.
OpenRouter HTTP 402/429 stops further fresh requests; paid routes remain disabled.

Existing EXEs must be rebuilt with **Build_Windows_EXE.bat** to include this provider.
Choose your existing invoice folder in the new EXE; keep `.invoice_app` intact.
Cloud regression tests simulate responses. Live access/accuracy requires running
the diagnostic with your own privately configured key on Windows.

# Recovering from an unfinished Groq read

`local fallback` means that AI extraction did not complete; it does not establish
the cause. Do not assume a bad API key or quota exhaustion without the provider
error. Failed reads remain review drafts, and cannot be approved with the
import-warning acknowledgement alone.

This update retains each recorded provider error in AI_First_Last_Run.json, the
completion status, and the corresponding AI extraction issue in workflow review.
No new network request runs to diagnose an old failure, and processing does not
automatically retry or send an import.

For an unfinished AI extraction:

1. Select the AI extraction issue to see its provider reason and recovery steps.
2. Resolve that provider error, then explicitly Analyse the affected invoice; or
   use Edit invoice, compare all fields with the source, correct them and Save
   changes to XML to record a human review without AI.
3. Wait for XML regeneration and reopen Import. An old open import plan must not
   send stale XML after an edit.

Saving one human review approves only that source. It does not approve the other
invoices in a complete client batch. With Include complete client batch selected,
all included invoices must have a completed AI read or saved human review.

For warning-only review (invalid printed GSTIN/state or other invoice-data
issues), the acknowledgement switch starts off and the import button is disabled.
Explicitly turn on the switch to enable Import to Tally anyway. This retains the
printed values and records the decision. It does not repair invalid test GSTINs
or establish that Tally will accept them. Correct facts in the invoice editor
when the source provides them; do not invent registration details.

Current sources, saved reviews, master snapshots and output hashes still have to
match. Those integrity checks cannot be bypassed by the warning acknowledgement.

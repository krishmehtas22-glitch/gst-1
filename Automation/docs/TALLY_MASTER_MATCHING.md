BillSync UI 2.2 — optional Tally master matching

1. Choose ONE client (or one of its invoice rows), then Read Tally masters.
2. Connect, choose the correct source company, and import ledgers, items & units.
   The saved snapshot is selected for that client. An existing saved snapshot
   can also be opened and selected with Use snapshot for [client]. This action
   does not analyse invoices, spend AI credits, generate XML or write to Tally.
3. Process this invoice / Process selected / Process all client invoices runs
   only after the original AI confirmation. Relevant master names, GSTINs,
   HSN/rate details and units are then supplied to Groq as matching candidates.
4. Right-click an invoice and choose Tally master assignments to see reused
   party, stock and unit names. Other entries show Current creation method.
5. Import ALL still sends Units -> Masters -> Vouchers once, with the original
   receipts, unit protocol, stop/rejection handling and company dialog. Select
   exactly the company from which these masters were read. A different target
   is rejected before ANY import request is sent.

New Groq reads can return extraction and optional master references in the same
request. Matching choices are stored separately from the extraction cache.
For cached or manually reviewed selected invoices, matching may use an unused
attempt within the existing confirmed cap. Saved extraction/approvals are not
discarded or reread. Matching requests retain Groq pacing and stop on access/
quota rejection. No startup, refresh, watch, upload or snapshot read calls AI.
AI_First_Last_Run.json reports additional matching attempts separately within
the total confirmed cap. Stop prevents subsequent requests; an in-flight request may finish. Existing
matching decisions are reused only for the same client, source, invoice facts
and exact snapshot checksum. Editing invoice facts invalidates old decisions.

Python checks that IDs were actually offered, confidence is at least 0.98,
GSTINs do not conflict, and simple units represent the same selling measure
without quantity/rate conversion and can hold the quantity's decimal precision.
Stock reuse additionally requires matching HSN and compatible known GST rates.
Unknown, conflicting or multiple historical rules fall back to creation.
High model confidence is a selection threshold, NOT measured accuracy.
The candidate list is bounded for request size; a master not retrieved into the
list cannot be selected. An unreadable/ambiguous document still needs review.

Reused party/stock/unit definitions are not recreated or altered in the XML.
Voucher references and new stock BASEUNITS use their exact Tally names/symbols.
Printed invoice identity, buyer/item descriptions, quantities, numeric rates,
amounts, tax postings and GUIDs remain unchanged. Stock references are applied
only when the existing writer posts inventory; accounting-only exports and
incomplete invoices retain the current accounting-voucher method. New fallback names avoid
overwriting a conflicting existing party/stock name by adding readable invoice
details. Unmatched units retain the existing catalog/creation/transport method.
Original sales/tax ledger selection and accounting calculations remain in place;
this feature does not choose arbitrary replacement sales/tax ledgers.

The XML envelopes contain local dependency/company metadata which the app strips
before sending native XML to Tally. Use the app's Import ALL for these matched
batches so company and external-master dependency checks are applied. Old
unbound batches keep their previous transport and byte-for-byte XML behavior.

Binding: .invoice_app/tally_master_bindings (one explicit snapshot per client).
Matches: .invoice_app/tally_master_matches (separate JSON sidecars).
Snapshots remain read-only; replacing/refreshing the selected snapshot invalidates
old matches. No customer documents, snapshots or API keys are in this update.
Original hashes are retained; TALLY_MASTER_MATCHING_CHANGE.json records the
narrow authorized exceptions. Before_Tally_Master_Matching.zip and the local
source installer's automatic backup preserve prior code.

Tests use synthetic/mocked masters and AI responses, real generated XML and
desktop controls. They do not prove live Groq accuracy or live TallyPrime 6.2
acceptance. Refresh snapshots after renaming/deleting masters in Tally. Missing
or changed live masters may produce normal Tally import exceptions; the app
does not fabricate success, recreate matched masters or retry an ambiguous import.

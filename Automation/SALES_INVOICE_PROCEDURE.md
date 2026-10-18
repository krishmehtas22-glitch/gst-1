# Sales invoice to Tally XML

Process invoices only through the explicit Groq or local Gemma action and its
confirmation. Upload, refresh and startup still only list documents. Saved human
corrections and successful AI caches remain reusable without a fresh AI call.

1. Confirm that the document is a sales invoice. Orders, quotations, delivery
   notes and credit/debit notes must not be exported as Sales vouchers.
2. Read the printed invoice number and invoice date. Never substitute due date,
   shipping date, today's date or a generated serial number.
3. Read seller name, GSTIN, address and state from the supplier panel/masthead.
4. Read the legal buyer's name, GSTIN, registration, address and state. Buyer
   labels can include Bill To, To, Invoiced To, Supplied To, Recipient and similar
   wording. Prefer the billed buyer over a different Ship To recipient. A
   shipping-only panel is usable only when it unambiguously identifies the buyer.
5. Read place of supply separately; it need not equal the buyer's state.
6. Read explicit reverse-charge status. Zero GST does not establish RCM. For a
   confirmed taxable domestic RCM sale, supplier-payable GST is zero. Printed
   nonzero GST or inconsistent totals require correction, and leave previous XML
   intact. Nominal item tax rates remain available for stock-master validation;
   new RCM stock masters carry reverse-charge applicability. This does not create
   the recipient's purchase-side RCM liability entries.
7. Read all stock/service rows: description, HSN/SAC, quantity, unit, price,
   taxable value, separate CGST/SGST/IGST rates, and printed row total if present.
   Do not invent HSN/rates or treat tax summaries as items.
8. Reconcile taxable values, tax components, round-off and grand total. Keep
   printed values for review instead of silently repairing discrepancies.
9. Reuse compatible masters from the explicitly bound company snapshot. Reject
   incompatible identity, HSN, tax, reverse-charge or unit/precision matches. New
   masters use the existing generation path and plain names; no existing Tally
   master is silently changed. Missing units may use recorded product/packaging
   reasoning, with the existing formal-name/UQC and exact-quantity rules.
10. Double-click the invoice to edit all extracted fields. Invoice details now
    includes document type and RCM Yes/No. The Items tab has a horizontally
    scrollable editable stock/HSN/unit/GST table and the existing detailed item
    fields; both use the same variables. Save changes to XML regenerates locally,
    without another AI request.

Review Units.xml, Masters.xml, Sales_Vouchers.xml and Batch_Report.json before
explicit Import ALL into the selected company. The existing Units → Masters →
Sales order, numbering check, source verification and exact-output review remain.
XML generation and offline tests do not prove live TallyPrime import acceptance
or GST-return correctness. Ambiguous AI readings still require source comparison.

The updated source installer is `Install_BillSync_Source.py` at repository root.
The old raw URL pinned to commit 052dbf2 continues to install the old release;
use the installer from the revision containing this change. It backs up replaced
code under `.invoice_app/code_backups` and preserves client documents/history.

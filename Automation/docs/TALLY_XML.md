# Native Tally XML import

XML is now the default output. Excel templates are not needed for this workflow.
Existing client.json files without output_format also default to XML. Set
`"output_format": "xml"` explicitly if a prior config selected Excel.

Official source documentation inspected during implementation:

- https://help.tallysolutions.com/sample-xml/
- https://help.tallysolutions.com/xml-integration/
- https://help.tallysolutions.com/understanding-tally-xml-tags/
- https://help.tallysolutions.com/getting-started-with-tally-integrations/

The official Sample XML document supplies the Import Data envelope, Create master
records, simple units, and Sales item-invoice structure. Customer debit is a
negative Tally amount (ISDEEMEDPOSITIVE Yes); inventory sales and output taxes
are positive (No). Each item's accounting allocation holds its sales credit.
There is no extra standalone sales credit that would double the posting.

## Files generated per client

Run main.py after configuring the company and placing PDFs directly in the
client folder. The engine creates:

- imports/Masters.xml, when new masters are required.
- imports/Sales_Vouchers.xml, containing one Sales voucher per valid invoice.
- imports/manifest.json, identifying company, invoice keys, file checksums,
  required masters and import order.
- reports/validation.json and other separate review/accounting reports.

The masters file orders simple units, custom stock groups, ledgers and stock
items. Required customer ledgers contain GSTIN/registration/state; output-tax
ledgers have separate GST duty heads. Stock items include HSN/SAC and GST rates.
A normal 18% item has master rates CGST 9%, SGST 9%, IGST 18%, so the same item
can be used for either intra-state or inter-state invoices. Actual vouchers
contain only the tax components applicable to the specific invoice.

No opening stock is fabricated. Vouchers use the built-in Main Location and
Primary Batch from the official example. Custom godowns, tracked batches,
serial numbers and compound units need a separate extension. The present stock
invoice output is for goods; service SAC/invoice requirements need a separate
profile. Do not use goods inventory XML for services.

## Import in a dummy Tally company first

1. Create/select the correct dummy company in TallyPrime. Its name must match
   client.json exactly. Enable inventory/accounts and the correct Indian GST
   company registration. Company creation itself is not performed by this tool.
   For the explicit demo profile, use a disposable company `abc`, state
   Maharashtra, and the synthetic seller GSTIN shown in that client's
   `client.json`. It is test data, not verified registration. Keep the company
   financial year/period open for the October 2026 invoice dates. All demo
   substitutions are listed in reports/demo_adjustments.json; never use this
   company or these files for GST filing.
2. Configure Sales voucher numbering to preserve the source invoice number
   (for example, Manual numbering), and confirm the numbering configuration.
3. Use the TallyPrime Import menu for **Masters**, selecting that client's
   imports/Masters.xml. If masters already exist, choose the option that ignores
   them rather than modifying/overwriting them. Check the import result/log.
4. After all required masters succeed, import **Transactions** using that
   client's imports/Sales_Vouchers.xml. Check the import summary and Tally's
   Day Book/Sales Register and ledger/inventory allocations.
5. Check customer GSTIN and place of supply, HSN, taxability, stock rates, GST
   calculation and GST reports in your target TallyPrime release. GST master
   fields can vary by release; export one manually entered master and voucher
   as XML if your release needs a different tag profile. Keep originals and
   share the sample/error report for a targeted adjustment.
6. Record actual imported/rejected/pending results through main.py confirm-import
   as documented in README.md. Workbook/XML generation alone never marks import
   success. Without confirmation the next run retains the pending export batch.

Do not repeatedly import a pending batch. Stable per-company voucher GUIDs are
generated, but their duplicate behavior also depends on Tally import settings.
The application checks its own history and, for existing companies, a complete
fresh normalized Tally snapshot. That does not automatically read a running
Tally instance. Never select settings that overwrite existing records.

## Scope of validation

Automated tests parse the generated XML, check the import envelopes, master
dependency order, references, debit/credit signs, totals, single vouchers with
multiple items, GST components and rates, Unicode/escaping, stable identities,
repeat runs, client isolation, and import-result history. These tests do not run
TallyPrime: a real dummy-company import and release-specific GST report validation
are still required. Real PDF layouts not covered by the text extractor need
reviewed JSON records or an extraction adapter.

Unit Quantity Codes are configured per client. Common codes map to their native
Tally labels (for example NOS to NOS-NUMBERS). For another unit, set its exact
label using the optional tally_uqc field after verifying it in Tally. Unknown
codes are flagged, not guessed. The unit's configured decimal precision must
support the invoice quantities.

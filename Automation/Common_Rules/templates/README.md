XML is the default output and does not use this folder or Excel templates.
See ../../docs/TALLY_XML.md for XML import instructions.

This folder is only for the optional Excel exporter (output_format: excel).
Official Excel workbooks and completed mappings are not bundled. The Excel
exporter refuses to produce files without verified source workbooks and
companion mappings; no replacement Excel layout is invented.

Required official sources:

- Sales Voucher with GST, e-Way and e-Invoice Details
- Sales Vouchers in Multiple Rows
- Ledger with GSTIN
- Stock Items with GST Details
- Simple and Compound Units
- Stock group mapping if custom stock groups are used

Download and extract the workbooks and mapping files from:
https://help.tallysolutions.com/download-sample-excel-files-with-data-for-import/

Inspect both Sales examples to choose the correct multi-item structure. Read the
actual ReadMe sheets and mapping XML before registering any file. Run:

    python main.py inspect-template Common_Rules/templates/<source.xlsx>

Then implement/review `registry.json` keyed by `ledger`, `unit`, `stock_item`,
`sales` and optionally `stock_group`. Each specification must include:

    file, source_url, sha256, mapping_file, mapping_sha256,
    verified: true, reviewed_by, blocks

Each block identifies:

    sheet, header_row, headers (the complete exact ordered header list),
    data_start_row, sample_end_row, mandatory_headers, stream, columns

`columns` maps **actual official column headers** to dotted canonical data paths
or `{"constant": <approved value>}`. Do not guess official column names or set
`verified` without reviewing the workbooks and mapping. `sample_end_row` is the
last example-data row, so footer instructions and ReadMe are not erased.

Master stream: `masters`; fields are documented by `required_masters()`.
Sales streams: `invoices`, `inventory`, `accounting`, `rows`. Inventory rows
have `item.*`; accounting rows have `allocation.ledger`, `allocation.debit`,
`allocation.credit`; both include the parent invoice fields, invoice_key,
voucher_type, company_name and sales_ledger. `rows` contains inventory then
accounting rows for each voucher. Choose streams according to the verified
official repeated-row mapping; do not split an invoice into multiple vouchers.

The adapter is a starting point, not a verified Tally mapping. Once official
workbooks are supplied, their date, sign, amount, boolean and repeated-row
conventions may require adapter changes. A synthetic test fixture only tests
workbook preservation; it does not demonstrate a successful Tally import.

Import in dependency order: units, stock groups if needed, ledgers, stock items,
then sales. Use a dummy Tally company and its import logs to verify the completed
mapping before production use. The current output filename Sales_Output.xlsx
is provisional until the user's earlier sample and filename are confirmed.

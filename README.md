# Sales invoice automation

See [setup, usage and current limitations](Automation/README.md).

The central Python engine is in `Automation/`. XML is now the default Tally output.
Extract `Sales_Invoice_Automation_XML.zip` directly into
`F:\Downloads\dummy sales invoice`; invoices may stay directly in `client 1`.
Each client receives Masters.xml and Sales_Vouchers.xml in its imports folder.
Automated tests verify XML structure, master references, accounting, GST amounts,
duplicates and client isolation. A live dummy-company Tally import and validation
against the user's actual PDFs still need to be performed.

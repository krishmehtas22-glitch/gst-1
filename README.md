# Sales invoice automation

See [setup, usage and current limitations](Automation/README.md).

The central Python engine is in `Automation/`. XML is now the default Tally output.
Extract `Sales_Invoice_Automation_XML.zip` directly into
`F:\Downloads\dummy sales invoice`; invoices may stay directly in `client 1`.
Each client receives Masters.xml and Sales_Vouchers.xml in its imports folder.
Automated tests verify XML structure, master references, accounting, GST amounts,
duplicates and client isolation. The supplied 25 marked dummy PDFs have been
tested in explicit demo mode using company abc and unit Nos. Use `init-demo-client`
as documented in Automation/README.md for these unassigned/synthetic GSTINs.
A live dummy-company Tally import still needs to be performed.

# Plain party and inventory names

This authorized patch removes the generated `[batch hash]` suffix from party
ledger and inventory master names and their corresponding voucher/report
references. Ordinary names now appear exactly as extracted, for example
`Nagpur Packaging Depot` and `Corrugated boxes`.

A batch hash previously also separated incompatible definitions. Same-name items
with different units remain separate using readable names such as `Material (PCS)`
and `Material (KG)`. Further HSN/tax variants use their source details. Same-name
parties with different GSTINs use their GSTINs; address/state variants also remain
separate using those source details. Printed names take precedence over
generated variant labels. Distinct definitions must never be merged silently.

AI extraction, invoice values, units/UQC, quantities/rates, taxes, dates, voucher
GUIDs and actual inventory batch/godown allocation XML remain unchanged. Desktop
versions 7.29 and 7.30, their controls and the locked Import ALL transport remain
unchanged. The original source fingerprints remain in WORKING_READER_LOCK.json;
this explicit exception is recorded separately.

After installing and reopening the Python reader, double-click an invoice and
choose Save changes to XML to regenerate that client's XML locally from retained
values without new AI requests. Old XML backups, AI caches and history remain.
The patch does not rename existing Tally masters/vouchers or trigger any import.
Review existing imported entries in Tally before importing regenerated files.

Validation includes synthetic XML from the pre-change exporter. After removing
only the old generated name suffixes from that reference, the complete Units,
Masters and Sales XML match the updated exporter. Additional tests cover
incompatible unit/GSTIN variants and collisions with printed names.

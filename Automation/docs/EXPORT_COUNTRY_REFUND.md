BillSync UI 2.1 — export country and invoice-IGST reference

The invoice editor already contains Buyer Country. AI extraction and manual
editing remain unchanged. For an export, enter/review the actual foreign country
there before regenerating XML. Known country aliases are normalized; a missing,
unknown or Indian country, or a conflicting Indian place of supply, blocks new
batch XML before any current files are replaced. Review the affected invoice and
save again. Existing XML is retained; it has not acquired the new country until
regeneration succeeds. A mixed batch also waits for the incomplete export.

Export buyer ledgers receive COUNTRYNAME and LEDSTATENAME=Not Applicable.
Export vouchers receive COUNTRYOFRESIDENCE, STATENAME=Not Applicable and
PLACEOFSUPPLY=Outside India, using the existing strict writer's country tags.
Financial values, allocations, quantities, rates, units and voucher identifiers
are preserved. Domestic XML is checked byte-for-byte against the previous writer.
Import ALL transport and destination-company selection are unchanged.

The new Potential IGST refund column shows positive invoice IGST in INR only
for an export marked with payment of IGST, with a valid country, explicit zero
CGST/SGST and basic amount/currency checks. It is labelled unverified. An invoice
does not prove actual tax payment, statutory refund eligibility, an approved claim
or government payment. The app does not submit claims, calculate eligibility or
post a refund-receivable ledger. For LUT exports a possible input-ITC refund is
not calculated from sales invoices; no zero-entitlement claim is made.

Select an export and click Refund review (also in the right-click menu). Record
Unreviewed, Eligibility reviewed, Claimed or Not eligible. Eligibility reviewed
requires a note of the review basis; Claimed requires a separate positive amount
no greater than invoice IGST and a claim/shipping-bill reference. These are manual
user records, not verification by the app. Edit invoice / country opens the
original editor. Refund review itself does not generate XML or send AI requests.

Manual review files live in .invoice_app/export_refund_reviews. They are separate
from invoice amounts, AI caches and XML. Changes to the invoice's tax/country/
amount identity start a new review rather than reusing the old approval.

Backups/Before_Export_Country_Refund.zip retains the prior code and checksums.
The source installer also backs up replaced local files before installing.
EXPORT_COUNTRY_REFUND_CHANGE.json records the single authorized existing-engine
file change without replacing the original lock fingerprints.

Live TallyPrime 6.2 is not available in automated tests. After import, verify the
country and export sales-ledger GST nature/GSTR-1 treatment in Tally before
filing. Country tags and structurally valid XML do not certify GSTR-1 reporting
or successful live import. Distinct ship-to and buyer countries require review;
the app uses the existing invoice Buyer Country field, not an invented country.

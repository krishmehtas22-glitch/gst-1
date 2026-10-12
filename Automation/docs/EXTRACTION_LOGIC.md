# Reader 6 extraction logic

## 1. Preserve document structure

The PDF reader compares ordered embedded text with geometric layout text produced
from the PDF's text positions. It prefers complete, consistent identity and item
fields rather than assuming the text stream's order matches the printed columns.
OCR is used for image-only pages; OCR-derived values continue to require review.

Party blocks and item tables are read from the original layout text. A separate
label-splitting view reads scalar fields. Splitting `Date:` away from an adjacent
buyer name therefore does not destroy the buyer's column context.

## 2. Read values according to their type

GSTIN is a bounded identifier, not every character after a colon. In
`Seller GSTIN: 27ABCDE1234F1Z5 | State: Maharashtra (27)`, the GSTIN ends after
its 15-character token. Metadata following it remains separate. A longer
malformed identifier is not silently truncated into a valid one.

Dates, monetary totals, currency and destination fields have their own
normalization and validation. Invoice numbers can also be read from a clear
header such as `Invoice DM/26-27/0106`; several different candidates cause review.

## 3. Identify parties independently

Explicit seller/buyer roles take priority. Side-by-side buyer and invoice-detail
columns are processed independently. Seller banners are checked against printed
GSTIN and matching signatory evidence. Harmless legal-suffix/authorization
formatting is normalized; a genuine conflict remains visible. Missing seller
names may use a verified local supplier identity under the restrictions described
in README.md. Buyer names are never substituted for seller names.

## 4. Reconstruct item rows from semantic headers

Headers identify description, HSN, quantity, unit, rate, value and tax fields,
even with different column order. Currency annotations such as RATE INR and
AMOUNT INR are handled as annotations, not separate field definitions.

Ordinary aligned cells are read first. If spaces inside a description break the
usual split, column positions from the header provide a fallback. Numeric
quantity/rate/value checks must still succeed. Item extensions are subsequently
checked against quantity times rate and against the invoice taxable total.

Printed units or quantity suffixes take priority over keyword suggestions.
Missing units may be estimated by the existing local unit resolver, always
marked estimated and editable. An omitted unit cannot be certified from the PDF.

## 5. Decide the accounting basis before creating masters

If item tax rates are printed, validate each item's tax and generate inventory
vouchers under the existing rules. Explicit exemption/LUT without payment has
zero payable GST. An export with payment uses IGST and never a domestic state
split.

If no item tax rates are printed but the invoice provides all three GST amounts,
**Summary GST accounting**, when explicitly enabled, can use those exact invoice totals. The code validates
item extensions, total taxable value, gross total, GST sign, buyer/seller identity
and domestic state split, then generates an accounting sales voucher. It does
not infer a uniform GST rate for all items and does not move stock or create
stock masters for those vouchers. The accounting basis is recorded in source
records, history fingerprint, voucher narration and desktop status.

This option is off by default, as requested: item-rate review is required before inventory output.
Partial printed item rates do not qualify for this fallback. Inconsistent totals
or tax geography remain blocked. Unknown fields remain explicit.

## Verified result and limits

Before these changes, Reader 5.5 generated 0/20 XML vouchers for the supplied
Sales_Invoice_106 through 125 batch. Reader 6 extracts all 20 invoice numbers,
sellers and buyers, and all 39 item rows. Tests compare quantities/rates/values
and each CGST/SGST/IGST/gross amount with independent ordered PDF text.

With the optional summary fallback enabled, all 20 generate balanced XML. Fifteen use invoice-summary accounting; two LUT
exports use the existing accounting export view; three exempt invoices use item
view with zero payable tax. All twenty contain estimated units because units
are omitted. This result is from a batch used to improve the reader; it is not
proof of accuracy on every future layout, a live Tally import, or verified
GSTR-1 reporting. The system does not need an API for this batch.

With the requested default (inventory item-rate review), all 20 are extracted,
but 15 need item GST rates and 5 prepare XML automatically. A reviewed rate set
enables the inventory voucher, checked against source tax and invoice totals.

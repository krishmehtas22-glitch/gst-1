# Invoice numbers in Tally Sales vouchers

The reader already writes the source/app invoice number into both
`VOUCHERNUMBER` and `REFERENCE`. Tally's destination voucher-type configuration
controls whether the supplied number is retained. Automatic numbering can
replace it with a serial number even when the XML contains the invoice number.

Before an explicit Import ALL, the app now reads Voucher Type names and
NumberingMethod from the selected company. Every voucher type referenced by the
Sales XML must be returned once, with Manual numbering. Automatic, other,
missing, ambiguous or unreadable settings stop before any units, masters or
vouchers are written, and show setup instructions. A master-only plan does not
need this check. The lookup is read-only; it runs only during explicit import.

In each destination company in TallyPrime:

1. Press Alt+G > Alter Master > Voucher Type > Sales.
2. Set Method of voucher numbering to Manual and save with Ctrl+A.
3. If multiple numbering series are enabled, review the applicable series.
4. Reopen Import to Tally in BillSync and select that company.

The app does not change company numbering configuration automatically. Existing
vouchers are not renumbered. Correct any already imported voucher separately in
Tally after checking it; reimporting is not a numbering repair. Exact invoice
numbers, GUIDs, financial entries, units, master assignments and XML files are
unchanged. After the check, the existing Units → Masters → Sales sequence,
single-attempt behavior and unknown-result stop still apply.

Official references:

- https://help.tallysolutions.com/import-data-faq/ — “How are Voucher Numbers imported?”
- https://help.tallysolutions.com/use-voucher-numbering-methods/ — Manual numbering.

Offline tests exercise Manual, Automatic, None, missing/ambiguous definitions,
XML errors and network errors with mock Tally replies. They verify no writes on
failure and exact voucher XML preservation on success. No live TallyPrime 6.2
instance was available; live acceptance must still be checked in the user's
company. No AI calls or live Tally writes were made during development.

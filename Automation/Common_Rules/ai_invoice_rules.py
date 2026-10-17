"""Shared party/quantity instructions required for all invoice AI providers."""
RULES=(
    'Identify buyer from Bill To, Buyer, Customer or Sold To, and seller from Supplier, Seller, From or the invoice masthead. '
    'Do not substitute a Ship To recipient, transporter, bank, salesperson or signatory for buyer or seller. '
    'Keep each name, address and GSTIN in its own party role; if ambiguous return null, never copy the seller into buyer. '
    'Printed selling units and explicit quantity suffixes outrank assumptions. If missing, use product/packaging reasoning for PCS, Units, BOX, LTR, KG or other appropriate units. '
    'Return unit_basis printed/inferred and unit_reason. Qty is a heading, not a selling unit. '
    'Never scale numeric quantity, rate or value, or mistake medicine strength for sold weight/volume. '
    'Identify the currency of returned accounting amounts from printed codes, names or symbols. '
    'Return an ISO code only when unambiguous; $ alone is ambiguous, retain it for review. '
    'For foreign-only amounts return the printed monetary values unchanged in their source currency; Python converts to INR. '
    'Read exchange_rate only if printed: exchange_rate_basis is INR_per_foreign for INR per one foreign unit, '
    'or foreign_per_INR for foreign units per INR. exchange_rate_units is the printed denominator unit count '
    '(normally 1; for INR 55 per 100 JPY return rate 55, units 100, basis INR_per_foreign). '
    'Never invent a missing exchange rate or use a current market rate; set exchange_rate_basis to unknown if direction is unclear. '
    'When INR accounting totals and item prices are printed, currency is INR; keep those INR values '
    'and report foreign_currency and exchange_rate separately. Never mix foreign item amounts with INR totals. '
)

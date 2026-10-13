"""Shared party/quantity instructions required for all invoice AI providers."""
RULES=(
    'Identify buyer from Bill To, Buyer, Customer or Sold To, and seller from Supplier, Seller, From or the invoice masthead. '
    'Do not substitute a Ship To recipient, transporter, bank, salesperson or signatory for buyer or seller. '
    'Keep each name, address and GSTIN in its own party role; if ambiguous return null, never copy the seller into buyer. '
    'Printed selling units and explicit quantity suffixes outrank assumptions. If missing, use product/packaging reasoning for PCS, Units, BOX, LTR, KG or other appropriate units. '
    'Return unit_basis printed/inferred and unit_reason. Qty is a heading, not a selling unit. '
    'Never scale numeric quantity, rate or value, or mistake medicine strength for sold weight/volume. '
)

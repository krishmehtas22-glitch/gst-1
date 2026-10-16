"""Correct unit provenance only for a complete, matching production goods table."""
from decimal import Decimal, InvalidOperation


def same_number(a, b):
    try:
        return Decimal(str(a).replace(',', '')) == Decimal(str(b).replace(',', ''))
    except (ValueError, InvalidOperation):
        return False


def same_text(a, b):
    return bool(a and b) and ' '.join(str(a).casefold().split()) == ' '.join(str(b).casefold().split())


def verify_printed_units(record, local_invoice):
    if record.get('reviewed') or local_invoice.get('source_layout') != 'goods_uom_v1':
        return
    if any('Goods table' in str(w) for w in local_invoice.get('extraction_warnings', [])):
        return
    items = record['invoice'].get('items', [])
    printed = local_invoice.get('items', [])
    if not items or len(items) != len(printed):
        return
    if not all(all(same_text(a.get(f), b.get(f)) for f in ('name', 'hsn', 'unit')) and
               all(same_number(a.get(f), b.get(f)) for f in ('quantity', 'rate', 'value'))
               for a, b in zip(items, printed)):
        return
    for item in items:
        if item.get('unit_origin') == 'manual' or item.get('unit_correction_reviewed'):
            continue
        item.update(unit_origin='printed', unit_basis='printed', unit_auto=False,
                    unit_reason='Verified printed UOM in the matching source table row',
                    unit_evidence='Printed UOM '+str(item['unit'])+'; source row matched')
        item.pop('unit_confidence', None)

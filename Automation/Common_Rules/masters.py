"""Plan master dependencies without overwriting existing company records."""
from decimal import Decimal
from .accounting import STATES, TAXES, EXPORT_MODES, money, sales_ledger


def required_masters(inv, config):
    is_export = inv['classification'] in EXPORT_MODES
    accounting_only=is_export or inv.get('tax_accounting_basis')=='invoice_summary'
    masters = [
        {'kind':'ledger','name':inv['buyer_name'],'group':'Sundry Debtors','gstin':inv['buyer_gstin'], 'registration':inv['buyer_registration'], 'state':'Not Applicable' if is_export else STATES[inv['buyer_state']], 'country':inv['buyer_country'] if is_export else 'India'},
        {'kind':'ledger','name':sales_ledger(inv, config),'group':'Sales Accounts','classification':'taxable' if config.get('unified_sales_ledger') else inv['classification']},
    ]
    for tax in TAXES:
        if money(inv[tax]):
            masters.append({'kind':'ledger','name':config['ledgers'][tax],'group':'Duties & Taxes','tax_type':'GST','duty_head':tax.upper()})
    if money(inv['round_off']):
        masters.append({'kind':'ledger','name':config['ledgers']['round_off'],'group':'Indirect Expenses'})
    for item in inv['items']:
        if accounting_only:
            continue  # Accounting export vouchers do not create stock masters.
        unit = config.get('units', {}).get(item['unit'])
        if not unit or not all(unit.get(k) is not None for k in ('formal_name','uqc','decimal_places')):
            raise ValueError(f"Unit {item['unit']!r} needs formal_name, UQC and decimal_places in client.json")
        if not isinstance(unit['decimal_places'], int) or not 0 <= unit['decimal_places'] <= 6:
            raise ValueError(f"Invalid decimal places for unit {item['unit']}")
        if money(item['quantity']).quantize(Decimal(10) ** -unit['decimal_places']) != money(item['quantity']):
            raise ValueError(f"Quantity precision conflicts with unit {item['unit']}")
        masters.append({'kind':'unit','name':item['unit'], **unit})
        # Primary is built in. A custom stock group is a dependency, not an invented existing master.
        group = config.get('stock_group', 'Primary')
        if group != 'Primary':
            masters.append({'kind':'stock_group','name':group,'parent':'Primary'})
        # A stock GST master describes the full GST rate, not only whichever
        # components applied to this invoice's place of supply.
        total_gst = sum(money(item[f'{t}_rate']) for t in TAXES)
        rates = {'cgst_rate':format((total_gst / 2).normalize(),'f'),
                 'sgst_rate':format((total_gst / 2).normalize(),'f'),
                 'igst_rate':format(total_gst.normalize(),'f')}
        masters.append({'kind':'stock_item','name':item['name'],'unit':item['unit'],'group':group,'hsn':item['hsn'], 'classification':inv['classification'], **rates})
    return masters


def identity(master):
    return (master['kind'], master['name'].strip().casefold())


def plan_masters(invoices, config, existing):
    known = {}
    for master in existing:
        key = identity(master)
        if key in known and known[key] != master:
            raise ValueError(f'Conflicting masters in Tally snapshot: {key}')
        known[key] = master
    needed = {}
    errors = {}
    usage = {}
    conflicts = {}
    for key, inv in invoices.items():
        try:
            masters = required_masters(inv, config)
        except ValueError as exc:
            errors.setdefault(key, []).append(str(exc))
            continue
        for master in masters:
            ident = identity(master)
            usage.setdefault(ident, set()).add(key)
            previous = known.get(ident) or needed.get(ident)
            if previous:
                mismatch = [field for field, value in master.items() if field not in ('name', 'kind') and previous.get(field) != value]
                if mismatch:
                    conflicts[ident] = f'Master conflict: {master["kind"]} {master["name"]}: {", ".join(mismatch)}'
                continue
            needed[ident] = master
    for ident, message in conflicts.items():
        for affected in usage[ident]:
            errors.setdefault(affected, []).append(message)
    safe = set(invoices) - set(errors)
    result = [m for ident, m in needed.items() if usage[ident] & safe]
    # If a shared master conflicts, every dependent invoice is blocked.
    priority = {'unit':0,'stock_group':1,'ledger':2,'stock_item':3}
    return sorted(result, key=lambda m:(priority[m['kind']], m['name'].casefold())), errors

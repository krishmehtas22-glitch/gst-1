"""Decimal accounting, GST validation and per-invoice identities."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re

STATES = dict(zip(
    ['01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','26','27','29','30','31','32','33','34','35','36','37','38'],
    ['Jammu and Kashmir','Himachal Pradesh','Punjab','Chandigarh','Uttarakhand','Haryana','Delhi','Rajasthan','Uttar Pradesh','Bihar','Sikkim','Arunachal Pradesh','Nagaland','Manipur','Mizoram','Tripura','Meghalaya','Assam','West Bengal','Jharkhand','Odisha','Chhattisgarh','Madhya Pradesh','Gujarat','Dadra and Nagar Haveli and Daman and Diu','Maharashtra','Karnataka','Goa','Lakshadweep','Kerala','Tamil Nadu','Puducherry','Andaman and Nicobar Islands','Telangana','Andhra Pradesh','Ladakh']))
TAXES = ('cgst', 'sgst', 'igst')
EXPORT_ACCOUNTING_NOTICE = ('LUT export accounting voucher only: no inventory movement. '
    'Configure/check the export sales ledger GST nature and GSTR-1 treatment in Tally before filing.')
EXPORT_COUNTRIES = {'uae':'United Arab Emirates','united arab emirates':'United Arab Emirates',
    'usa':'United States of America','us':'United States of America',
    'united states':'United States of America','united states of america':'United States of America'}


def money(value):
    value = str(value).replace(',', '').strip()
    value = re.sub(r'^(?:Rs\.?|INR|₹)\s*', '', value, flags=re.I).rstrip('%').strip()
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Non-finite number')
    return result


def cents(value):
    return money(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def state_code(value):
    value = str(value).strip()
    if value.isdigit() and value.zfill(2) in STATES:
        return value.zfill(2)
    for code, name in STATES.items():
        if value.casefold() == name.casefold() or value.casefold() == f'{code} - {name}'.casefold():
            return code
    raise ValueError(f'Unknown Indian state/place of supply: {value}')


def gstin_valid(value):
    if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]', value):
        return False
    if value[:2] not in STATES:
        return False
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for i, char in enumerate(value[:14]):
        product = alphabet.index(char) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return alphabet[(36 - total % 36) % 36] == value[-1]


def invoice_key(inv):
    date = datetime.strptime(inv['date'], '%Y-%m-%d')
    year = date.year if date.month >= 4 else date.year - 1
    return f"{inv['seller_gstin']}|{year}-{year+1}|{inv['number'].strip().casefold()}"


def fingerprint(inv):
    clean = {k: v for k, v in inv.items() if k not in ('source', 'sha256', 'raw_text', 'extraction_warnings')}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate(raw, config):
    """Return normalized invoice and errors. Uncertainty never becomes a voucher."""
    inv = dict(raw)
    inv.pop('accounting_only_export',None)
    inv.pop('export_accounting_notice',None)
    errors = list(inv.pop('extraction_warnings', []))
    if bool(inv.get('demo_only')) != bool(config.get('demo_only')):
        errors.append('Demo invoices require a demo client; real invoices require a separate production client')
    required = ('number','date','seller_name','seller_gstin','buyer_name','buyer_registration','place_of_supply','classification','taxable','total','items')
    for field in required:
        if inv.get(field) is None or inv.get(field) == '' or inv.get(field) == []:
            errors.append(f'Missing {field}')
    if errors:
        return inv, errors
    try:
        inv['number'] = str(inv['number']).strip()
        inv['date'] = datetime.strptime(inv['date'], '%Y-%m-%d').date().isoformat()
        inv['seller_gstin'] = str(inv['seller_gstin']).strip().upper()
        inv['buyer_gstin'] = str(inv.get('buyer_gstin') or '').strip().upper()
        if not gstin_valid(inv['seller_gstin']):
            errors.append('Invalid seller GSTIN (format, state or checksum)')
        if inv['seller_gstin'] != config.get('seller_gstin'):
            errors.append('Seller GSTIN does not match this client company')
        if inv['buyer_registration'] not in ('Regular','Composition','Unregistered','Consumer'):
            errors.append('Uncertain buyer registration type')
        if inv['buyer_registration'] in ('Regular','Composition') and not inv['buyer_gstin']:
            errors.append('Registered buyer requires GSTIN')
        if inv['buyer_gstin'] and not gstin_valid(inv['buyer_gstin']):
            errors.append('Invalid buyer GSTIN (format, state or checksum)')
        if inv['buyer_gstin'] and inv['buyer_registration'] in ('Unregistered','Consumer'):
            errors.append('Buyer GSTIN conflicts with unregistered classification')
        is_export = inv['classification'] == 'export_lut'
        if is_export:
            if inv.get('supply') != 'EXPORT' or inv.get('export_mode') != 'LUT_without_payment':
                errors.append('Export accounting requires explicit EXPORT supply and LUT without payment of IGST')
            if str(inv['place_of_supply']).casefold() != 'outside india':
                errors.append('Export place of supply must be Outside India')
            if inv['buyer_gstin'] or inv['buyer_registration'] != 'Unregistered':
                errors.append('LUT export requires an overseas buyer without an Indian GSTIN')
            if str(inv.get('buyer_state','')).casefold() not in ('n/a','outside india',''):
                errors.append('Overseas buyer must not have an Indian buyer state')
            country = str(inv.get('buyer_country','')).strip()
            if not country or country.casefold() in ('india','in','n/a'):
                errors.append('Export requires the foreign buyer country')
            inv['buyer_country'] = EXPORT_COUNTRIES.get(country.casefold(),country)
            inv['buyer_state'] = 'Outside India'
            inv['place_of_supply'] = 'Outside India'
            inv['accounting_only_export'] = True
            inv['export_accounting_notice'] = EXPORT_ACCOUNTING_NOTICE
        else:
            inv['place_of_supply'] = state_code(inv['place_of_supply'])
        if not is_export and inv.get('buyer_state'):
            inv['buyer_state'] = state_code(inv['buyer_state'])
            if inv['buyer_gstin'] and inv['buyer_state'] != inv['buyer_gstin'][:2]:
                errors.append('Buyer GSTIN conflicts with buyer state')
        elif not is_export and inv['buyer_gstin']:
            inv['buyer_state'] = inv['buyer_gstin'][:2]
        elif not is_export:
            errors.append('Buyer state required for master creation')
        if inv['classification'] not in ('taxable','exempt','nil_rated','non_gst','export_lut'):
            errors.append('Uncertain GST classification')
        inv['taxable'] = str(cents(inv['taxable']))
        inv['total'] = str(cents(inv['total']))
        inv['round_off'] = str(cents(inv.get('round_off', '0')))
        if abs(money(inv['round_off'])) > Decimal('1'):
            errors.append('Round off above Rs 1 requires a separately agreed rule')
        for tax in TAXES:
            if tax not in inv:
                errors.append(f'Missing explicit {tax} amount (enter 0 if absent after review)')
            inv[tax] = str(cents(inv.get(tax, 0)))
            if is_export and money(inv[tax]):
                errors.append('LUT without payment export must have zero '+tax.upper())
        normalized = []
        sums = {tax: Decimal('0') for tax in TAXES}
        for index, item in enumerate(inv['items'], 1):
            item = dict(item)
            for field in ('name','hsn','quantity','unit','rate','value'):
                if item.get(field) in (None, ''):
                    errors.append(f'Item {index}: missing {field}')
            if any(item.get(f) in (None, '') for f in ('name','hsn','quantity','unit','rate','value')):
                continue
            item['hsn'] = str(item['hsn'])
            if not re.fullmatch(r'\d{4}|\d{6}|\d{8}', item['hsn']):
                errors.append(f'Item {index}: invalid HSN/SAC')
            for field in ('quantity','rate','value'):
                item[field] = format(money(item[field]).normalize(), 'f')
            if money(item['quantity']) <= 0 or money(item['rate']) < 0 or money(item['value']) < 0:
                errors.append(f'Item {index}: negative amount or nonpositive quantity')
            if abs(cents(money(item['quantity']) * money(item['rate'])) - cents(item['value'])) > Decimal('.01'):
                errors.append(f'Item {index}: quantity × rate does not equal taxable value; discount handling needs review')
            for tax in TAXES:
                rate_field = f'{tax}_rate'
                if item.get(rate_field) in (None, ''):
                    errors.append(f'Item {index}: missing {rate_field}')
                item[rate_field] = format(money(item.get(rate_field) or '0').normalize(), 'f')
                rate = money(item[rate_field])
                if rate < 0 or rate > 100:
                    errors.append(f'Item {index}: invalid {tax} rate')
                sums[tax] += cents(money(item['value']) * rate / 100)
            if money(item['cgst_rate']) != money(item['sgst_rate']):
                errors.append(f'Item {index}: CGST and SGST rates differ')
            intra = inv['seller_gstin'][:2] == inv['place_of_supply']
            if intra and money(item['igst_rate']):
                errors.append(f'Item {index}: intra-state sale has IGST')
            if not intra and (money(item['cgst_rate']) or money(item['sgst_rate'])):
                errors.append(f'Item {index}: inter-state sale has CGST/SGST')
            rate_sum = sum(money(item[f'{t}_rate']) for t in TAXES)
            if inv['classification'] == 'taxable' and rate_sum == 0:
                errors.append(f'Item {index}: taxable classification requires a GST rate')
            if inv['classification'] != 'taxable' and rate_sum:
                errors.append(f'Item {index}: non-taxable classification conflicts with GST')
            normalized.append(item)
        inv['items'] = normalized
        if abs(sum(money(i['value']) for i in normalized) - money(inv['taxable'])) > Decimal('.01'):
            errors.append('Item taxable values do not reconcile to invoice taxable total')
        for tax in TAXES:
            if money(inv[tax]) < 0 or abs(sums[tax] - money(inv[tax])) > Decimal('.01'):
                errors.append(f'{tax.upper()} amount does not reconcile to item rates')
        expected = money(inv['taxable']) + sum(money(inv[t]) for t in TAXES) + money(inv['round_off'])
        if money(inv['taxable']) < 0 or money(inv['total']) <= 0 or cents(expected) != cents(inv['total']):
            errors.append('Invoice total does not balance')
        if inv.get('cess') and money(inv['cess']):
            errors.append('Cess requires a separately agreed ledger and tax rule')
    except (ValueError, InvalidOperation, TypeError, KeyError) as exc:
        errors.append(f'Invalid invoice value: {exc}')
    return inv, errors


def sales_ledger(inv, config):
    if inv['classification'] == 'export_lut':
        name = config['ledgers'].get('export_lut','Export Sales - LUT')
        if not name.strip() or any(name.casefold()==other.casefold() for key,other in config['ledgers'].items() if key != 'export_lut'):
            raise ValueError('Export sales ledger must have a distinct nonempty name')
        return name
    return config['ledgers'][inv['classification']]


def accounting_entries(inv, config):
    rows = [{'ledger': inv['buyer_name'], 'debit': inv['total'], 'credit': '0.00'}]
    rows.append({'ledger': sales_ledger(inv, config), 'debit': '0.00', 'credit': inv['taxable']})
    for tax in TAXES:
        if money(inv[tax]):
            rows.append({'ledger': config['ledgers'][tax], 'debit':'0.00', 'credit': inv[tax]})
    if money(inv['round_off']):
        amount = money(inv['round_off'])
        rows.append({'ledger': config['ledgers']['round_off'], 'debit': str(-amount if amount < 0 else Decimal('0.00')), 'credit': str(amount if amount > 0 else Decimal('0.00'))})
    if sum(money(r['debit']) - money(r['credit']) for r in rows) != 0:
        raise ValueError('Sales entry is not balanced; correct totals or record an explicit round off')
    return rows

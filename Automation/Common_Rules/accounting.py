"""Decimal accounting, GST validation and per-invoice identities."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from .country_catalog import COUNTRY_NAMES

STATES = dict(zip(
    ['01','02','03','04','05','06','07','08','09','10','11','12','13','14','15','16','17','18','19','20','21','22','23','24','26','27','29','30','31','32','33','34','35','36','37','38'],
    ['Jammu and Kashmir','Himachal Pradesh','Punjab','Chandigarh','Uttarakhand','Haryana','Delhi','Rajasthan','Uttar Pradesh','Bihar','Sikkim','Arunachal Pradesh','Nagaland','Manipur','Mizoram','Tripura','Meghalaya','Assam','West Bengal','Jharkhand','Odisha','Chhattisgarh','Madhya Pradesh','Gujarat','Dadra and Nagar Haveli and Daman and Diu','Maharashtra','Karnataka','Goa','Lakshadweep','Kerala','Tamil Nadu','Puducherry','Andaman and Nicobar Islands','Telangana','Andhra Pradesh','Ladakh']))
TAXES = ('cgst', 'sgst', 'igst')
EXPORT_MODES = {'export_lut':'LUT_without_payment','export_igst':'with_payment_of_IGST'}
EXPORT_ACCOUNTING_NOTICE = ('Export accounting voucher only: no inventory movement. '
    'Configure/check the export sales ledger GST nature and GSTR-1 treatment in Tally before filing.')
EXPORT_COUNTRIES = {**COUNTRY_NAMES, 'uk':'United Kingdom','united kingdom':'United Kingdom','uae':'United Arab Emirates','united arab emirates':'United Arab Emirates',
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
    prefixed=re.fullmatch(r'(\d{2})\s*-\s*(.+)',value)
    if prefixed and STATES.get(prefixed[1],'').casefold()==prefixed[2].strip().casefold():
        return prefixed[1]
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


def legacy_fingerprint(inv):
    clean = {k: v for k, v in inv.items() if k not in ('source', 'sha256', 'raw_text', 'extraction_warnings')}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint(inv):
    # Compare validated accounting facts, rather than PDF layout or extraction
    # audit fields. Those facts still undergo full validation before this call.
    fields = ('number','date','seller_name','seller_gstin','seller_state','seller_address',
        'buyer_name','buyer_gstin','buyer_registration','buyer_state','buyer_address','buyer_country',
        'place_of_supply','classification','supply','taxable','total','round_off',
        'cgst','sgst','igst','cess','currency','export_mode','demo_only',
        'foreign_currency','exchange_rate','foreign_invoice_value','tax_accounting_basis')
    item_fields = ('name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate',
                   'list_rate','discount_rate','foreign_rate','foreign_value')
    clean = {key:inv[key] for key in fields if key in inv}
    clean['items'] = [{key:item[key] for key in item_fields if key in item} for item in inv.get('items',[])]
    return hashlib.sha256(json.dumps(clean,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def previous_financial_fingerprint(inv):
    """Verify hashes saved before discount/foreign-price facts were included."""
    previous={key:value for key,value in inv.items() if key not in ('foreign_currency','exchange_rate','foreign_invoice_value')}
    previous['items']=[{key:value for key,value in item.items() if key not in ('list_rate','discount_rate','foreign_rate','foreign_value')} for item in inv.get('items',[])]
    return fingerprint(previous)


def validate(raw, config):
    """Return normalized invoice and errors. Uncertainty never becomes a voucher."""
    inv = dict(raw)
    inv.pop('accounting_only_export',None)
    inv.pop('export_accounting_notice',None)
    for key in ('foreign_currency','exchange_rate','foreign_invoice_value'):
        if inv.get(key) in (None,''):inv.pop(key,None)
    errors = list(inv.pop('extraction_warnings', []))
    if bool(inv.get('demo_only')) != bool(config.get('demo_only')):
        errors.append('Demo invoices require a demo client; real invoices require a separate production client')
    summary=inv.get('tax_accounting_basis')=='invoice_summary'
    if summary and inv.get('items') and all(all(item.get(tax+'_rate') not in (None,'') for tax in TAXES) for item in inv['items']):
        inv.pop('tax_accounting_basis',None);summary=False
    if summary and not config.get('allow_invoice_summary_accounting',False):errors.append('Item GST rates are not printed; inventory requires item-rate review')
    if summary:
        try:
            if any(money(item[tax+'_rate'])!=0 for item in inv.get('items',[]) for tax in TAXES if item.get(tax+'_rate') not in (None,'')):errors.append('Partial item GST rates require full item-rate review before inventory posting')
        except (ValueError,InvalidOperation,TypeError):errors.append('Invalid partial item GST rate')
    required = ('number','date','seller_name','seller_gstin','buyer_name','buyer_registration','place_of_supply','classification','taxable','total','items')
    for field in required:
        if inv.get(field) is None or inv.get(field) == '' or inv.get(field) == []:
            errors.append(f'Missing {field}')
    if errors:
        return inv, errors
    try:
        if inv.get('currency') and str(inv['currency']).strip().upper()!='INR':
            errors.append('Only INR accounting amounts are supported')
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
        is_export = inv['classification'] in EXPORT_MODES
        if is_export:
            if inv.get('supply') != 'EXPORT' or inv.get('export_mode') != EXPORT_MODES[inv['classification']]:
                errors.append('Export accounting requires explicit EXPORT supply and a matching LUT/IGST payment mode')
            if str(inv['place_of_supply']).casefold() != 'outside india':
                errors.append('Export place of supply must be Outside India')
            if inv['buyer_gstin'] or inv['buyer_registration'] != 'Unregistered':
                errors.append('Export requires an overseas buyer without an Indian GSTIN')
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
        if inv['classification'] not in ('taxable','exempt','nil_rated','non_gst',*EXPORT_MODES):
            errors.append('Uncertain GST classification')
        fx=any(key in inv for key in ('foreign_currency','exchange_rate','foreign_invoice_value'))
        if fx:
            if not is_export or inv.get('foreign_currency') not in ('USD','AED') or any(key not in inv for key in ('foreign_currency','exchange_rate','foreign_invoice_value')):
                errors.append('Foreign-price conversion requires an export, USD/AED currency, exchange rate and foreign invoice value')
            inv['exchange_rate']=format(money(inv.get('exchange_rate',0)).normalize(),'f')
            inv['foreign_invoice_value']=str(cents(inv.get('foreign_invoice_value',0)))
            if money(inv['exchange_rate'])<=0 or money(inv['foreign_invoice_value'])<=0:
                errors.append('Export exchange rate and foreign invoice value must be positive')
        inv['taxable'] = str(cents(inv['taxable']))
        inv['total'] = str(cents(inv['total']))
        inv['round_off'] = str(cents(inv.get('round_off', '0')))
        if abs(money(inv['round_off'])) > Decimal('1'):
            errors.append('Round off above Rs 1 requires a separately agreed rule')
        for tax in TAXES:
            if tax not in inv:
                errors.append(f'Missing explicit {tax} amount (enter 0 if absent after review)')
            inv[tax] = str(cents(inv.get(tax, 0)))
            if inv['classification']=='export_lut' and money(inv[tax]):
                errors.append('LUT without payment export must have zero '+tax.upper())
            if inv['classification']=='export_igst' and tax in ('cgst','sgst') and money(inv[tax]):
                errors.append('Export with IGST must not charge '+tax.upper())
        if inv['classification']=='export_igst' and money(inv['igst'])<=0:
            errors.append('Export with payment of IGST requires a positive IGST amount')
        normalized = []
        foreign_sum=Decimal(0)
        sums = {tax: Decimal('0') for tax in TAXES}
        for index, item in enumerate(inv['items'], 1):
            item = dict(item)
            for key in ('list_rate','discount_rate','foreign_rate','foreign_value','printed_cgst','printed_sgst','printed_igst','printed_total'):
                if item.get(key) in (None,''):item.pop(key,None)
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
            if 'list_rate' in item or 'discount_rate' in item:
                if 'list_rate' not in item or 'discount_rate' not in item:
                    errors.append(f'Item {index}: printed list rate and discount percentage are both required')
                else:
                    item['list_rate']=format(money(item['list_rate']).normalize(),'f')
                    item['discount_rate']=format(money(item['discount_rate']).normalize(),'f')
                    discount=money(item['discount_rate'])
                    if money(item['list_rate'])<0 or not 0<discount<=100 or money(item['list_rate'])*(1-discount/100)!=money(item['rate']):
                        errors.append(f'Item {index}: net unit rate does not reconcile to printed list rate and discount')
            if fx:
                if 'foreign_rate' not in item or 'foreign_value' not in item:
                    errors.append(f'Item {index}: foreign unit rate and value are required')
                else:
                    for key in ('foreign_rate','foreign_value'):item[key]=format(money(item[key]).normalize(),'f')
                    foreign_sum+=money(item['foreign_value'])
                    if money(item['foreign_rate'])<0 or money(item['foreign_value'])<0 or cents(money(item['quantity'])*money(item['foreign_rate']))!=cents(item['foreign_value']) or cents(money(item['foreign_value'])*money(inv['exchange_rate']))!=cents(item['value']) or money(item['foreign_rate'])*money(inv['exchange_rate'])!=money(item['rate']):
                        errors.append(f'Item {index}: foreign price/exchange rate does not reconcile to INR accounting values')
            elif 'foreign_rate' in item or 'foreign_value' in item:
                errors.append(f'Item {index}: foreign item prices require export exchange-rate metadata')
            if money(item['quantity']) <= 0 or money(item['rate']) < 0 or money(item['value']) < 0:
                errors.append(f'Item {index}: negative amount or nonpositive quantity')
            if abs(cents(money(item['quantity']) * money(item['rate'])) - cents(item['value'])) > Decimal('.01'):
                errors.append(f'Item {index}: quantity × rate does not equal taxable value; discount handling needs review')
            if summary:
                if any(item.get('printed_'+tax) not in (None,'') for tax in TAXES):errors.append('Item GST amounts require item-level tax validation')
                normalized.append(item);continue
            for tax in TAXES:
                rate_field = f'{tax}_rate'
                if item.get(rate_field) in (None, ''):
                    errors.append(f'Item {index}: missing {rate_field}')
                item[rate_field] = format(money(item.get(rate_field) or '0').normalize(), 'f')
                rate = money(item[rate_field])
                if rate < 0 or rate > 100:
                    errors.append(f'Item {index}: invalid {tax} rate')
                sums[tax] += cents(money(item['value']) * rate / 100)
                if 'printed_'+tax in item and cents(item['printed_'+tax])!=cents(money(item['value'])*rate/100):
                    errors.append(f'Item {index}: printed {tax.upper()} amount does not reconcile')
            if money(item['cgst_rate']) != money(item['sgst_rate']):
                errors.append(f'Item {index}: CGST and SGST rates differ')
            intra = inv['seller_gstin'][:2] == inv['place_of_supply']
            if intra and money(item['igst_rate']):
                errors.append(f'Item {index}: intra-state sale has IGST')
            if not intra and (money(item['cgst_rate']) or money(item['sgst_rate'])):
                errors.append(f'Item {index}: inter-state sale has CGST/SGST')
            rate_sum = sum(money(item[f'{t}_rate']) for t in TAXES)
            if inv['classification'] in ('taxable','export_igst') and rate_sum == 0:
                errors.append(f'Item {index}: taxable classification requires a GST rate')
            if inv['classification'] not in ('taxable','export_igst') and rate_sum:
                errors.append(f'Item {index}: non-taxable classification conflicts with GST')
            if item.get('printed_total') is not None and cents(item['printed_total'])!=cents(money(item['value'])+sum(cents(money(item['value'])*money(item[tax+'_rate'])/100) for tax in TAXES)):
                errors.append(f'Item {index}: printed gross amount does not reconcile')
            normalized.append(item)
        inv['items'] = normalized
        if fx and cents(foreign_sum)!=cents(inv['foreign_invoice_value']):errors.append('Foreign item values do not reconcile to foreign invoice total')
        if abs(sum(money(i['value']) for i in normalized) - money(inv['taxable'])) > Decimal('.01'):
            errors.append('Item taxable values do not reconcile to invoice taxable total')
        if summary:
            if inv['classification']=='taxable':
                intra=inv['seller_gstin'][:2]==inv['place_of_supply']
                if intra and (money(inv['igst']) or money(inv['cgst'])!=money(inv['sgst'])):errors.append('Invoice-summary GST conflicts with intra-state supply')
                if not intra and (money(inv['cgst']) or money(inv['sgst'])):errors.append('Invoice-summary GST conflicts with inter-state supply')
                if sum(money(inv[t]) for t in TAXES)<=0:errors.append('Taxable invoice-summary accounting requires positive GST')
        for tax in TAXES:
            if money(inv[tax]) < 0 or (not summary and abs(sums[tax] - money(inv[tax])) > Decimal('.01')):
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
    if config.get('unified_sales_ledger'):
        return config['ledgers']['taxable']
    if inv['classification'] in EXPORT_MODES:
        kind=inv['classification']
        name = config['ledgers'].get(kind,'Export Sales - LUT' if kind=='export_lut' else 'Export Sales - IGST')
        if not name.strip() or any(name.casefold()==other.casefold() for key,other in config['ledgers'].items() if key != kind):
            raise ValueError('Export sales ledger must have a distinct nonempty name')
        return name
    return config['ledgers'][inv['classification']]


def export_notice(config):
    if config.get('unified_sales_ledger'):
        return ('Export accounting voucher only: no inventory movement. '
                'Check the export GST nature on this voucher and verify GSTR-1 in Tally; '
                'do not change the shared Sales ledger to export-only GST treatment.')
    return EXPORT_ACCOUNTING_NOTICE


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

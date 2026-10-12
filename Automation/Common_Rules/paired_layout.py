"""Explicit adapter for the supplied two-column seller/buyer invoice layout."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from .accounting import cents, EXPORT_COUNTRIES


def parse_paired_layout(text):
    if not re.search(r'SELLER / SUPPLIER\s{2,}BUYER / RECIPIENT', text):
        return None
    warnings = []
    inv = {'source_layout':'paired_columns_v1', 'extraction_warnings':warnings, 'items':[]}
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # These supplied PDFs wrap the last digit of the last table cell.
        # Join only a single digit to an otherwise complete 10-cell row with
        # a monetary cell that has exactly one decimal digit.
        if (lines and re.fullmatch(r'\s+\d',line) and
                len(re.split(r'\s{2,}',lines[-1])) == 10 and
                re.search(r'\d+\.\d$',lines[-1])):
            lines[-1] += line.strip()
        else:
            lines.append(line.strip())
    split = lambda line: re.split(r'\s{2,}', line.strip())
    explicit_lut = bool(re.search(r'Export under LUT without payment of (?:IGST|integrated tax)\b',text,re.I))
    explicit_exempt = bool(re.search(r'(?:Tax treatment:\s*Exempt supply\s*-\s*no GST charged|Exempt supply:\s*no GST charged)',text,re.I))
    currency_ok = False

    def put(key, value):
        if key in inv and inv[key] != value:
            warnings.append('Ambiguous ' + key + ': multiple different values')
        else:
            inv[key] = value

    def amount(value):
        return value.removeprefix('INR ').replace(',', '').strip()

    for index, line in enumerate(lines):
        if re.fullmatch(r'SELLER / SUPPLIER\s{2,}BUYER / RECIPIENT', line):
            if index + 2 < len(lines):
                names, addresses = split(lines[index+1]), split(lines[index+2])
                if len(names) == len(addresses) == 2:
                    for prefix, name, address in zip(('seller','buyer'), names, addresses):
                        put(prefix+'_name', name)
                        put(prefix+'_address', address)
                else:
                    warnings.append('Seller/buyer columns need review')
        row = split(line)
        if len(row) == 2 and all(re.fullmatch(r'GSTIN(?: \(fictional\))?: .*', cell) for cell in row):
            for prefix, cell in zip(('seller','buyer'), row):
                value = cell.split(':',1)[1].strip()
                put(prefix+'_gstin', '' if value.casefold() in ('unregistered','n/a - overseas buyer') else value)
                if value.casefold() == 'unregistered' and prefix == 'buyer':
                    put('buyer_registration', 'Unregistered')
        if len(row) == 2 and re.fullmatch(r'State code: \d{2}',row[0]) and re.fullmatch(r'State code: (?:\d{2}|N/A)',row[1]):
            put('seller_state', row[0].split(':')[1].strip())
            put('buyer_state', row[1].split(':')[1].strip())
        elif len(row) == 2 and re.fullmatch(r'State code: \d{2}',row[0]) and row[1].startswith('Place of supply:'):
            put('seller_state',row[0].split(':')[1].strip())
            put('place_of_supply',row[1].split(':',1)[1].strip())
        if re.match(r'Export under LUT without payment of (?:IGST|integrated tax)\b',line,re.I):
            put('export_mode','LUT_without_payment')
            if 'Country:' in line:
                put('buyer_country',line.split('Country:',1)[1].strip())
        if line.startswith('Shipping bill / port:'):
            put('shipping_bill_port',line.split(':',1)[1].strip())
        match = re.fullmatch(r'Invoice No: (.*?)\s{2,}Date: (\d{2}/\d{2}/\d{4})', line)
        if match:
            put('number',match[1])
            try:
                put('date', datetime.strptime(match[2], '%d/%m/%Y').date().isoformat())
            except ValueError:
                warnings.append('Invalid invoice date')
        match = re.fullmatch(r'Supply: (.*?)\s{2,}Place of supply: (.*)', line)
        if match:
            put('supply', match[1])
            put('place_of_supply', match[2])
            if match[1] in ('INTRA','INTER'):
                put('classification','taxable')
            elif match[1] == 'EXEMPT' and explicit_exempt:
                put('classification','exempt')
            elif match[1] == 'EXPORT':
                put('classification','export_lut' if explicit_lut else 'export')
                if not explicit_lut:
                    warnings.append('Export mode is not explicitly LUT without payment of IGST')
            else:
                warnings.append('Unsupported supply treatment: ' + match[1])
        if line.startswith('Currency:'):
            currency_line = re.sub(r'\s*\|\s*','    ',line)
            currency_ok = bool(re.fullmatch(r'Currency: INR\s{2,}Payment terms: .*?\s{2,}Reverse charge: No', currency_line))
            if not currency_ok:
                warnings.append('Currency/reverse charge treatment needs review')
        match = re.fullmatch(r'(Taxable / exempt value|CGST|SGST|IGST|Invoice Total)(?:\s*:\s*|\s{2,})(INR [\d,.]+)', line)
        if match:
            key = {'Taxable / exempt value':'taxable','Invoice Total':'total'}.get(match[1],match[1].lower())
            put(key,amount(match[2]))

    expected = ['Goods / description','HSN','Qty','UOM','Rate','Taxable','GST %','CGST','SGST','IGST']
    in_table = False
    for line in lines:
        row = split(line)
        if len(row)==10 and row[:6]==expected[:6] and row[6:]==['GST','CGST','SGST','IGST']:
            row[6]='GST %'
        if in_table and row==['%']:
            continue  # Recognized wrapped GST-percent heading, not an item.
        if row == expected:
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith('Taxable / exempt value'):
            in_table = False
            continue
        if len(row) != 10:
            warnings.append('Unrecognized item row needs review')
            continue
        item = dict(zip(('name','hsn','quantity','unit','rate','value','printed_gst_rate',
                         'printed_cgst','printed_sgst','printed_igst'), row))
        for key in ('quantity','rate','value','printed_cgst','printed_sgst','printed_igst'):
            item[key] = amount(item[key])
        try:
            if not re.fullmatch(r'\d+(?:\.\d+)?%',item['printed_gst_rate']):
                raise ValueError('Missing printed item GST percentage')
            gst = Decimal(item['printed_gst_rate'][:-1])
            if inv.get('supply') == 'INTRA':
                rates = (gst/2,gst/2,Decimal(0))
            elif inv.get('supply') == 'INTER':
                rates = (Decimal(0),Decimal(0),gst)
            elif inv.get('classification') == 'exempt' and gst == 0:
                rates = (Decimal(0),Decimal(0),Decimal(0))
            elif inv.get('supply') == 'EXPORT' and gst == 0:
                rates = (Decimal(0),Decimal(0),Decimal(0))
            else:
                raise ValueError('Unsupported supply treatment')
            for tax, rate in zip(('cgst','sgst','igst'),rates):
                item[tax+'_rate'] = str(rate)
                expected_tax = cents(Decimal(item['value'])*rate/100)
                if Decimal(item['printed_'+tax]) != expected_tax:
                    warnings.append('Item '+item['name']+': printed '+tax.upper()+' does not reconcile')
        except (ValueError, InvalidOperation):
            warnings.append('Item tax amounts/rates need review')
        inv['items'].append(item)
    if not inv['items']:
        warnings.append('No recognized item rows')
    if not currency_ok:
        warnings.append('Explicit INR currency and no reverse charge required for this layout')
    if inv.get('supply')=='EXPORT' and not inv.get('buyer_country'):
        country=inv.get('buyer_address','').rsplit(',',1)[-1].strip()
        if country.casefold() in EXPORT_COUNTRIES:
            put('buyer_country',country)  # Country explicitly printed in address.
    compact = re.sub(r'\s+','',text).casefold()
    if all(re.sub(r'\s+','',marker).casefold() in compact for marker in (
        'DEMO DOCUMENT - NOT VALID FOR GST FILING OR COMMERCIAL USE',
        'GSTIN (fictional):',
        'Computer-generated dummy invoice. No actual goods supplied, tax collected or export made.')):
        inv['dummy_document'] = True
    return inv

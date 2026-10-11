"""Conservative text-PDF extraction with digest-bound human review overrides."""
from datetime import datetime
import re
from pypdf import PdfReader

FIELDS = {
    'number': ('invoice no', 'invoice number', 'invoice no.', 'bill no'),
    'date': ('invoice date', 'date'),
    'seller_name': ('seller', 'seller name', 'supplier', 'supplier name'),
    'seller_gstin': ('seller gstin', 'supplier gstin'),
    'buyer_name': ('buyer', 'buyer name', 'customer', 'customer name', 'bill to'),
    'buyer_gstin': ('buyer gstin', 'customer gstin'),
    'buyer_registration': ('buyer registration', 'registration type', 'buyer registration type'),
    'buyer_state': ('buyer state', 'customer state'),
    'place_of_supply': ('place of supply', 'pos'),
    'classification': ('tax treatment', 'gst classification', 'supply type'),
    'taxable': ('taxable value', 'taxable amount', 'taxable total', 'subtotal', 'sub total'),
    'total': ('grand total', 'invoice total', 'total invoice amount', 'total amount'),
    'round_off': ('round off', 'rounding'),
    'cess': ('cess',),
}
HEADERS = {
    'name': ('item', 'item name', 'description', 'product', 'particulars'),
    'hsn': ('hsn', 'hsn/sac', 'sac', 'hsn code'),
    'quantity': ('qty', 'quantity'),
    'unit': ('unit', 'uom', 'units'),
    'rate': ('rate', 'unit rate', 'price'),
    'value': ('value', 'taxable value', 'amount', 'item value'),
    'cgst_rate': ('cgst %', 'cgst rate', 'cgst%'),
    'sgst_rate': ('sgst %', 'sgst rate', 'sgst%'),
    'igst_rate': ('igst %', 'igst rate', 'igst%'),
}


def text_from_pdf(path):
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('Password-protected PDF; provide a readable copy')
    text = '\n'.join(page.extract_text(extraction_mode='layout') or '' for page in reader.pages)
    if len(text.strip()) < 30:
        raise ValueError('No readable text; scanned PDFs require OCR or a reviewed JSON record')
    return text


def unique_field(text, aliases, field, warnings):
    pattern = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    found = re.findall(rf'^\s*(?:{pattern})\s*[:=]\s*(.*?)\s*$', text, re.I | re.M)
    unique = list(dict.fromkeys(s.strip() for s in found if s.strip()))
    if len(unique) > 1:
        warnings.append(f'Ambiguous {field}: multiple different values')
        return None
    return unique[0] if unique else None


def parse_text(text):
    warnings = []
    inv = {key: unique_field(text, aliases, key, warnings) for key, aliases in FIELDS.items()}
    if inv['date']:
        for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %b %Y','%d-%b-%Y'):
            try:
                inv['date'] = datetime.strptime(inv['date'], fmt).date().isoformat()
                break
            except ValueError:
                pass
    # A missing GSTIN is never used to classify the supply or buyer registration.
    if inv['buyer_registration']:
        inv['buyer_registration'] = inv['buyer_registration'].strip().title()
    if inv['classification']:
        normalized = inv['classification'].strip().lower().replace('-', '_').replace(' ', '_')
        inv['classification'] = {'nil':'nil_rated', 'nilrated':'nil_rated', 'exempted':'exempt', 'non_taxable':'non_gst'}.get(normalized, normalized)
    rates = {}
    for tax in ('cgst','sgst','igst'):
        # Examples: CGST: 180, CGST (9%): 180, CGST @ 9%: 180.
        matches = re.findall(rf'^\s*{tax}(?:\s*(?:@\s*|\(\s*)?(\d+(?:\.\d+)?)\s*%\s*\)?)?\s*[:=]\s*([^\n]+)$', text, re.I | re.M)
        amounts = list(dict.fromkeys(a.strip() for _, a in matches))
        if len(amounts) > 1:
            warnings.append(f'Ambiguous {tax.upper()} total')
        if len(amounts) == 1:
            inv[tax] = amounts[0]
        rate_values = list(dict.fromkeys(rate for rate, _ in matches if rate))
        if len(rate_values) == 1:
            rates[tax] = rate_values[0]
        elif len(rate_values) > 1:
            warnings.append(f'Multiple {tax.upper()} rates need item-wise review')
    items = []
    columns = None
    for line in text.splitlines():
        cells = [s.strip() for s in re.split(r'\s*\|\s*|\t+|\s{2,}', line.strip())]
        decoded = []
        for cell in cells:
            decoded.append(next((key for key, aliases in HEADERS.items() if cell.casefold() in aliases), None))
        if all(field in decoded for field in ('name','quantity','rate','value')):
            columns = decoded
            continue
        if columns and len(cells) == len(columns) and len(cells) >= 4:
            item = {key: value for key, value in zip(columns, cells) if key}
            if not re.fullmatch(r'[\d,.]+', item.get('quantity', '')):
                continue
            for tax in ('cgst','sgst','igst'):
                if f'{tax}_rate' not in item:
                    if tax in rates:
                        item[f'{tax}_rate'] = rates[tax]
                    elif inv.get(tax) is not None and re.fullmatch(r'(?:0+(?:\.0+)?)', inv[tax]):
                        item[f'{tax}_rate'] = '0'
            items.append(item)
    inv['items'] = items
    inv['extraction_warnings'] = warnings
    return {k: v for k, v in inv.items() if v is not None}

"""Conservative text-PDF extraction with digest-bound human review overrides."""
from datetime import datetime
import re
from pypdf import PdfReader
from .accounting import money

FIELDS = {
    'number': ('invoice no', 'invoice number', 'invoice no.', 'bill no'),
    'date': ('invoice date', 'date'),
    'seller_name': ('seller', 'seller name', 'supplier', 'supplier name'),
    'seller_gstin': ('seller gstin', 'supplier gstin'),
    'buyer_name': ('buyer', 'buyer name', 'customer', 'customer name', 'bill to'),
    'buyer_gstin': ('buyer gstin', 'customer gstin'),
    'buyer_registration': ('buyer registration', 'registration type', 'buyer registration type'),
    'buyer_state': ('buyer state', 'customer state'),
    'place_of_supply': ('place of supply', 'place of supply (state code)', 'pos'),
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
    delimiter = r'(?:\s*[:=]\s*|\s{2,})' if field in ('taxable','total','round_off','cess') else r'\s*[:=]\s*'
    found = re.findall(rf'^\s*(?:{pattern}){delimiter}(.*?)\s*$', text, re.I | re.M)
    unique = list(dict.fromkeys(s.strip() for s in found if s.strip()))
    if len(unique) > 1:
        warnings.append(f'Ambiguous {field}: multiple different values')
        return None
    return unique[0] if unique else None


def cells(line):
    return [s.strip() for s in re.split(r'\s*\|\s*|\t+|\s{2,}', line.strip())]


def layout_fields(text, warnings):
    """Read the invoice grid, seller banner and standalone BILL TO block.

    Only recognized structural anchors supply roles; source placeholders stay
    unchanged and missing fields remain missing for validation/review.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    found = {}

    def add(key, value):
        if key in found and found[key] != value:
            warnings.append(f'Ambiguous {key}: multiple different values')
            found[key] = None
        elif key not in found:
            found[key] = value

    for index, line in enumerate(lines):
        row = cells(line)
        if [c.casefold() for c in row] == ['invoice no.', 'invoice date', 'type']:
            if index + 1 < len(lines):
                values = cells(lines[index + 1])
                if len(values) == 3:
                    for key, value in zip(('number','date','invoice_type'), values):
                        add(key, value)
                else:
                    warnings.append('Invoice header grid needs review')
        if line.casefold() == 'bill to' and index + 1 < len(lines):
            value = lines[index + 1]
            if ':' not in value and value.casefold() != 'item details':
                add('buyer_name', value)
        metadata = re.fullmatch(r'([^|]+)\|\s*([^|]+)\|\s*GSTIN:\s*(.*?)(?:\s{2,}.*)?', line, re.I)
        if metadata and index > 0:
            banner = cells(lines[index - 1])
            if len(banner) == 2 and banner[1].casefold() == 'tax invoice':
                add('seller_name', banner[0])
                add('seller_state', metadata.group(2).strip())
                add('seller_gstin', metadata.group(3).strip())
    return found


def parse_text(text):
    warnings = []
    inv = {key: unique_field(text, aliases, key, warnings) for key, aliases in FIELDS.items()}
    for key, value in layout_fields(text, warnings).items():
        if inv.get(key) is not None and inv[key] != value:
            warnings.append(f'Ambiguous {key}: label and layout values differ')
            inv[key] = None
        else:
            inv[key] = value
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
    if (inv.get('buyer_gstin') or '').casefold() == 'unregistered':
        inv['buyer_gstin'] = ''
        if inv.get('buyer_registration') not in (None, 'Unregistered', 'Consumer'):
            warnings.append('Buyer registration conflicts with explicit Unregistered label')
        else:
            inv['buyer_registration'] = 'Unregistered'
    if inv['classification']:
        normalized = inv['classification'].strip().lower().replace('-', '_').replace(' ', '_')
        inv['classification'] = {'nil':'nil_rated', 'nilrated':'nil_rated', 'exempted':'exempt', 'non_taxable':'non_gst'}.get(normalized, normalized)
    rates = {}
    for tax in ('cgst','sgst','igst'):
        # Examples: CGST: 180, CGST (9%): 180, CGST @ 9%: 180.
        matches = re.findall(rf'^\s*{tax}(?:\s*(?:@\s*|\(\s*)?(\d+(?:\.\d+)?)\s*%\s*\)?)?(?:\s*[:=]\s*|\s{{2,}})([^\n]+)$', text, re.I | re.M)
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
    # Positive printed GST establishes taxable treatment, never exemption.
    if not inv.get('classification'):
        try:
            if any(money(inv[tax]) > 0 for tax in ('cgst','sgst','igst') if tax in inv):
                inv['classification'] = 'taxable'
        except (ValueError, ArithmeticError):
            pass  # Validation reports malformed printed amounts.
    items = []
    columns = None
    for line in text.splitlines():
        row = cells(line)
        decoded = []
        for cell in row:
            decoded.append(next((key for key, aliases in HEADERS.items() if cell.casefold() in aliases), None))
        if all(field in decoded for field in ('name','quantity','rate','value')):
            columns = decoded
            continue
        if columns and len(row) == len(columns) and len(row) >= 4:
            item = {key: value for key, value in zip(columns, row) if key}
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
    if all(marker.casefold() in text.casefold() for marker in (
            'TEST DOCUMENT - NOT VALID FOR FILING', 'DUMMY / NOT FOR COMMERCIAL USE',
            'All parties, GSTINs, HSN mappings and rates are synthetic examples')):
        inv['dummy_document'] = True
    inv['extraction_warnings'] = warnings
    return {k: v for k, v in inv.items() if v is not None}

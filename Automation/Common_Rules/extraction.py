"""Conservative text-PDF extraction with digest-bound human review overrides."""
from datetime import datetime
import re
from pypdf import PdfReader
from .accounting import money
from .paired_layout import parse_paired_layout
from .section_layout import parse_section_layout
from .ocr import MARKER, read_page

FIELDS = {
    'number': ('invoice no', 'invoice number', 'invoice no.', 'bill no', 'bill number', 'inv no', 'inv no.', 'invoice #', 'tax invoice no'),
    'date': ('invoice date', 'date', 'dated', 'inv date'),
    'seller_name': ('seller', 'seller name', 'supplier', 'supplier name'),
    'seller_gstin': ('seller gstin', 'supplier gstin'),
    'buyer_name': ('buyer', 'buyer name', 'customer', 'customer name', 'bill to', 'billed to', 'recipient', 'recipient name', 'purchaser'),
    'buyer_gstin': ('buyer gstin', 'customer gstin'),
    'buyer_registration': ('buyer registration', 'registration type', 'buyer registration type'),
    'buyer_state': ('buyer state', 'customer state'),
    'place_of_supply': ('place of supply', 'place of supply (state code)', 'pos'),
    'classification': ('tax treatment', 'gst classification', 'supply type'),
    'taxable': ('taxable value', 'taxable amount', 'taxable total', 'subtotal', 'sub total', 'net taxable value'),
    'total': ('grand total', 'invoice total', 'total invoice amount', 'total amount'),
    'round_off': ('round off', 'rounding'),
    'cess': ('cess',),
}
HEADERS = {
    'name': ('item', 'item name', 'description', 'product', 'particulars', 'description of goods', 'goods description', 'product description'),
    'hsn': ('hsn', 'hsn/sac', 'sac', 'hsn code'),
    'quantity': ('qty', 'qty.', 'quantity'),
    'unit': ('unit', 'uom', 'units', 'u/q', 'uqc'),
    'rate': ('rate', 'unit rate', 'price', 'rate (inr)', 'unit price'),
    'value': ('value', 'taxable value', 'taxable amount', 'amount', 'item value', 'net amount', 'taxable (inr)'),
    'cgst_rate': ('cgst %', 'cgst rate', 'cgst%'),
    'sgst_rate': ('sgst %', 'sgst rate', 'sgst%'),
    'igst_rate': ('igst %', 'igst rate', 'igst%'),
    'gst_rate': ('gst %', 'gst%', 'gst rate', 'tax %'),
    'printed_cgst': ('cgst', 'cgst amount', 'cgst amt'),
    'printed_sgst': ('sgst', 'sgst amount', 'sgst amt'),
    'printed_igst': ('igst', 'igst amount', 'igst amt'),
}


def text_from_pdf(path):
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('Password-protected PDF; provide a readable copy')
    pages = []
    used_ocr = False
    for index,page in enumerate(reader.pages):
        text = page.extract_text(extraction_mode='layout') or ''
        if len(text.strip()) < 30:
            text = read_page(path,index)
            used_ocr = True
        pages.append(text)
    text = '\n'.join(pages)
    if len(text.strip()) < 30:
        raise ValueError('No readable text; scanned PDFs require OCR or a reviewed JSON record')
    return (MARKER+'\n'+text) if used_ocr else text


def split_label_lines(text):
    """Separate known key/value pairs that share a row; never split item rows."""
    aliases = sorted({alias for values in FIELDS.values() for alias in values},key=len,reverse=True)
    pattern = '|'.join(re.escape(alias) for alias in aliases)
    lines = []
    original = text.splitlines()
    for index,line in enumerate(original):
        segments = re.split(rf'\s+(?=(?:{pattern})\s*[:=])',line,flags=re.I)
        for segment in segments:
            lines.append(segment)
            if re.fullmatch(rf'\s*(?:{pattern})\s*[:=]?\s*',segment,re.I) and index+1<len(original):
                next_line = original[index+1].strip()
                if next_line and not re.match(rf'(?:{pattern})\s*[:=]',next_line,re.I):
                    lines[-1] = segment.rstrip(' :=')+': '+next_line
    return '\n'.join(lines)


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


def party_blocks(text, warnings):
    """Assign generic GSTIN/state labels only inside an explicit party block."""
    found = {}
    role = None
    expect_name = False
    labels = {'seller':('seller','supplier','from','seller details','supplier details'),
              'buyer':('buyer','recipient','customer','bill to','billed to','buyer details','customer details')}
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        matched_role = next((prefix for prefix,names in labels.items() if line.rstrip(':').casefold() in names),None)
        if matched_role:
            role = matched_role
            expect_name = True
            continue
        inline_role = next((prefix for prefix in ('seller','buyer') if re.match(
            r'^(?:'+ '|'.join(re.escape(alias) for alias in FIELDS[prefix+'_name'])+r')\s*:',line,re.I)),None)
        if inline_role:
            role = inline_role
            expect_name = False
            continue
        if re.match(r'^(?:invoice|inv\b|bill no|date\b|dated\b|item\b|description\b|particulars\b|place of supply\b)',line,re.I):
            role = None
        if not role:
            continue
        if expect_name and ':' not in line:
            found[role+'_name'] = line
            expect_name = False
        match = re.fullmatch(r'(GSTIN|GSTIN/UIN|GST No\.?|State|State code|GST registration|Registration type)\s*:\s*(.*)',line,re.I)
        if match:
            label,value = match[1].casefold(),match[2].strip()
            suffix = 'gstin' if label.startswith('gst') and 'registration' not in label else 'state' if label.startswith('state') else 'registration'
            key = role+'_'+suffix
            if key in found and found[key] != value:
                warnings.append('Ambiguous '+key+' in party block')
                found[key] = None
            elif key not in found:
                found[key] = value
    return found


def normalize_ocr_labels(text):
    # OCR sometimes drops spaces inside known labels. Restore labels only;
    # never invent word boundaries in party names, identifiers or amounts.
    phrases = ['SELLER / SUPPLIER','BUYER / RECIPIENT','GSTIN (fictional)',
               'State code','Invoice No','Place of supply','Payment terms',
               'Reverse charge','Taxable / exempt value','Goods / description',
               'GST %','Invoice Total']
    for phrase in phrases:
        pattern = r'\s*'.join(re.escape(part) for part in phrase.split())
        text = re.sub(pattern,phrase,text,flags=re.I)
    text = re.sub(r':\s*',': ',text)
    for label in ('Date','Place of supply','Payment terms','Reverse charge'):
        text = re.sub(r'\s*'+re.escape(label)+r':', '    '+label+':',text,flags=re.I)
    return text


def parse_text(text):
    if MARKER in text:
        text = normalize_ocr_labels(text)
    paired = parse_section_layout(text, HEADERS)
    if paired is None:
        paired = parse_paired_layout(text)
    if paired is not None:
        if MARKER in text:
            paired['source_ocr'] = True
            paired['extraction_warnings'].append('OCR-derived fields must be checked against the PDF in Review')
        return paired
    warnings = []
    if MARKER in text:
        warnings.append('OCR-derived fields must be checked against the PDF in Review')
    text = split_label_lines(text)
    inv = {key: unique_field(text, aliases, key, warnings) for key, aliases in FIELDS.items()}
    extracted = layout_fields(text, warnings)
    for key,value in party_blocks(text,warnings).items():
        if key in extracted and extracted[key] != value:
            warnings.append('Ambiguous '+key+' in party layout')
            extracted[key] = None
        else:
            extracted[key] = value
    for key, value in extracted.items():
        if inv.get(key) is not None and inv[key] != value:
            warnings.append(f'Ambiguous {key}: label and layout values differ')
            inv[key] = None
        else:
            inv[key] = value
    if inv['date']:
        for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %b %Y','%d-%b-%Y','%d %B %Y'):
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
            if item.get('gst_rate'):
                try:
                    from .accounting import state_code, cents
                    rate = money(item['gst_rate'])
                    intra = state_code(inv['place_of_supply']) == inv['seller_gstin'][:2]
                    derived = {'cgst':rate/2 if intra else 0,'sgst':rate/2 if intra else 0,'igst':0 if intra else rate}
                    for tax,value in derived.items():
                        if item.get(tax+'_rate') is not None and money(item[tax+'_rate']) != value:
                            warnings.append('Item combined GST rate conflicts with component rate')
                        else:
                            item[tax+'_rate'] = str(value)
                        if item.get('printed_'+tax) is not None and cents(money(item['value'])*money(value)/100) != cents(item['printed_'+tax]):
                            warnings.append('Item printed '+tax.upper()+' does not reconcile to its rate')
                except (KeyError,ValueError,ArithmeticError):
                    warnings.append('Item GST split needs seller state and place of supply review')
            items.append(item)
    inv['items'] = items
    if all(marker.casefold() in text.casefold() for marker in (
            'TEST DOCUMENT - NOT VALID FOR FILING', 'DUMMY / NOT FOR COMMERCIAL USE',
            'All parties, GSTINs, HSN mappings and rates are synthetic examples')):
        inv['dummy_document'] = True
    inv['extraction_warnings'] = warnings
    if MARKER in text:
        inv['source_ocr'] = True
    return {k: v for k, v in inv.items() if v is not None}

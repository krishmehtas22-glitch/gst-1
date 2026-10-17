"""Conservative text-PDF extraction with digest-bound human review overrides."""
from datetime import datetime
import re
from pypdf import PdfReader
from .accounting import money
from .paired_layout import parse_paired_layout
from .section_layout import parse_section_layout
from .tabular_layout import parse_role_table, parse_receipt, marked_sample
from .ocr import MARKER, read_page
from .supplier_layouts import layout_text
from .flat_layout import parse_flat_layout, supported_flat
from .goods_layout import parse_goods_layout
from .party_evidence import read_party_roles, role_heading, read_seller_masthead
from .unit_inference import quantity_parts, canonical_unit, default_missing_quantity
from .tax_treatment import apply_printed_treatment
from .document_structure import gst_identifier, header_key, unlabelled_invoice_number, positional_cells

FIELDS = {
    'number': ('invoice no', 'invoice number', 'invoice no.', 'bill no', 'bill number', 'inv no', 'inv no.', 'invoice #', 'tax invoice no', 'invoice reference', 'invoice ref', 'document no', 'document number', 'invoice id', 'document id', 'reference'),
    'date': ('invoice date', 'date', 'dated', 'inv date', 'issued on'),
    'seller_name': ('seller', 'seller name', 'supplier', 'supplier name', 'vendor', 'vendor name', 'exporter', 'issued by', 'sold by', 'bill from', 'seller details', 'supplier details', 'vendor details'),
    'seller_gstin': ('seller gstin', 'supplier gstin', 'vendor gstin', 'seller gst no', 'supplier gst no', 'gstin (supplier)'),
    'buyer_name': ('buyer', 'buyer name', 'customer', 'customer name', 'bill to', 'billed to', 'sold to', 'recipient', 'recipient name', 'purchaser'),
    'buyer_gstin': ('buyer gstin', 'customer gstin', 'recipient gstin', 'gst reg no.'),
    'buyer_registration': ('buyer registration', 'registration type', 'buyer registration type'),
    'buyer_state': ('buyer state', 'customer state'),
    'place_of_supply': ('place of supply', 'place of supply (state code)', 'pos', 'supply state'),
    'classification': ('tax treatment', 'gst classification', 'supply classification', 'supply category', 'transaction', 'type'),
    'taxable': ('taxable value', 'taxable amount', 'taxable total', 'taxable / supply value', 'taxable / exempt value', 'subtotal', 'sub total', 'net taxable value', 'sub-total / supply value', 'amount before tax'),
    'total': ('grand total', 'invoice total', 'total invoice amount', 'total amount', 'total payable', 'amount payable', 'net payable', 'invoice value', 'invoice total (inr)'),
    'round_off': ('round off', 'rounding'),
    'cess': ('cess',),
    'seller_state': ('seller state', 'supplier state'),
    'seller_address': ('seller address', 'supplier address'),
    'buyer_address': ('buyer address', 'customer address', 'address', 'location', 'deliver to'),
    'buyer_country': ('buyer country', 'country of destination', 'destination country', 'destination'),
    'supply': ('supply', 'supply type'),
    'export_mode': ('export mode',),
    'shipping_bill_port': ('shipping bill / port',),
    'currency': ('currency', 'ccy', 'denomination'),
    'reverse_charge': ('reverse charge',),
    'foreign_currency': ('foreign currency',),
    'exchange_rate': ('exchange rate',),
    'foreign_invoice_value': ('foreign invoice value',),
    'cgst': ('cgst', 'central gst (cgst)', 'cgst amount'), 'sgst': ('sgst', 'state gst (sgst)', 'sgst amount'), 'igst': ('igst', 'integrated gst (igst)', 'igst amount'),
}
HEADERS = {
    'name': ('item', 'item name', 'description', 'product', 'particulars', 'description of goods', 'goods description', 'product description', 'item description', 'item / description', 'goods / description', 'description of goods/services', 'product / description', 'item / particulars', 'product / particulars', 'goods / service'),
    'hsn': ('hsn', 'hsn/sac', 'sac', 'hsn code', 'hsn / sac', 'hsn/sac code'),
    'quantity': ('qty', 'qty.', 'quantity'),
    'unit': ('unit', 'uom', 'units', 'u/q', 'uqc', 'unit of measurement'),
    'rate': ('rate', 'unit rate', 'price', 'rate (inr)', 'unit price', 'unit price (inr)', 'price (inr)', 'rate/unit', 'price per unit'),
    'value': ('value', 'taxable value', 'taxable amount', 'amount', 'item value', 'net amount', 'taxable (inr)', 'amount (inr)', 'taxable', 'net value', 'line value'),
    'cgst_rate': ('cgst %', 'cgst rate', 'cgst%'),
    'sgst_rate': ('sgst %', 'sgst rate', 'sgst%'),
    'igst_rate': ('igst %', 'igst rate', 'igst%'),
    'gst_rate': ('gst %', 'gst%', 'gst rate', 'tax %', 'gst (%)', 'tax rate'),
    'printed_cgst': ('cgst', 'cgst amount', 'cgst amt'),
    'printed_sgst': ('sgst', 'sgst amount', 'sgst amt'),
    'printed_igst': ('igst', 'igst amount', 'igst amt'),
    'discount_rate': ('discount %','disc %','discount rate'),
    'foreign_rate': ('rate (usd)','rate (aed)','foreign rate'),
    'foreign_value': ('amount (usd)','amount (aed)','foreign amount'),
}


def text_from_pdf(path):
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('Password-protected PDF; provide a readable copy')
    pages = []
    used_ocr = False
    ocr_evidence=[]
    for index,page in enumerate(reader.pages):
        plain = page.extract_text() or ''
        text = choose_embedded_text(plain,page.extract_text(extraction_mode='layout') or '')
        if len(text.strip()) < 30:
            text = read_page(path,index)
            ocr_evidence.extend(getattr(text,'ocr_evidence',[]))
            used_ocr = True
        pages.append(text)
    text = '\n'.join(pages)
    if len(text.strip()) < 30:
        raise ValueError('No readable text; scanned PDFs require OCR or a reviewed JSON record')
    if used_ocr:
        from .ocr import OCRText
        return OCRText(MARKER+'\n'+text,ocr_evidence)
    return text


def split_label_lines(text, fields=None):
    """Separate known key/value pairs that share a row; never split item rows."""
    aliases = sorted({alias for values in (fields or FIELDS).values() for alias in values},key=len,reverse=True)
    pattern = '|'.join(re.escape(alias) for alias in aliases)
    lines = []
    original = text.splitlines()
    def segments(line):
        # Consume longest labels first: Supply must not split Place of Supply.
        matches=list(re.finditer(rf'(?<!\w)(?:{pattern})\s*[:=]',line,flags=re.I))
        matches=[match for match in matches if not (re.fullmatch(r'supply\s*[:=]',match[0],re.I) and re.search(r'\b(?:local|exempt|taxable|nil-rated|non-gst|(?:intra|inter|outside)[ -]state)\s+$',line[:match.start()],re.I))]
        boundaries=[0]+[match.start() for match in matches if match.start()>0 and line[match.start()-1:match.start()].isspace()]+[len(line)]
        return [line[start:end] for start,end in zip(boundaries,boundaries[1:])]
    for index,line in enumerate(original):
        row=cells(line)
        if len(row)>=4 and len(row)%2==0 and all(re.fullmatch(pattern,row[i],re.I) and not re.fullmatch(pattern,row[i+1],re.I) for i in range(0,len(row),2)):
            lines.extend(row[i]+': '+row[i+1] for i in range(0,len(row),2))
            continue
        # A printed two-column form is also a key/value pair. Only recognize
        # an entire known label, so item descriptions and party names stay intact.
        pair=re.fullmatch(rf'\s*({pattern})\s{{2,}}(\S.*?)\s*',line,re.I)
        if pair and len(cells(line))==2 and not re.match(rf'(?:{pattern})(?=$|\s{{2,}}|:)',pair[2],re.I):
            line=pair[1]+': '+pair[2]
        for segment in segments(line):
            lines.append(segment)
            if re.fullmatch(rf'\s*(?:{pattern})\s*[:=]?\s*',segment,re.I) and index+1<len(original):
                next_line = original[index+1].strip()
                if role_heading(segment.rstrip(' := ').strip()) and ':' in next_line:
                    continue  # A following field label is not the party name.
                if next_line and not re.match(rf'(?:{pattern})\s*[:=]',next_line,re.I):
                    lines[-1] = segment.rstrip(' :=')+': '+next_line
    return '\n'.join(segment for line in lines for segment in segments(line))


def party_value(key,value):
    token=str(value or '').strip()
    if key in ('seller_gstin','buyer_gstin'):
        if key=='buyer_gstin' and (re.fullmatch(r'unregistered(?:\s*(?:/\s*consumer|buyer|[-–]\s*export|\(foreign entity\)))?',token,re.I) or re.fullmatch(r'(?:n/a|na|not applicable)(?:\s*[-–]\s*(?:overseas buyer|export))?',token,re.I)):
            return ''
        return gst_identifier(token).upper()
    return value


def unique_field(text, aliases, field, warnings, mapped=False):
    pattern = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    delimiter = r'(?:\s*[:=]\s*|\s{2,})' if mapped or field in ('taxable','total','round_off','cess') else r'\s*[:=]\s*'
    anchor=r'(?:^\s*|\s{2,})' if mapped else r'^\s*'
    found = re.findall(rf'{anchor}(?:{pattern}){delimiter}(.*?)\s*$', text, re.I | re.M)
    values=[s.strip() for s in found if s.strip()]
    if field in ('seller_gstin','buyer_gstin'):values=[gst_identifier(value) for value in values]
    elif field not in ('seller_name','buyer_name','seller_address','buyer_address'):
        values=[re.split(r'\s*\|\s*(?=[A-Za-z][^|:]{0,40}:)',value)[0].strip() for value in values]
    unique=list(dict.fromkeys(party_value(field,value) for value in values)) if field in ('seller_gstin','buyer_gstin') else list(dict.fromkeys(values))
    if len(unique) > 1:
        warnings.append(f'Ambiguous {field}: multiple different values')
        return None
    if field in ('seller_gstin','buyer_gstin') and unique:
        return next((v for v in values if v.casefold().startswith('unregistered')),values[0])
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
    found,_=read_party_roles(text,warnings)
    return found


def choose_embedded_text(plain,layout):
    """Use ordered text for intact roles when geometric spacing loses fields."""
    if supported_flat(plain):return plain
    if not layout.strip():return plain
    first=parse_text(layout)
    required=('number','date','seller_name','seller_gstin','buyer_name','items')
    if all(first.get(key) for key in required):return layout
    second=parse_text(plain)
    def quality(inv):
        populated=sum(bool(inv.get(key)) for key in required)
        complete_items=sum(all(item.get(key) not in (None,'') for key in ('name','hsn','quantity','unit','rate','value')) for item in inv.get('items',[]))
        return (populated,complete_items,-len(inv.get('extraction_warnings',[])))
    return plain if quality(second)>quality(first) else layout


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


def normalize_basic_fields(inv, warnings):
    from .accounting import state_code
    if inv.get('tax_accounting_basis')=='invoice_summary' and inv.get('items') and all(all(item.get(tax+'_rate') not in (None,'') for tax in ('cgst','sgst','igst')) for item in inv['items']):
        inv.pop('tax_accounting_basis',None);inv.pop('tax_accounting_note',None)
    if inv.get('currency') and re.fullmatch(r'INR(?:\s*(?:\(Indian Rupees\)|[-–]\s*Indian Rupees))?(?:\s+Reverse charge:\s*No)?',inv['currency'],re.I):inv['currency']='INR'
    if inv.get('reverse_charge') and inv['reverse_charge'].strip().casefold() not in ('no','n','false'):
        warnings.append('Reverse-charge invoice requires supported accounting treatment')
    if inv.get('place_of_supply'):
        parts=inv['place_of_supply'].rsplit(',',1)
        if len(parts)==2:
            try:inv['place_of_supply']=state_code(parts[1])
            except ValueError:pass
    if str(inv.get('classification','')).upper() in ('INTRA','INTER'):
        legacy_supply=inv['classification'].upper()
        if inv.get('supply') and str(inv['supply']).upper()!=legacy_supply:warnings.append('Supply type conflicts with the retained classification')
        else:inv['supply']=legacy_supply;inv['classification']='taxable'
    if inv.get('supply'):
        inv['supply']=inv['supply'].strip().upper()
        if inv['supply'] in ('INTRA','INTER') and not inv.get('classification'):inv['classification']='taxable'
    if inv.get('date'):
        inv['date']=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',inv['date'],flags=re.I)
        for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %b %Y','%d-%b-%Y','%d %B %Y'):
            try:
                inv['date'] = datetime.strptime(inv['date'], fmt).date().isoformat()
                break
            except ValueError:
                pass
    if inv.get('buyer_registration'):
        inv['buyer_registration'] = inv['buyer_registration'].strip().title()
    if str(inv.get('buyer_gstin') or '').casefold().startswith('unregistered') and party_value('buyer_gstin',inv.get('buyer_gstin'))=='':
        inv['buyer_gstin'] = ''
        if inv.get('buyer_registration') not in (None, 'Unregistered', 'Consumer'):
            warnings.append('Buyer registration conflicts with explicit Unregistered label')
        else:
            inv['buyer_registration'] = 'Unregistered'
    if inv.get('classification'):
        normalized = inv['classification'].strip().lower().replace('-', '_').replace(' ', '_')
        inv['classification'] = {'nil':'nil_rated', 'nilrated':'nil_rated', 'exempted':'exempt', 'exempt_supply':'exempt', 'nil_rated_supply':'nil_rated', 'taxable_supply':'taxable', 'non_taxable':'non_gst'}.get(normalized, normalized)
    for field in ('seller_gstin','buyer_gstin'):
        if inv.get(field):inv[field]=inv[field].strip().upper()


def mapped_field(text,rule,key,fields,warnings):
    scoped=layout_text(text,rule,warnings)
    if rule.get('position')=='first_line':
        return next((line.strip() for line in scoped.splitlines() if line.strip()),None)
    return unique_field(split_label_lines(scoped,fields),(rule['label'],),key,warnings,mapped=True)


def parse_text(text, field_mappings=None, header_aliases=None):
    field_mappings=field_mappings or {}
    field_aliases=dict(FIELDS)
    field_aliases.update({key:(rule['label'],) for key,rule in field_mappings.items() if rule.get('label')})
    headers={key:tuple(aliases)+tuple(alias.strip().casefold() for alias in (header_aliases or {}).get(key,())) for key,aliases in HEADERS.items()}
    if MARKER in text:
        text = normalize_ocr_labels(text)
    original_text=text
    paired = parse_flat_layout(text)
    if paired is None:
        paired = parse_role_table(text,headers)
    if paired is None:
        paired = parse_receipt(text)
    if paired is None:
        paired = parse_section_layout(text, headers)
    if paired is None:
        paired = parse_paired_layout(text,headers)
    if paired is None:
        paired = parse_goods_layout(text)
    if paired is not None:
        for key,rule in field_mappings.items():
            value=mapped_field(text,rule,key,field_aliases,paired['extraction_warnings'])
            if value is not None:
                paired[key]=value
            else:
                paired.pop(key,None)
                paired['extraction_warnings'].append('Mapped field missing: '+key)
        if marked_sample(original_text):paired['dummy_document']=True
        normalize_basic_fields(paired,paired['extraction_warnings'])
        for item in paired.get('items',[]):default_missing_quantity(item)
        if MARKER in text:
            paired['source_ocr'] = True
            paired['extraction_warnings'].append('OCR-derived fields must be checked against the PDF in Review')
        return paired
    warnings = []
    if MARKER in text:
        warnings.append('OCR-derived fields must be checked against the PDF in Review')
    text = split_label_lines(text,field_aliases)
    inv = {key:(mapped_field(original_text,field_mappings[key],key,field_aliases,warnings)
                if key in field_mappings else unique_field(text,aliases,key,warnings))
           for key,aliases in field_aliases.items()}
    warnings.extend('Mapped field missing: '+key for key in field_mappings if inv.get(key) is None)
    extracted = layout_fields(original_text, warnings)
    for key,value in party_blocks(original_text,warnings).items():
        if key in extracted and extracted[key] != value:
            warnings.append('Ambiguous '+key+' in party layout')
            extracted[key] = None
        else:
            extracted[key] = value
    for key, value in extracted.items():
        if key in field_mappings:
            continue  # Explicit role/section mapping supplies this field.
        if inv.get(key) is not None and party_value(key,inv[key]) != party_value(key,value):
            warnings.append(f'Ambiguous {key}: label and layout values differ')
            inv[key] = None
        else:
            inv[key] = value
    if not inv.get('seller_name') and not any('ambiguous seller' in warning.casefold() for warning in warnings):
        for key,value in read_seller_masthead(original_text,warnings).items():
            if inv.get(key) and inv[key]!=value:
                warnings.append('Seller masthead conflicts with '+key)
            elif key not in field_mappings:
                inv[key]=value
    if not inv.get('number'):inv['number']=unlabelled_invoice_number(original_text,warnings)
    normalize_basic_fields(inv,warnings)
    apply_printed_treatment(inv,original_text,warnings)
    rates = {}
    for tax in ('cgst','sgst','igst'):
        # Examples: CGST: 180, CGST (9%): 180, CGST @ 9%: 180.
        matches = re.findall(rf'^\s*{tax}(?:\s*(?:@\s*|\(\s*)?(\d+(?:\.\d+)?)\s*%\s*\)?)?(?:\s*[:=]\s*|\s{{2,}})([^\n]+)$', text, re.I | re.M)
        amounts = list(dict.fromkeys(a.strip() for _, a in matches))
        if len(amounts) > 1:
            warnings.append(f'Ambiguous {tax.upper()} total')
        if len(amounts) == 1 and tax not in field_mappings:
            inv[tax] = amounts[0]
        rate_values = list(dict.fromkeys(rate for rate, _ in matches if rate))
        if len(rate_values) == 1:
            rates[tax] = rate_values[0]
        elif len(rate_values) > 1:
            warnings.append(f'Multiple {tax.upper()} rates need item-wise review')
    zero_notice=re.search(r'^\s*(?:(?:total\s+)?GST(?:\s+amount)?\s*(?:[:=]|\s{2,})\s*(?:INR\s*)?0+(?:\.0+)?\s*%?|No GST(?:\s+charged)?)\s*[.]?\s*$',original_text,re.I|re.M)
    if zero_notice:
        try:
            if any(inv.get(tax) not in (None,'') and money(inv[tax])!=0 for tax in ('cgst','sgst','igst')):
                warnings.append('Printed no-GST declaration conflicts with component tax amounts')
            else:
                for tax in ('cgst','sgst','igst'):
                    if inv.get(tax) in (None,''):inv[tax]='0'
                inv['zero_gst_evidence']=zero_notice[0].strip()
        except (ValueError,TypeError,ArithmeticError):pass
    # Positive printed GST establishes taxable treatment, never exemption.
    if not inv.get('classification'):
        try:
            if any(money(inv[tax]) > 0 for tax in ('cgst','sgst','igst') if inv.get(tax) is not None):
                inv['classification'] = 'taxable'
        except (ValueError, ArithmeticError):
            pass  # Validation reports malformed printed amounts.
    items = []
    columns = None
    header_line=None
    numeric_units_column=False
    quantity_header_unit=rate_header_unit=None
    for line in original_text.splitlines():
        row = cells(line)
        if columns and any(unique_field(line,FIELDS[key],key,[]) is not None for key in ('taxable','total')):columns=None
        continuation=re.fullmatch(r'\s*GST\s+rate\s*:\s*(\d+(?:\.\d+)?)\s*%\s*',line,re.I)
        if continuation and columns and items:
            if items[-1].get('gst_rate') and money(items[-1]['gst_rate'])!=money(continuation[1]):
                warnings.append('Conflicting GST rate continuation for the preceding item')
            else:items[-1]['gst_rate']=continuation[1];items[-1]['tax_rates_printed']=True
            continue
        decoded = []
        row_quantity_unit=row_rate_unit=None
        for cell in row:
            key=header_key(cell,headers)
            if key is None:
                hint=re.fullmatch(r'(qty\.?|quantity|rate|price|unit rate|unit price)\s*(?:\(\s*(?:per\s+)?([^()]+)\s*\)|(?:per|/)\s+(.+))',cell,re.I)
                if hint and canonical_unit(hint[2] or hint[3]):
                    key='quantity' if hint[1].casefold().startswith(('qty','quantity')) else 'rate'
                    if key=='quantity':row_quantity_unit=hint[2] or hint[3]
                    else:row_rate_unit=hint[2] or hint[3]
            decoded.append(key)
        # Some tables label their numeric quantity column "Units". It is
        # quantity only when the other core columns exist and Qty is absent.
        if all(field in decoded for field in ('name','rate','value')):
            columns = decoded;header_line=line
            numeric_units_column=('quantity' not in decoded and 'unit' in decoded and row[decoded.index('unit')].casefold()=='units')
            quantity_header_unit,rate_header_unit=row_quantity_unit,row_rate_unit
            continue
        if columns and len(row)!=len(columns) and header_line:
            positioned=positional_cells(line,header_line)
            if positioned and len(positioned)==len(columns):
                candidate=dict(zip(columns,positioned))
                try:
                    if quantity_parts(candidate.get('quantity') or '1') and money(candidate.get('rate',''))>=0 and money(candidate.get('value',''))>=0:row=positioned
                except (ValueError,TypeError,ArithmeticError):pass
        if columns and len(row) == len(columns) and len(row) >= 3:
            item = {key: value for key, value in zip(columns, row) if key}
            if numeric_units_column and quantity_parts(item.get('unit','')):
                item['quantity']=item.pop('unit')
            for key in ('gst_rate','cgst_rate','sgst_rate','igst_rate'):
                if item.get(key) and re.fullmatch(r'\d+(?:\.\d+)?\s*%',item[key]):
                    item['printed_'+key]=item[key];item[key]=item[key].rstrip('%').strip()
                if item.get(key) and re.fullmatch(r'\d+(?:\.\d+)?\s*%?\s*[*†‡]+',item[key]):
                    item['printed_'+key]=item[key]
                    item[key]=re.sub(r'\s*%?\s*[*†‡]+$','',item[key])
            item['tax_rates_printed']=any(item.get(key) not in (None,'') for key in ('gst_rate','cgst_rate','sgst_rate','igst_rate'))
            if not item.get('unit') and (quantity_header_unit or rate_header_unit):
                item['unit']=quantity_header_unit or rate_header_unit
                item['unit_evidence']='Printed quantity/rate table header: '+str(item['unit'])
                item['unit_origin']='printed';item['unit_auto']=False
            if quantity_header_unit and rate_header_unit and canonical_unit(quantity_header_unit)!=canonical_unit(rate_header_unit):
                warnings.append('Quantity and price use different units; unit-price conversion needs review')
            default_missing_quantity(item)
            parsed_quantity=quantity_parts(item.get('quantity',''))
            if not parsed_quantity:
                continue
            if parsed_quantity[1]:
                item['printed_quantity']=item['quantity'];item['quantity']=parsed_quantity[0]
                if item.get('unit') and canonical_unit(item['unit'])!=canonical_unit(parsed_quantity[1]):
                    warnings.append('Quantity suffix conflicts with the printed item unit; choose the actual selling unit')
                if not item.get('unit'):item['unit']=parsed_quantity[1]
            items.append(item)
    summary_only=bool(items) and all(not item.get('tax_rates_printed') for item in items) and not rates
    zero_gst=False
    try:zero_gst=all(inv.get(tax) not in (None,'') and money(inv[tax])==0 for tax in ('cgst','sgst','igst'))
    except (ValueError,TypeError,ArithmeticError):pass
    if zero_gst:inv.setdefault('zero_gst_evidence','Printed CGST, SGST and IGST amounts are all zero')
    if summary_only and all(inv.get(tax) is not None for tax in ('cgst','sgst','igst')):
        if zero_gst or inv.get('classification') in ('export_lut','exempt','nil_rated','non_gst'):
            for item in items:
                for tax in ('cgst','sgst','igst'):item[tax+'_rate']='0'
        else:
            inv['tax_accounting_basis']='invoice_summary'
            inv['tax_accounting_note']='Printed invoice GST totals used in accounting view; item GST rates are not printed; no stock movement'
    for item in items:
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
                treatment=inv.get('classification')
                if treatment in ('export_lut','exempt','nil_rated','non_gst'):
                    item.setdefault('printed_gst_rate',item['gst_rate'])
                    derived={'cgst':0,'sgst':0,'igst':0}
                elif treatment=='export_igst':
                    derived={'cgst':0,'sgst':0,'igst':rate}
                elif inv.get('supply')=='EXPORT':
                    raise ValueError('Export payment mode must be read before splitting GST')
                else:
                    intra = state_code(inv['place_of_supply']) == inv['seller_gstin'][:2]
                    derived = {'cgst':rate/2 if intra else 0,'sgst':rate/2 if intra else 0,'igst':0 if intra else rate}
                for tax,value in derived.items():
                    if item.get(tax+'_rate') is not None and money(item[tax+'_rate']) != value:
                        warnings.append('Item combined GST rate conflicts with component rate')
                    else:
                        item[tax+'_rate'] = str(value)
                    if item.get('printed_'+tax) is not None and cents(money(item['value'])*money(value)/100) != cents(item['printed_'+tax]):
                        warnings.append('Item printed '+tax.upper()+' does not reconcile to its rate')
            except (KeyError,ValueError,TypeError,ArithmeticError):
                warnings.append('Export GST payment mode needs review' if inv.get('supply')=='EXPORT' else 'Item GST split needs seller state and place of supply review')
    inv['items'] = items
    if items:
        for tax in ('cgst','sgst','igst'):
            if inv.get(tax) is None and all(item.get(tax+'_rate') is not None and money(item[tax+'_rate'])==0 for item in items):inv[tax]='0'
    if all(marker.casefold() in text.casefold() for marker in (
            'TEST DOCUMENT - NOT VALID FOR FILING', 'DUMMY / NOT FOR COMMERCIAL USE',
            'All parties, GSTINs, HSN mappings and rates are synthetic examples')):
        inv['dummy_document'] = True
    if 'synthetic test document - not for real gst filing or commercial use. gstins and identifiers are fictional.' in ' '.join(original_text.lower().split()):
        inv['dummy_document'] = True
    if marked_sample(original_text):inv['dummy_document']=True
    if 'synthetic test data - not a valid tax document or gst registration' in ' '.join(original_text.casefold().split()):
        inv['dummy_document']=True
    if re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9]',inv.get('seller_gstin') or ''):
        if inv.get('seller_name') and inv.get('buyer_name') and items:
            inv['source_layout']='flexible_roles_v1'
    inv['extraction_warnings'] = warnings
    if MARKER in text:
        inv['source_ocr'] = True
    return {k: v for k, v in inv.items() if v is not None}

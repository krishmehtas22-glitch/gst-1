"""Read the explicit Goods/HSN/Qty/UOM/Rate/Taxable/GST table family.

Support both a column-by-column PDF text stream and positioned text rows.
Fields come from printed labels and corroborated party blocks, never filenames.
"""
import re
from datetime import datetime
from decimal import Decimal,InvalidOperation
from .accounting import state_code
from .party_evidence import read_party_roles,legal_name_key
from .tax_treatment import apply_printed_treatment


HEADER=re.compile(r'\bGoods\s+description\s+HSN\s+Qty\s+UOM\s+Rate\s+Taxable\s+GST\s*%\s+GST\s+amount\b',re.I)
NUMBER=r'[+-]?\d[\d,]*(?:\.\d+)?'


def parse_goods_layout(text):
    table=HEADER.search(text)
    end=re.search(r'^\s*Total value of goods\b',text[table.end():],re.I|re.M) if table else None
    if table is None or end is None:return None
    if not re.search(r'^\s*BUYER(?:\s{2,}SUPPLY DETAILS)?\s*$',text[:table.start()],re.I|re.M):return None
    header=text[:table.start()]
    body=text[table.end():table.end()+end.start()]
    summary=text[table.end()+end.start():]
    warnings=[]
    inv={'source_layout':'goods_uom_v1','items':[],'extraction_warnings':warnings}
    rows=[];pending=[]
    for line in body.splitlines():
        if not line.strip():continue
        cells=[c.strip() for c in re.split(r'\s{2,}|\t+',line.strip())]
        if len(cells)==8 and not pending:rows.append(cells)
        elif len(cells)==1:
            pending.extend(cells)
            if len(pending)==8:rows.append(pending);pending=[]
        else:
            warnings.append('Goods table has an incomplete or ambiguous item row')
    if pending:warnings.append('Goods table has an incomplete item row')
    for row in rows:
        name,hsn,qty,unit,rate,value,gst,amount=row
        if not re.fullmatch(r'\d{4,8}',hsn) or not all(re.fullmatch(NUMBER,v) for v in (qty,rate,value,gst,amount)):
            warnings.append('Goods table item columns need review');continue
        inv['items'].append({'name':name,'hsn':hsn,'quantity':qty,'unit':unit,
            'rate':rate,'value':value,'gst_rate':gst,'printed_gst':amount})
    if not inv['items']:warnings.append('Goods table has no complete item rows')

    def printed(label,source=header):
        matches=re.findall(r'(?:^|(?<=\s))'+label+r'[ \t]*(?::[ \t]*|\r?\n[ \t]*|[ \t]{2,})([^\n]+)',source,re.I|re.M)
        values=list(dict.fromkeys(v.strip() for v in matches
            if v.strip() and len(re.split(r'\s{2,}|\t+',v.strip()))==1))
        if len(values)>1:warnings.append('Ambiguous printed '+label);return None
        return values[0] if values else None

    # Read the explicit invoice identifier from its label/title, not the footer
    # page reference or uploaded filename.
    matches=re.finditer(r'\bInvoice(?: reference| number| no\.?)?[ \t]*(?::[ \t]*|/[ \t]*|\r?\n[ \t]*)([A-Z0-9][A-Z0-9./-]*\d[A-Z0-9./-]*)[ \t]*(?=\r?\n|$)',header,re.I)
    numbers=[]
    for match in matches:
        prefix=header[header.rfind('\n',0,match.start())+1:match.start()].strip().casefold()
        if prefix in {'tax','sales','commercial'}:continue
        numbers.append(match[1])
    numbers=list(dict.fromkeys(numbers))
    if len(numbers)==1:inv['number']=numbers[0]
    else:warnings.append('Printed invoice number missing or ambiguous')
    date=printed(r'(?:Invoice date|Issue date|Dated|Date)')
    if not date:
        dates=re.findall(r'\bTAX INVOICE\s*\|\s*(\d{1,2}/\d{1,2}/\d{4})\b',header,re.I)
        if len(set(dates))==1:date=dates[0]
    try:inv['date']=datetime.strptime(date or '', '%d/%m/%Y').date().isoformat()
    except ValueError:warnings.append('Printed invoice date missing or invalid')

    parties,_=read_party_roles(header,warnings)
    for key,value in parties.items():
        if key.startswith('buyer_'):inv[key]=value
    # Corroborate the seller signature against an exact printed masthead cell.
    signatures=list(dict.fromkeys(re.findall(r'^\s*For\s+(.+?)\s*$',summary,re.I|re.M)))
    boundary=re.search(r'^\s*BUYER\b',header,re.I|re.M)
    masthead=header[:boundary.start()] if boundary else header
    candidates=[]
    if len(signatures)==1:
        signature=legal_name_key(signatures[0])
        for line in masthead.splitlines():
            for cell in re.split(r'\s{2,}|\t+',line.strip()):
                if cell and legal_name_key(cell)==signature:candidates.append(cell)
    candidates=list(dict.fromkeys(candidates))
    if len(candidates)==1:inv['seller_name']=candidates[0]
    else:warnings.append('Printed seller masthead/signature missing or ambiguous')
    ids=list(dict.fromkeys(re.findall(r'\b(?:Seller )?GSTIN\s*:?\s*(\d{2}[A-Z0-9]{13})\b',masthead,re.I)))
    if len(ids)==1:inv['seller_gstin']=ids[0]
    else:warnings.append('Printed seller GSTIN missing or ambiguous')

    seller_state=printed(r'Seller state')
    pos=printed(r'Place of supply')
    if seller_state:
        state=re.fullmatch(r'(.+?)\s*\((\d{2})\)',seller_state)
        try:
            inv['seller_state']=state_code(state[1] if state else seller_state)
            if state and state[2]!=inv['seller_state']:warnings.append('Printed seller state name/code conflict')
        except ValueError:warnings.append('Printed seller state needs review')
    if pos:inv['place_of_supply']=pos
    inv['currency']=printed(r'Currency')

    for label,key in [('Total value of goods','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),(r'TOTAL PAYABLE \(INR\)','total')]:
        value=printed(label,summary)
        if value and re.fullmatch(NUMBER,value):inv[key]=value
        else:warnings.append('Printed '+key+' total missing or ambiguous')
    apply_printed_treatment(inv,text,warnings)
    if inv.get('supply')!='EXPORT' and not inv.get('supply'):
        if re.search(r'\bIntra-state supply\s*-\s*CGST and SGST charged\.',summary,re.I):inv.update(supply='INTRA',classification='taxable')
        elif re.search(r'\bInter-state supply\s*-\s*IGST charged\.',summary,re.I):inv.update(supply='INTER',classification='taxable')
    if re.search(r'\bBill of Supply\s*-\s*exempt goods;\s*no GST charged\.',summary,re.I):inv.update(supply='EXEMPT',classification='exempt')
    if inv.get('supply')=='EXPORT':
        destination=printed(r'Dispatch destination')
        if destination:inv['buyer_country']=destination
        inv['buyer_gstin']='';inv['buyer_registration']='Unregistered'
    elif pos:
        try:inv['place_of_supply']=state_code(pos)
        except ValueError:warnings.append('Printed place of supply needs review')
    for item in inv['items']:
        try:
            rate=Decimal(item['gst_rate'])
            if inv.get('supply')=='INTRA':parts=(rate/2,rate/2,Decimal(0))
            elif inv.get('supply') in ('INTER','EXPORT'):parts=(Decimal(0),Decimal(0),rate)
            elif inv.get('supply')=='EXEMPT' and rate==0:parts=(Decimal(0),Decimal(0),Decimal(0))
            else:warnings.append('Item GST split needs printed supply treatment');continue
            for key,value in zip(('cgst_rate','sgst_rate','igst_rate'),parts):item[key]=str(value)
            item['tax_rates_printed']=True
        except InvalidOperation:warnings.append('Printed item GST rate needs review')
    return inv

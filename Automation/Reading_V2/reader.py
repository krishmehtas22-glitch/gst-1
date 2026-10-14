"""Coordinate-first shadow reader, with explicitly labelled legacy fallback."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,InvalidOperation
import re
from Common_Rules.extraction import FIELDS,HEADERS,parse_text,text_from_pdf
from Common_Rules.accounting import state_code,EXPORT_COUNTRIES
from Common_Rules.party_evidence import BUYER_ROLES,SELLER_ROLES
from .document import read_document,positioned_text,union

VERSION='invoice-reading-v3-evidence-1'
CORE=('number','date','seller_name','buyer_name','taxable','total','cgst','sgst','igst','currency','place_of_supply')
NUMERIC={'taxable','total','cgst','sgst','igst','cess','round_off','quantity','rate','value','gst_rate','printed_gst','gross_value'}
SECTIONS={'supply details','invoice details','invoice information','shipping details','ship to','bank details','payment details'}


def key(value):return ' '.join(re.sub(r'[^\w%]+',' ',str(value or '').casefold()).split())


def decimal(value,locale=None):
    raw=str(value if value is not None else '').strip().replace('\u00a0',' ')
    currency=r'(?:Rs\.?|INR|USD|EUR|GBP|AED|SAR|KWD|BHD|OMR|QAR|JPY|CNY|TWD|HKD|SGD|AUD|CAD|NZD|ZAR|CHF|MYR|[$₹€£])'
    raw=re.sub(r'^'+currency+r'\s*','',raw,flags=re.I)
    raw=re.sub(r'\s*'+currency+r'$','',raw,flags=re.I).strip()
    if locale=='comma':
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:[. ]\d{3})+)(?:,\d+)?',raw):return None
        raw=raw.replace('.','').replace(' ','').replace(',','.')
    elif ',' in raw:
        if ' ' in raw and re.fullmatch(r'[+-]?[\d., ]+',raw):raw=raw.replace(' ','')
        if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?',raw):return None
        raw=raw.replace(',','')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',raw):return None
    try:return Decimal(raw)
    except InvalidOperation:return None


MONTHS={
    'januar':'January','janvier':'January','januari':'January',
    'februar':'February','février':'February','februari':'February',
    'märz':'March','mars':'March','maart':'March','avril':'April',
    'mai':'May','mei':'May','juin':'June','juni':'June',
    'juillet':'July','juli':'July','août':'August','augustus':'August',
    'septembre':'September','oktober':'October','octobre':'October',
    'novembre':'November','dezember':'December','décembre':'December'}


def date_value(text):
    text=re.sub(r'\s+,',',',text.strip())
    text=re.sub(r'(?<=\d)(?:st|nd|rd|th)\b','',text,flags=re.I)
    for name,english in MONTHS.items():text=re.sub(r'\b'+name+r'\b',english,text,flags=re.I)
    text=re.sub(r'(?<=\d)\.\s+(?=[A-Za-z])',' ',text)
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %b %Y','%d-%b-%Y','%d %B %Y','%B %d, %Y','%b %d, %Y','%d.%m.%y','%d/%m/%y','%d-%b-%y','%b %d %Y','%B %d %Y','%Y%m%d'):
        try:return datetime.strptime(text,fmt).date().isoformat()
        except ValueError:pass
    # Month-first numeric dates are accepted only when the second number > 12.
    match=re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})',text)
    if match and int(match[2])>12:
        try:return datetime(int(match[3]),int(match[1]),int(match[2])).date().isoformat()
        except ValueError:pass
    return None


def regional_numbers(document):
    text=' '.join(l['text'] for p in document['pages'] for l in p['lines'])
    return 'comma' if re.search(r'\b(?:factuur|facture|rechnungsdatum|rechnungsnr)\b',text,re.I) and re.search(r'\d,\d{2}\b',text) else None


def equal(a,b,field):
    if field in NUMERIC:
        x,y=decimal(a),decimal(b)
        return x is not None and y is not None and x==y
    if field in {'seller_state','buyer_state','place_of_supply'}:
        x,y=valid_field(field,str(a or '')),valid_field(field,str(b or ''))
        return x is not None and y is not None and x==y
    return key(a)==key(b)


def trace(tokens,page,origin):
    return {'page':page,'token_ids':[t['id'] for t in tokens],
            'box':union([t['box'] for t in tokens]),'raw_text':' '.join(t['text'] for t in tokens),
            'origin':origin,'ocr_confidences':[t['ocr_confidence'] for t in tokens if t['ocr_confidence'] is not None]}


def labels(line,aliases):
    tokens=line['tokens'];found=[];i=0
    while i<len(tokens):
        best=None
        for end in range(min(i+7,len(tokens)),i,-1):
            if any(b['box'][0]-a['box'][2]>.04 for a,b in zip(tokens[i:end],tokens[i+1:end])):continue
            phrase=key(' '.join(t['text'] for t in tokens[i:end]))
            field=aliases.get(phrase)
            if field:
                best=(end,field,union([t['box'] for t in tokens[i:end]]));break
        if best:
            end,field,box=best
            raw=' '.join(t['text'] for t in tokens[i:end])
            if i and end-i==1 and field not in {'name','hsn','quantity','unit','rate','value','gst_rate','printed_gst'} and ':' not in raw and '=' not in raw and tokens[i]['box'][0]-tokens[i-1]['box'][2]<.04:
                i=end;continue
            if field=='number' and i and key(tokens[i-1]['text']) in {'tax','sales','commercial','export'}:
                i=end;continue
            found.append({'start':i,'end':end,'field':field,'box':box});i=end
        else:i+=1
    return found


def valid_field(field,text,locale=None):
    text=text.strip(' :=|')
    if not text:return None
    if field in NUMERIC:
        value=decimal(text,locale)
        return str(value) if value is not None else None
    if field=='number':
        return text.lstrip('# ').strip() if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./_-]*',text.lstrip('# ').strip()) and any(c.isdigit() for c in text) else None
    if field=='date':return date_value(text)
    if field in {'seller_state','buyer_state','place_of_supply'}:
        state=re.sub(r'\s*\(\d{2}\)\s*$','',text)
        if field=='place_of_supply' and key(state) in {'outside india','96 other countries','other countries'}:return 'Outside India'
        try:
            code=state_code(state)
            printed=re.search(r'\((\d{2})\)\s*$',text)
            return code if printed is None or printed[1]==code else None
        except ValueError:
            if field=='place_of_supply' and EXPORT_COUNTRIES.get(text.casefold()) not in (None,'India'):return 'Outside India'
            return None
    if field=='currency':return text.upper() if re.fullmatch(r'[A-Za-z]{3}',text) else None
    if field=='supply':return text.upper() if text.upper() in {'INTRA','INTER','EXEMPT','EXPORT'} else None
    if field=='classification':
        value=key(text).replace(' ','_')
        return value if value in {'taxable','exempt','nil_rated','non_gst','export_lut','export_igst'} else None
    if field=='reverse_charge':return text.title() if text.casefold() in {'yes','no'} else None
    if field in {'seller_gstin','buyer_gstin'}:
        if re.fullmatch(r'\d{2}[A-Z0-9]{13}',text,re.I):return text.upper()
        if re.search(r'foreign buyer|unregistered|not applicable|n/a',text,re.I):return ''
        return None
    if field.endswith('_name'):
        if re.search(r'for software testing|synthetic fixture|not a real (?:supplier )?invoice|fictitious|for demonstration',text,re.I):return None
        if not key(text) or key(text) in SECTIONS|BUYER_ROLES|SELLER_ROLES|{'n a','na','not applicable','unregistered','foreign buyer','unknown','none','null'} or re.match(r'^(?:GSTIN|State|Seller state|Place of supply|Currency|Bank|Tax Invoice|Invoice|\d)\b',text,re.I):return None
        if re.search(r'\bHSN\b.*\b(?:Qty|Quantity|Rate)\b',text,re.I):return None
        try:state_code(text);return None
        except ValueError:pass
        if text.casefold() in EXPORT_COUNTRIES:return None
    return text


def role_boundary(line,mark,marks):
    if mark['field']=='section':return True
    if mark['field'] not in {'buyer_name','seller_name'}:return False
    raw=' '.join(t['text'] for t in line['tokens'][mark['start']:mark['end']])
    if ':' in raw or '=' in raw:return True
    following=next((m['start'] for m in marks if m['start']>=mark['end']),len(line['tokens']))
    return following==mark['end']


def fields_from_document(document):
    aliases={key(a):field for field,values in FIELDS.items() for a in values}
    aliases.update({key(a):'buyer_name' for a in BUYER_ROLES})
    aliases.update({key(a):'seller_name' for a in SELLER_ROLES})
    aliases.update({'invoice':'number','invoice reference':'number','issue date':'date',
        'total payable inr':'total','total value of goods':'taxable','gstin':'gstin',
        'reference':'reference','due date':'due_date','order date':'order_date','date due':'due_date',
        'factuurdatum':'date','factuur datum':'date','rechnungsdatum':'date',
        'factuurnummer':'number','factuur':'number','facture n°':'number','rechnungsnr':'number',
        'kundennr':'reference','vervaldatum':'due_date','klant':'reference','order':'reference',
        'total':'total','totaal':'total','total ttc':'total','total for this invoice':'total',
        'total due':'total','amount due':'total','balance due':'total','invoice subtotal':'taxable',
        'issued':'date','issued date':'date','date issued':'date','tax invoice date':'date',
        'invoice currency':'currency','merchant store currency':'reporting_currency',
        'date de facture':'date','date of issue':'date','billing date':'date',
        'delv date':'delivery_date','delivery date':'delivery_date','date of delivery':'delivery_date',
        'coll date':'collection_date','collection date':'collection_date',
        'invoice total incl tax':'total','total price':'total','bruttosumme':'total',
        'rechnungsbetrag':'total','rechnungssumme brutto inkl ust':'total','brutto':'total',
        'summe inkl ust':'total','due payable':'total','facture':'number','datum':'date',
        'invoice id':'number','rechnung nr':'number','rechnungsnummer':'number',
        'rechnungsbetrag brutto':'total','gesamtbetrag':'total','endbetrag':'total',
        'factuur totaal':'total','somme à payer':'total','total ht':'taxable','total facture':'total',
        'orderdatum':'order_date','date limite de paiement le':'due_date'})
    aliases.update({section:'section' for section in SECTIONS})
    aliases={key(alias):field for alias,field in aliases.items()}
    found={};locale=regional_numbers(document);last_table_columns=None
    for page in document['pages']:
        roles=[];lines=page['lines']
        for index,line in enumerate(lines):
            current_columns=header_columns(line)
            if current_columns:last_table_columns=current_columns
            if re.search(r'synthetic fixture|for software testing|not a real (?:supplier )?invoice',line['text'],re.I):continue
            marks=labels(line,aliases)
            # Attached n° identifiers retain their original source token.
            inline=re.search(r'\bfacture\s+n[°º]\s*(\w+)\s+du\s+(.+?)(?:\s+Détail|$)',line['text'],re.I)
            if inline:
                for field,raw in [('number',inline[1]),('date',inline[2])]:
                    value=valid_field(field,raw,locale)
                    if value is not None and not any(equal(v['value'],value,field) for v in found.get(field,[])):
                        found.setdefault(field,[]).append({'value':value,'evidence':trace(line['tokens'],page['number'],'positioned_label')})
            # A standalone # identifier under an invoice heading is explicit.
            if re.fullmatch(r'#\s*[\w./-]+',line['text']) and any(re.search(r'\binvoice\b',r['text'],re.I) for r in lines[max(0,index-3):index]):
                value=valid_field('number',line['text'])
                if value and not any(equal(e['value'],value,'number') for e in found.get('number',[])):found.setdefault('number',[]).append({'value':value,'evidence':trace(line['tokens'],page['number'],'positioned_label')})
            marks=[m for m in marks if not(m['field'] in {'buyer_name','seller_name'}
                and not role_boundary(line,m,marks) and any(r['field']==m['field']
                    and abs(r['box'][0]-m['box'][0])<.12 and 0<m['box'][1]-r['box'][3]<.06 for r in roles))]
            if not marks:continue
            for mark in marks:
                if mark['field'] in {'buyer_name','seller_name'}:roles.append(mark)
            for position,mark in enumerate(marks):
                field=mark['field']
                if field in {'section','reference','reporting_currency'}:continue
                other_date=field in {'due_date','order_date','delivery_date','collection_date'}
                if other_date:field='date'
                if field=='total':
                    header_aliases={key(a):f for f,values in HEADERS.items() for a in values}
                    header_fields={m['field'] for m in labels(line,header_aliases)}
                    if header_columns(line) or {'quantity','rate'} <= header_fields:continue
                if field=='gstin':
                    nearby=[r for r in roles if abs(r['box'][0]-mark['box'][0])<.12]
                    owner=max(nearby,key=lambda r:r['box'][1]) if nearby else None
                    field='buyer_gstin' if owner and owner['field']=='buyer_name' else 'seller_gstin'
                end=marks[position+1]['start'] if position+1<len(marks) else len(line['tokens'])
                candidates=[line['tokens'][mark['end']:end]]
                if field=='total':
                    previous=next((header_columns(r) for r in reversed(lines[:index]) if header_columns(r)),last_table_columns)
                    if previous:
                        money_columns=[(i,m) for i,m in enumerate(previous) if m['field'] in {'value','gross_value'}]
                        if money_columns:
                            col,amount=money_columns[-1]
                            center=(amount['box'][0]+amount['box'][2])/2
                            lower=((previous[col-1]['box'][0]+previous[col-1]['box'][2])/2+center)/2 if col else 0
                            upper=((previous[col+1]['box'][0]+previous[col+1]['box'][2])/2+center)/2 if col+1<len(previous) else 1
                            aligned=[t for t in line['tokens'][mark['end']:end] if lower<=(t['box'][0]+t['box'][2])/2<upper]
                            if aligned:candidates.insert(0,aligned)
                left=(marks[position-1]['box'][0]+mark['box'][0])/2 if position else max(0,mark['box'][0]-.08)
                right=(mark['box'][0]+marks[position+1]['box'][0])/2 if position+1<len(marks) else 1
                for following in lines[index+1:index+3]:
                    if following['box'][1]-line['box'][3]>.08:break
                    next_marks=labels(following,aliases)
                    if header_columns(following):break
                    if any(role_boundary(following,m,next_marks) for m in next_marks):break
                    if any(left<=m['box'][0]<right and (m['field'] not in {'buyer_name','seller_name'} or role_boundary(following,m,next_marks)) for m in next_marks):break
                    candidates.append([t for t in following['tokens'] if left<=(t['box'][0]+t['box'][2])/2<right])
                for tokens in candidates:
                    value=valid_field(field,' '.join(t['text'] for t in tokens),locale)
                    if value is None and field in {'date','number','total'}:
                        # A typed value may precede text belonging to a separate
                        # nearby panel; keep only an unambiguous leading value.
                        for limit in range(min(len(tokens),5),0,-1):
                            raw=' '.join(t['text'] for t in tokens[:limit])
                            value=valid_field(field,raw,locale)
                            if value is not None:
                                if field=='total' and any(re.search(r'\d',t['text']) for t in tokens[limit:]):
                                    value=None;continue
                                tokens=tokens[:limit];break
                    if value is None:continue
                    if field.endswith('_name') and tokens:
                        bottom=max(t['box'][3] for t in tokens)
                        next_row=next((r for r in lines[index+1:index+4] if 0<r['box'][1]-bottom<.04),None)
                        continuation=[t for t in next_row['tokens'] if left<=(t['box'][0]+t['box'][2])/2<right] if next_row else []
                        suffix=' '.join(t['text'] for t in continuation)
                        if re.fullmatch(r'(?:(?:limited|ltd\.?|private|pvt\.?|llp|llc|inc\.?|incorporated|company)\s*)+',suffix,re.I):
                            tokens=tokens+continuation;value+=' '+suffix
                    priority=1
                    label=key(' '.join(t['text'] for t in line['tokens'][mark['start']:mark['end']]))
                    if field=='total':priority=3 if label in {'grand total','invoice total','total invoice amount','total ttc','rechnungsbetrag brutto','gesamtbetrag','endbetrag','total for this invoice'} else (1 if any(word in label for word in ('due','payable','payer')) else 2)
                    entry={'value':value,'priority':2 if field=='date' and key(' '.join(t['text'] for t in line['tokens'][mark['start']:mark['end']])) not in {'date','dated'} else priority,'evidence':trace(tokens,page['number'],'positioned_label')}
                    if other_date:
                        found.setdefault('_other_dates',[]).append(entry);break
                    previous=next((v for v in found.get(field,[]) if equal(v['value'],value,field)),None)
                    if previous is None:found.setdefault(field,[]).append(entry)
                    elif entry['priority']>previous.get('priority',1):
                        found[field].remove(previous);found[field].append(entry)
                    break
    if not found.get('seller_name'):
        for page in document['pages'][:1]:
            for line in page['lines'][:12]:
                raw=line['text']
                if line['box'][1]>.25:break
                if any(m['field'] in {'buyer_name','section'} for m in labels(line,aliases)) or header_columns(line):break
                if re.search(r'software testing|synthetic fixture|demonstration|sample data|fictitious|not a real invoice',raw,re.I):continue
                if re.search(r'\b(?:LLC|WLL|GmbH|Inc\.?|Ltd\.?|Limited|LLP|PLC|SARL|B\.?V\.?|AG)\b',raw,re.I):
                    name=valid_field('seller_name',raw)
                    if name:
                        found['seller_name']=[{'value':name,'priority':1,'evidence':trace(line['tokens'],page['number'],'positioned_masthead')}]
                        break
    for field,entries in list(found.items()):
        unique=[]
        for entry in entries:
            if not any(equal(e['value'],entry['value'],field) for e in unique):unique.append(entry)
        entries=unique
        priority=max(e.get('priority',1) for e in entries)
        found[field]=[e for e in entries if e.get('priority',1)==priority]
    if not found.get('currency'):
        evidence_by_currency={}
        for page in document['pages']:
            for line in page['lines']:
                tokens=line['tokens']
                for i,token in enumerate(tokens):
                    raw=token['text'];codes=[]
                    for sign,code in [('€','EUR'),('£','GBP'),('₹','INR')]:
                        if sign in raw:codes.append(code)
                    code=raw.strip('():,.;').upper()
                    if code in {'INR','USD','EUR','GBP','AED','SAR','KWD','BHD','OMR','QAR','JPY','CNY','TWD','HKD','SGD','AUD','CAD','NZD','ZAR','CHF','MYR'}:codes.append(code)
                    for currency in codes:evidence_by_currency.setdefault(currency,(page['number'],[token]))
                    if key(' '.join(t['text'] for t in tokens[i:i+2]))=='us dollars':
                        evidence_by_currency.setdefault('USD',(page['number'],tokens[i:i+2]))
        if len(evidence_by_currency)==1:
            currency,(page,tokens)=next(iter(evidence_by_currency.items()))
            found['currency']=[{'value':currency,'priority':1,'evidence':trace(tokens,page,'document_currency_evidence')}]
    return found


def header_columns(line):
    aliases={key(a):field for field,values in HEADERS.items() for a in values}
    aliases.update({'gst amount':'printed_gst','gst amt':'printed_gst',
        'title':'name','product id':'name','total price':'value','price ₹':'rate','total ₹':'value','total':'value','tax':'printed_gst',
        'disc %':'discount_rate','taxes':'gst_rate',
        'artikel':'name','omschrijving':'name','aantal':'quantity','hoeveelheid':'quantity',
        'prijs per stuk':'rate','prijs incl btw':'value','prijs':'rate','bedrag':'value','btw':'gst_rate',
        'désignation':'name','nombre':'quantity','p u ht':'rate','montant ht':'value',
        'beschreibung':'name','menge':'quantity','vk preis':'rate','zeilenbetrag':'value','rabatt %':'discount_rate','pos':'position'})
    marks=labels(line,aliases)
    # Product/category and Title can coexist: use the detailed title column.
    names=[m for m in marks if m['field']=='name']
    if len(names)>1:marks=[m for m in marks if m['field']!='name' or m is names[-1]]
    values=[m for m in marks if m['field']=='value']
    if len(values)==2:
        taxable=next((m for m in values if 'taxable' in key(' '.join(t['text'] for t in line['tokens'][m['start']:m['end']]))),None)
        if taxable:
            for m in values:
                if m is not taxable:m['field']='gross_value'
    if len({m['field'] for m in marks})!=len(marks):return None
    required={'name','quantity','rate','value'}
    if not required<={m['field'] for m in marks}:return None
    return marks


def tables_from_document(document):
    tables=[];locale=regional_numbers(document)
    for page in document['pages']:
        lines=page['lines']
        for index,line in enumerate(lines):
            columns=header_columns(line)
            if not columns:continue
            centers=[(m['box'][0]+m['box'][2])/2 for m in columns]
            edges=[0]+[(a+b)/2 for a,b in zip(centers,centers[1:])]+[1]
            rows=[];notes=[]
            for following in lines[index+1:]:
                if header_columns(following):break
                if re.match(r'^(?:subtotal|sub total)\b',following['text'],re.I):continue
                if re.match(r'^(?:total|grand total|net total|tax summary|tax\s+\d+|TVA|totaal|exclusief btw|factuur totaal|taxable value|CGST|SGST|IGST|round off|amount payable)\b',following['text'],re.I):break
                cells={m['field']:[t for t in following['tokens'] if edges[i]<=(t['box'][0]+t['box'][2])/2<edges[i+1]] for i,m in enumerate(columns)}
                values={field:' '.join(t['text'] for t in tokens) for field,tokens in cells.items()}
                # Long item names can extend into the whitespace before Qty.
                # Move text before a trailing quantity back to the name cell;
                # require its geometry to precede the numeric quantity token.
                quantity_tokens=cells.get('quantity',[])
                split=next((i for i,t in enumerate(quantity_tokens) if decimal(t['text'],locale) is not None and all(re.fullmatch(r'[A-Za-z][A-Za-z./]*',v['text']) for v in quantity_tokens[i+1:])),None)
                if split is not None and split>0 and all(decimal(t['text'],locale) is None for t in quantity_tokens[:split]):
                    cells['name']+=quantity_tokens[:split];cells['quantity']=quantity_tokens[split:]
                    values['name']=' '.join(t['text'] for t in cells['name']);values['quantity']=' '.join(t['text'] for t in cells['quantity'])
                # Units printed inside Qty remain separate, without conversion.
                qty=re.fullmatch(r'([+-]?[\d.,]+)\s+([A-Za-z][A-Za-z./]*)',values.get('quantity',''))
                if qty and 'unit' not in values:
                    values['quantity'],values['unit']=qty.groups();cells['unit']=cells['quantity']
                for field in NUMERIC:
                    if field in values:
                        number=decimal(values[field],locale)
                        if number is not None:values[field]=str(number)
                if all(decimal(values.get(field)) is not None for field in ('quantity','rate','value')) and values.get('name'):
                    if 'hsn' in values and not re.fullmatch(r'\d{4,8}',values['hsn']):notes.append('HSN cell needs review.')
                    rows.append({'values':{k:v for k,v in values.items() if v},'evidence':{k:trace(v,page['number'],'positioned_table') for k,v in cells.items() if v}})
                elif rows and values.get('name') and all(not v for k,v in values.items() if k!='name'):
                    rows[-1]['values']['name']+=' '+values['name']
                    evidence=rows[-1]['evidence']['name'];evidence['token_ids'].extend(t['id'] for t in cells['name']);evidence['box']=union([evidence['box'],union([t['box'] for t in cells['name']])])
                elif any(decimal(values.get(field)) is not None for field in ('quantity','rate','value')):
                    notes.append('Incomplete positioned item row; not fabricated.')
            if rows:tables.append({'page':page['number'],'header':trace(line['tokens'],page['number'],'positioned_table_header'),
                                  'columns':[m['field'] for m in columns],'rows':rows,'warnings':notes})
    return tables


def find_value_evidence(document,value,field):
    if value in (None,''):return None
    for page in document['pages']:
        for line in page['lines']:
            tokens=line['tokens']
            for i in range(len(tokens)):
                for end in range(i+1,min(len(tokens)+1,i+10)):
                    raw=' '.join(t['text'] for t in tokens[i:end])
                    candidate=valid_field(field,raw) if field=='date' else raw
                    if candidate is not None and equal(candidate,value,field):return trace(tokens[i:end],page['number'],'legacy_value_match')
    return None


def validate(invoice):
    checks=[]
    for field in ('number','date','seller_name','buyer_name','total'):
        value=invoice.get(field)
        valid=value not in (None,'')
        if field=='date':valid=valid and date_value(str(value)) is not None
        if field=='total':valid=valid and decimal(value) is not None
        checks.append({'check':'required_'+field,'status':'pass' if valid else 'review'})
    for index,item in enumerate(invoice.get('items',[])):
        q,r,v=(decimal(item.get(f)) for f in ('quantity','rate','value'))
        if any(x is None for x in (q,r,v)):status='review'
        elif item.get('discount_rate') not in (None,'') or item.get('discount') not in (None,''):status='review'
        else:status='pass' if abs(q*r-v)<=Decimal('.01') else 'review'
        checks.append({'check':'item_quantity_rate_value','item':index+1,'status':status})
    taxable,total=decimal(invoice.get('taxable')),decimal(invoice.get('total'))
    components=[decimal(invoice.get(f)) for f in ('cgst','sgst','igst','cess','round_off') if invoice.get(f) not in (None,'')]
    if taxable is not None and total is not None:
        status='pass' if all(x is not None for x in components) and abs(taxable+sum(components,Decimal(0))-total)<=Decimal('.01') else 'review'
        checks.append({'check':'printed_invoice_totals','status':status,
            'scope':'Available printed amounts only; missing tax/cess/round-off stay missing.'})
    else:checks.append({'check':'printed_invoice_totals','status':'review'})
    if not invoice.get('items'):checks.append({'check':'item_rows','status':'review'})
    if invoice.get('seller_name') and key(invoice['seller_name'])==key(invoice.get('buyer_name')):
        checks.append({'check':'seller_buyer_identity','status':'review'})
    return checks


def read_invoice(path,baseline=None,correct_local_baseline=False):
    correct_local_baseline=correct_local_baseline or baseline is None
    document=read_document(path)
    baseline=deepcopy(baseline) if baseline is not None else parse_text(text_from_pdf(path))
    candidates=fields_from_document(document);tables=tables_from_document(document)
    other_dates=candidates.pop('_other_dates',[])
    invoice=deepcopy(baseline);evidence={};conflicts=[];fallback=[]
    if correct_local_baseline and not candidates.get('date') and any(date_value(str(invoice.get('date','')))==d['value'] for d in other_dates):
        conflicts.append({'field':'date','legacy_value':invoice.pop('date',None),'resolution':'Only an order/due/delivery/collection date was found; invoice date remains missing.'})
    for field in set(CORE)|set(candidates):
        choices=candidates.get(field,[])
        if len(choices)==1 and (invoice.get(field) in (None,'') or equal(invoice[field],choices[0]['value'],field) or (correct_local_baseline and (field in {'number','date','total'} or (field=='seller_name' and choices[0]['evidence']['origin']=='positioned_masthead')))):
            if invoice.get(field) not in (None,'') and not equal(invoice[field],choices[0]['value'],field):
                conflicts.append({'field':field,'legacy_value':invoice[field],'positioned_values':[choices[0]['value']],'resolution':'Unique printed label used in comparison only.'})
            invoice[field]=choices[0]['value'];evidence[field]=choices[0]['evidence']
        elif choices:
            conflicts.append({'field':field,'legacy_value':invoice.get(field),'positioned_values':[c['value'] for c in choices]})
        if field not in evidence and invoice.get(field) not in (None,''):
            fallback.append(field);evidence[field]=find_value_evidence(document,invoice[field],field)
    spatial_items=[row for table in tables for row in table['rows']]
    multiple_invoices=len(candidates.get('number',[]))>1
    baseline_items=invoice.get('items',[])
    matches=len(spatial_items)==len(baseline_items) and all(
        all(equal(row['values'].get(f),item.get(f),f) for f in ('name','quantity','rate','value'))
        for row,item in zip(spatial_items,baseline_items))
    can_correct_items=correct_local_baseline and len(spatial_items)>=len(baseline_items) and not any(t['warnings'] for t in tables)
    if spatial_items and not multiple_invoices and (not baseline_items or matches or can_correct_items):
        if not baseline_items or (can_correct_items and not matches):
            if baseline_items:conflicts.append({'field':'items','resolution':'Complete positioned rows used in comparison; legacy rows retained in baseline report.'})
            invoice['items']=[deepcopy(row['values']) for row in spatial_items]
        item_evidence=[row['evidence'] for row in spatial_items]
    else:
        item_evidence=[{f:find_value_evidence(document,item.get(f),f) for f in ('name','quantity','unit','rate','value')} for item in baseline_items]
        if spatial_items:conflicts.append({'field':'items','note':'Positioned rows differ from the legacy result; review required.'})
        if baseline_items:fallback.append('items')
    checks=validate(invoice)
    warnings=list(document['warnings'])+baseline.get('extraction_warnings',[])+[w for t in tables for w in t['warnings']]
    first_lines=' '.join(l['text'] for p in document['pages'][:1] for l in p['lines'][:3])
    document_kind='payment_receipt' if re.search(r'\bpayment receipt\b',first_lines,re.I) else 'invoice_candidate'
    if document_kind=='payment_receipt':warnings.append('Payment receipt: do not substitute Booking ID for an invoice number.')
    return {'version':VERSION,'document_kind':document_kind,'mode':'shadow_only','source_sha256':document['source_sha256'],
        'invoice':invoice,'document':document,'field_evidence':evidence,'item_evidence':item_evidence,
        'table_candidates':tables,'legacy_fallback_fields':sorted(set(fallback)),
        'conflicts':conflicts,'checks':checks,'warnings':warnings,
        'invoice_grouping_required':multiple_invoices,'non_invoice_date_values':[d['value'] for d in other_dates],
        'review_required':bool(conflicts or warnings or any(c['status']=='review' for c in checks)),
        'automatic_import_enabled':False}


def ai_input(result,max_characters=24000):
    """Prepare source geometry for later AI integration; make no request."""
    import json
    if result.get('invoice_grouping_required'):raise ValueError('Multiple invoice identifiers detected; separate the invoices before preparing an AI request.')
    source={'document_id':result['source_sha256'],'coordinate_system':'normalized_top_left',
        'pages':[{'page':p['number'],'lines':[{'id':l['id'],'text':l['text'],'box':[round(v,4) for v in l['box']],
            'tokens':[{'id':t['id'],'text':t['text'],'box':[round(v,4) for v in t['box']]} for t in l['tokens']]} for l in p['lines']]} for p in result['document']['pages']]}
    text=json.dumps(source,ensure_ascii=False,separators=(',',':'))
    if len(text)>max_characters:raise ValueError('Positioned document exceeds the AI input budget; split/page routing must be approved before sending. No content was silently truncated.')
    return text

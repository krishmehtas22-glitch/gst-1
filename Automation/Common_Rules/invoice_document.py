"""Versioned invoice domain: source-bound nested facts, evidence and local projections.

Provider JSON is untrusted. Flat dictionaries are compatibility views at existing
accounting/editor boundaries, not the persisted extraction contract for V2 reads.
"""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
import hashlib,json,re
from .invoice_dates import normalize_date

VERSION=2
STRING={'type':['string','null'],'maxLength':12000}
def obj(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
def strings(names):return {name:deepcopy(STRING) for name in names}
def array(items,limit=1000):return {'type':'array','items':items,'maxItems':limit}
PARTY=obj(strings(('name','address','state','gstin','country','registration')))
ITEM=obj(strings(('description','hsn','quantity','unit','unit_basis','unit_reason','rate',
                  'taxable_value','gst_rate','cgst_rate','sgst_rate','igst_rate','cess_rate',
                  'cgst_amount','sgst_amount','igst_amount','cess_amount','discount',
                  'discount_basis','price_basis','line_total','classification','list_rate','discount_rate','foreign_rate','foreign_value','printed_cgst','printed_sgst','printed_igst','printed_total')))
CHARGE=obj(strings(('label','kind','amount','included_in_taxable_total','hsn',
                    'cgst_rate','sgst_rate','igst_rate','cgst_amount','sgst_amount','igst_amount')))
EVIDENCE=obj({**strings(('field','quote')),'page':{'type':['integer','null'],'minimum':1}},('field','quote'))
FLAG=obj(strings(('code','field','reason')),('code','reason'))
INVOICE_SCHEMA=obj({
 **strings(('document_type','invoice_number','invoice_date_raw','invoice_date_iso',
            'invoice_number_evidence','invoice_date_evidence','place_of_supply','supply',
            'classification','reverse_charge','currency','foreign_currency','exchange_rate',
            'exchange_rate_basis','exchange_rate_units','foreign_invoice_value')),
 'seller':PARTY,'buyer':PARTY,'ship_to':PARTY,
 'export':obj(strings(('country','mode','printed_treatment','shipping_bill_port'))),
 'items':array(ITEM),'other_charges':array(CHARGE,100),
 'totals':obj(strings(('taxable_total','cgst_total','sgst_total','igst_total','cess_total',
                      'round_off','grand_total','grand_total_evidence'))),
 'evidence':array(EVIDENCE,500),'flags':array(FLAG,200)},('items',))
MATCH=obj({'id':STRING,'confidence':{'type':'number','minimum':0,'maximum':1},'reason':STRING},('id','confidence','reason'))
MATCHES=obj({'party':{'anyOf':[MATCH,{'type':'null'}]},'items':array(obj({
 'index':{'type':'integer','minimum':0},'stock':{'anyOf':[MATCH,{'type':'null'}]},
 'unit':{'anyOf':[MATCH,{'type':'null'}]}}),1000)})
EXTRACTION_SCHEMA=obj({'schema_version':{'type':'integer','enum':[VERSION]},
 'invoices':{**array(INVOICE_SCHEMA,1),'minItems':1},'_tally_matches':MATCHES},('schema_version','invoices'))


def validate(value,schema,path='$'):
    """Validate the small explicit JSON-schema vocabulary used by our contract."""
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:validate(value,option,path);return
            except ValueError:pass
        raise ValueError('Invalid invoice value at '+path)
    types=schema.get('type');types=types if isinstance(types,list) else [types]
    actual='null' if value is None else 'boolean' if isinstance(value,bool) else 'string' if isinstance(value,str) else 'object' if isinstance(value,dict) else 'array' if isinstance(value,list) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else 'unsupported'
    if actual not in types and not(actual=='integer' and 'number' in types):raise ValueError('Invalid invoice type at '+path+'; expected '+str(types))
    if 'enum' in schema and value not in schema['enum']:raise ValueError('Unsupported invoice version/value at '+path)
    if actual=='object':
        if any(not isinstance(k,str) for k in value):raise ValueError('Invalid invoice keys at '+path)
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(value)-set(props):raise ValueError('Unexpected invoice fields at '+path+': '+', '.join(sorted(set(value)-set(props))))
        if set(schema.get('required',()))-set(value):raise ValueError('Missing invoice structure at '+path)
        for key,item in value.items():
            if key in props:validate(item,props[key],path+'.'+key)
    elif actual=='array':
        if len(value)>schema.get('maxItems',10000) or len(value)<schema.get('minItems',0):raise ValueError('Unsupported invoice count/rows at '+path+'; split/review the source, no invoice was dropped')
        for index,item in enumerate(value):validate(item,schema['items'],path+'['+str(index)+']')
    elif actual=='string' and len(value)>schema.get('maxLength',12000):raise ValueError('Invoice text exceeds field limit at '+path)
    elif actual in ('integer','number'):
        if not Decimal(str(value)).is_finite() or value<schema.get('minimum',float('-inf')) or value>schema.get('maximum',float('inf')):raise ValueError('Invalid invoice number at '+path)


MAP={'number':('invoice_number',),'date':('invoice_date_iso',),
 'seller_name':('seller','name'),'seller_address':('seller','address'),'seller_state':('seller','state'),'seller_gstin':('seller','gstin'),
 'buyer_name':('buyer','name'),'buyer_address':('buyer','address'),'buyer_state':('buyer','state'),'buyer_gstin':('buyer','gstin'),
 'buyer_country':('buyer','country'),'buyer_registration':('buyer','registration'),
 'export_mode':('export','mode'),'shipping_bill_port':('export','shipping_bill_port'),'taxable':('totals','taxable_total'),'total':('totals','grand_total'),
 **{head:('totals',head+'_total') for head in ('cgst','sgst','igst','cess')},'round_off':('totals','round_off'),
 **{key:(key,) for key in ('place_of_supply','classification','supply','currency','foreign_currency','exchange_rate','exchange_rate_basis','exchange_rate_units','foreign_invoice_value')}}
ITEM_MAP={'name':'description','value':'taxable_value',**{key:key for key in ('hsn','quantity','unit','rate','gst_rate','cgst_rate','sgst_rate','igst_rate','unit_basis','unit_reason','classification','list_rate','discount_rate','foreign_rate','foreign_value','printed_cgst','printed_sgst','printed_igst','printed_total')}}


def get(data,path):
    for key in path:
        if not isinstance(data,dict):return None
        data=data.get(key)
    return data


def put(data,path,value):
    for key in path[:-1]:data=data.setdefault(key,{})
    data[path[-1]]=deepcopy(value)


def checksum(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def field_values(value,path=''):
    if isinstance(value,dict):
        for key,item in value.items():
            if key not in ('evidence','flags') and not key.endswith('_evidence'):yield from field_values(item,path+'.'+key if path else key)
    elif isinstance(value,list):
        for index,item in enumerate(value):yield from field_values(item,path+'['+str(index)+']')
    else:yield path,value


def evidence_status(invoice,source_text='',human=False,previous=None):
    previous=previous or {};quotes={}
    for entry in invoice.get('evidence') or []:
        quotes[entry['field']]=entry
    direct={'invoice_number':invoice.get('invoice_number_evidence'),'invoice_date_iso':invoice.get('invoice_date_evidence'),
            'totals.grand_total':get(invoice,('totals','grand_total_evidence'))}
    for field,quote in direct.items():
        if quote:quotes.setdefault(field,{'field':field,'quote':quote,'page':None})
    result={};normalized=' '.join(source_text.split()).casefold()
    for field,value in field_values(invoice):
        quote=quotes.get(field,{});text=quote.get('quote') or ''
        status='missing' if value in (None,'') else 'unverified'
        origin='model'
        if human and value not in (None,''):status='human_reviewed';origin='human'
        elif text and normalized:
            observed=' '.join(text.split()).casefold() in normalized
            quoted=' '.join(text.split()).casefold()
            expected=str(value or '').casefold()
            if field=='invoice_date_iso':
                supported=normalize_date(text)==value or bool(invoice.get('invoice_date_raw') and str(invoice['invoice_date_raw']).casefold() in quoted)
            else:
                # A source quote for some other value is not supporting evidence.
                expected=expected.replace(',','');quoted=quoted.replace(',','')
                supported=bool(expected and re.search(r'(?<![a-z0-9])'+re.escape(expected)+r'(?![a-z0-9])',quoted))
            status='source_observed' if observed and supported else 'uncertain'
        elif field in previous and previous[field].get('value')==value:
            old=previous[field];status=old.get('status',status);origin=old.get('origin',origin)
        result[field]={'value':deepcopy(value),'status':status,'origin':origin,'quote':text or previous.get(field,{}).get('quote',''),'page':quote.get('page')}
    return result


def normalize_numeric_fields(invoice):
    # Do not let a locale-ambiguous comma be silently stripped into another amount.
    numeric=[]
    numeric.extend((invoice.get('totals') or {},k) for k in ('taxable_total','cgst_total','sgst_total','igst_total','cess_total','round_off','grand_total'))
    numeric.extend((invoice,k) for k in ('exchange_rate','exchange_rate_units','foreign_invoice_value'))
    for row in invoice.get('items') or []:
        numeric.extend((row,k) for k in ('quantity','rate','taxable_value','gst_rate','cgst_rate','sgst_rate','igst_rate','cess_rate','cgst_amount','sgst_amount','igst_amount','cess_amount','discount','discount_rate','list_rate','line_total'))
    for row in invoice.get('other_charges') or []:numeric.extend((row,k) for k in ('amount','cgst_rate','sgst_rate','igst_rate','cgst_amount','sgst_amount','igst_amount'))
    currency_codes=set()
    for row,key in numeric:
        value=row.get(key)
        if value in (None,''):continue
        value=value.strip()
        if key not in ('quantity','exchange_rate_units'):
            prefix=re.match(r'(?i)^(INR|USD|EUR|GBP|JPY|AED|CAD|AUD|CHF|CNY|SGD|NZD|HKD|Rs\.?)\s*',value)
            code=None
            if prefix:
                code=prefix[1].upper();value=value[prefix.end():].strip()
                if code.startswith('RS'):code=None
            elif value[:1] in ('₹','$','€','£','¥'):
                symbol=value[0];value=value[1:].strip();code={'₹':'INR','€':'EUR','£':'GBP'}.get(symbol)
                if code is None and not invoice.get('currency'):raise ValueError('Currency symbol is ambiguous; identify the currency before processing.')
            if code and key not in ('exchange_rate','foreign_invoice_value','cgst_rate','sgst_rate','igst_rate','gst_rate','cess_rate','discount_rate'):currency_codes.add(code)
        if (key.endswith('_rate') or key=='discount' and row.get('discount_basis')=='percent') and value.endswith('%'):value=value[:-1].strip()
        if ',' in value:
            grouped=bool(re.fullmatch(r'[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})*,[0-9]{3})(?:\.[0-9]+)?',value))
            if not grouped:raise ValueError('Ambiguous number formatting in '+key+': '+value+'. Review the source; amount was not guessed.')
            value=value.replace(',','')
        if not re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?',value):raise ValueError('Unclear numeric value in '+key+'; review the printed number before processing.')
        row[key]=value
    explicit=str(invoice.get('currency') or '').strip().upper()
    if len(currency_codes)>1 or explicit and len(explicit)==3 and currency_codes and currency_codes!={explicit}:
        raise ValueError('Printed monetary currency conflicts with accounting currency; review source amounts before processing.')
    if not explicit and len(currency_codes)==1:invoice['currency']=next(iter(currency_codes))


def from_model(answer,record,source_text='',provider='AI'):
    validate(answer,EXTRACTION_SCHEMA)
    invoice=deepcopy(answer['invoices'][0])
    normalize_numeric_fields(invoice)
    raw=invoice.get('invoice_date_raw');iso=invoice.get('invoice_date_iso')
    parsed=normalize_date(raw) if raw else None
    flags=invoice.setdefault('flags',[])
    if raw and iso and parsed!=iso:
        flags.append({'code':'date_conflict','field':'invoice_date_iso','reason':'Raw invoice date does not agree with returned ISO date; review both before posting.'})
    if iso and normalize_date(iso)!=iso:
        flags.append({'code':'date_unclear','field':'invoice_date_iso','reason':'Returned date is not an unambiguous ISO calendar date.'})
    document={'schema_version':VERSION,'invoice':invoice,'source':{'read_sha256':record.get('digest',''),
       'source_sha256':record.get('source_sha256',record.get('digest','')),'client':record.get('client',''),
       'source_text_sha256':hashlib.sha256(source_text.encode()).hexdigest() if source_text else ''},
       'provenance':{'provider':provider,'origin':'nested_extraction'},'raw_extraction':deepcopy(answer['invoices'][0]),'field_status':evidence_status(invoice,source_text)}
    return document


def from_legacy(invoice,record=None,previous=None,human=False):
    record=record or {};previous=deepcopy(previous or invoice.get('_document_v2') or {})
    nested=deepcopy(previous.get('invoice') or {'items':[]})
    for key,path in MAP.items():
        if key in invoice:put(nested,path,invoice[key])
    if 'invoice_date_raw' not in nested:nested['invoice_date_raw']=invoice.get('date')
    old=nested.get('items') or [];items=[]
    for index,item in enumerate(invoice.get('items') or []):
        row=deepcopy(old[index]) if index<len(old) else {}
        for key,path in ITEM_MAP.items():
            if key in item:row[path]=deepcopy(item[key])
        items.append(row)
    nested['items']=items
    if '_other_charges' in invoice:nested['other_charges']=deepcopy(invoice['_other_charges'])
    if human:normalize_numeric_fields(nested)
    document=previous or {'schema_version':VERSION,'source':{'read_sha256':record.get('digest',''),
        'source_sha256':record.get('source_sha256',record.get('digest','')),'client':record.get('client','')},
        'provenance':{'origin':'legacy_migration','provider':invoice.get('api_provider','Saved data')}}
    old_values=dict(field_values((record.get('document') if human and record.get('document') else document).get('invoice') or {}))
    document.setdefault('raw_extraction',deepcopy(nested))
    document['invoice']=nested
    statuses=evidence_status(nested,previous=document.get('field_status'))
    for field,row in statuses.items():
        changed=field not in old_values or old_values[field]!=row['value']
        if human and row['value'] not in (None,''):
            if changed:row.update(status='human_corrected',origin='human',previous_value=old_values.get(field),quote='')
            else:row.update(status='human_reviewed',origin='human')
        elif previous and changed and row['value'] not in (None,''):
            row.update(status='derived',origin='python_normalization',previous_value=old_values.get(field))
    document['field_status']=statuses
    if human:
        document['provenance']['human_reviewed']=True
        document['reviewed_facts_sha256']=checksum(nested)
    return document


def to_legacy(document,base=None):
    if document.get('schema_version')!=VERSION or not isinstance(document.get('invoice'),dict):raise ValueError('Unsupported saved invoice document version')
    inv=document['invoice'];out=deepcopy(base or {})
    for key,path in MAP.items():
        value=get(inv,path)
        if value is not None:out[key]=deepcopy(value)
        else:out.pop(key,None)
    old=out.get('items') or [];out['items']=[]
    for index,row in enumerate(inv.get('items') or []):
        item=deepcopy(old[index]) if index<len(old) else {}
        for key,path in ITEM_MAP.items():
            if row.get(path) is not None:item[key]=deepcopy(row[path])
            else:item.pop(key,None)
        if row.get('discount') not in (None,'','0','0.00'):
            basis=row.get('discount_basis')
            if basis=='percent':item['discount_rate']=row['discount']
            elif basis=='amount':
                try:
                    gross=Decimal(str(row.get('quantity')))*Decimal(str(row.get('rate')))
                    if gross:item['discount_rate']=format(Decimal(row['discount'])/gross*100,'f')
                except (InvalidOperation,TypeError,ArithmeticError):pass
        out['items'].append(item)
    country=get(inv,('export','country'))
    if country and not out.get('buyer_country'):out['buyer_country']=country
    out['_other_charges']=deepcopy(inv.get('other_charges') or [])
    out['_document_v2']=deepcopy(document)
    return out


def prepare_model_result(answer,record,provider,source_text=''):
    """A deliberate local migration for old provider fixtures/caches, no AI call."""
    if isinstance(answer,dict) and ('schema_version' in answer or 'invoices' in answer):
        document=from_model(answer,record,source_text,provider)
        return to_legacy(document)
    # Old caches remain usable; the legacy parser still strictly checks its keys.
    return answer


def sync_record(record,human=False):
    invoice=record.get('invoice') or {};document=from_legacy(invoice,record,previous=record.get('document') or invoice.get('_document_v2'),human=human)
    record['document']=document
    if '_document_v2' in invoice:invoice['_document_v2']=deepcopy(document)
    return document


def findings(document):
    """Domain issues are preserved independently from provider confidence."""
    inv=document['invoice'];result=[]
    if document.get('reviewed_facts_sha256')==checksum(inv):return result
    if document.get('provenance',{}).get('origin')=='legacy_model_response':
        result.append({'field':'Extraction format','reason':'The model returned the old field format. It was migrated locally without another request; review source facts because structured evidence was not supplied.','code':'legacy_response_review'})
    for flag in inv.get('flags') or []:
        result.append({'field':flag.get('field') or 'Invoice extraction','reason':flag.get('reason') or flag.get('code') or 'AI uncertainty','code':flag.get('code') or 'uncertain'})
    for field,status in document.get('field_status',{}).items():
        if status.get('status')=='uncertain':result.append({'field':field,'reason':'Quoted evidence was not found in the supplied source text. Compare with the original document.','code':'evidence_unverified'})
    if document.get('provenance',{}).get('origin')=='nested_extraction':
        for field in ('invoice_number','invoice_date_iso','seller.gstin','buyer.gstin','totals.grand_total'):
            review=document.get('field_status',{}).get(field,{})
            if review.get('value') not in (None,'') and review.get('status')=='unverified':
                result.append({'field':field,'reason':'No supporting source quote was retained for this critical field; compare it with the original invoice.','code':'evidence_missing'})
    if inv.get('other_charges'):
        result.append({'field':'Charge GST reporting','reason':'Separate charges are posted to their named ledgers. Review their GST nature and inclusion in invoice totals in the destination company.','code':'charge_reporting_review'})
    country=get(inv,('export','country'));buyer_country=get(inv,('buyer','country'))
    if country and buyer_country and country.casefold()!=buyer_country.casefold():
        result.append({'field':'Export country','reason':'Export destination and buyer country differ. Current XML uses the reviewed buyer country; verify the source and destination treatment.','code':'country_conflict'})
    raw=inv.get('invoice_date_raw');iso=inv.get('invoice_date_iso')
    if raw and iso and normalize_date(raw)!=iso:result.append({'field':'Invoice date','reason':'Printed date and normalized date disagree; no replacement date was invented.','code':'date_conflict'})
    return result


def require_exportable(records):
    """Never drop facts that the established serializer cannot represent safely."""
    for record in records:
        document=sync_record(record)
        if document.get('source',{}).get('read_sha256') and document['source']['read_sha256']!=record.get('digest'):raise ValueError('Nested document source changed; re-process or review the source before XML.')
        inv=document['invoice'];kind=inv.get('document_type')
        if kind not in (None,'','tax_invoice','sales_invoice','bill_of_supply'):
            raise ValueError('Unsupported sales document type '+str(kind)+' in '+str(inv.get('invoice_number') or record.get('path'))+'. Review the source; no current XML was replaced.')
        if inv.get('reverse_charge') not in (None,'','No','no','false','False','0','not_applicable'):
            raise ValueError('Reverse-charge treatment needs explicit accounting review before XML. No unsupported tax treatment was silently posted.')
        for item in inv.get('items') or []:
            if item.get('price_basis') not in (None,'','per_unit','1'):
                raise ValueError('Non-unit price basis requires review before XML; quantities and rates were not silently converted.')
            if item.get('discount') not in (None,'','0','0.00') and item.get('discount_basis') not in ('amount','percent'):
                raise ValueError('Confirm whether the item discount is a percentage or amount before XML.')
        charges=inv.get('other_charges') or []
        for charge in charges:
            try:amount=Decimal(str(charge.get('amount')))
            except InvalidOperation:raise ValueError('Charge amount is missing/invalid; review charges before XML.') from None
            if not amount.is_finite() or abs(amount)>Decimal('1e20'):raise ValueError('Charge amount is invalid; review charges before XML.')
            kind=str(charge.get('kind') or '').strip().casefold()
            label=str(charge.get('label') or '')
            if kind=='tcs' or re.search(r'\btcs\b|tax collected at source',label,re.I):raise ValueError('TCS requires a reviewed tax-ledger allocation; it was not silently exported as ordinary sales.')
            if kind=='discount' and amount>0:raise ValueError('Confirm the signed discount deduction before XML; a positive discount was not added as income.')
            if charge.get('included_in_taxable_total') not in ('yes','no'):raise ValueError('Confirm whether '+str(charge.get('label') or 'charge')+' is included in the taxable total before XML.')
            if not str(charge.get('label') or '').strip():raise ValueError('Charge ledger description is required before XML.')


def normalize_document_result(answer,record,provider,source_text=''):
    from .gemini_reader import normalize_invoice_result,FIELDS,ITEM_FIELDS
    nested=isinstance(answer,dict) and ('schema_version' in answer or 'invoices' in answer)
    if nested:
        document=from_model(answer,record,source_text,provider)
        view=to_legacy(document);view.pop('_document_v2',None);view.pop('_other_charges',None)
        projected={k:v for k,v in view.items() if k in FIELDS or k=='items'}
        projected['items']=[{k:v for k,v in row.items() if k in ITEM_FIELDS} for row in view.get('items',[])]
    else:
        document=None;view=None;projected=deepcopy(answer)
        valid_legacy=(isinstance(answer,dict) and not set(answer)-set(FIELDS)-{'items'} and isinstance(answer.get('items'),list)
            and all(v is None or isinstance(v,str) for k,v in answer.items() if k!='items')
            and all(isinstance(row,dict) and not set(row)-set(ITEM_FIELDS) and all(v is None or isinstance(v,str) for v in row.values()) for row in answer['items']))
        if valid_legacy:
            numeric=from_legacy(answer)['invoice'];normalize_numeric_fields(numeric)
    result=normalize_invoice_result(projected,record,provider)
    if not nested and isinstance(answer,dict):
        for row,original in zip(result['items'],answer.get('items') or []):
            if original.get('quantity') in (None,'') and row.get('quantity_assumed'):row.pop('quantity',None)
    if view is not None:
        result.update({k:v for k,v in view.items() if k not in FIELDS and k!='items'})
        for row,original in zip(result['items'],view['items']):row.update({k:v for k,v in original.items() if k not in ITEM_FIELDS})
        for row,source_item in zip(result['items'],document['invoice'].get('items') or []):
            if source_item.get('quantity') in (None,'') and row.get('quantity_assumed'):row.pop('quantity',None)
    if document is not None:
        for row,source_item in zip(result['items'],document['invoice'].get('items') or []):
            treatment=source_item.get('classification') or document['invoice'].get('classification')
            if treatment in ('exempt','nil_rated','non_gst','export_lut'):
                for head in ('cgst','sgst','igst'):
                    # An explicit non-tax/LUT treatment determines transaction
                    # components, while raw_extraction retains printed absence.
                    if row.get(head+'_rate') in (None,''):row[head+'_rate']='0'
    document=from_legacy(result,record,document)
    if not nested:
        document['provenance'].update(origin='legacy_model_response',provider=provider)
        document['raw_legacy_response']=deepcopy(answer)
        document['raw_extraction']=from_legacy(answer)['invoice']
    result['_document_v2']=document
    result['_other_charges']=deepcopy(document['invoice'].get('other_charges') or [])
    return result


def cache_fields(invoice):
    document=deepcopy(invoice.get('_document_v2'))
    if not document:return {'invoice':deepcopy(invoice)}
    view={k:deepcopy(v) for k,v in invoice.items() if k!='_document_v2'}
    return {'document':document,'document_sha256':checksum(document),'invoice':view,'projection_sha256':checksum(view)}


def cached_invoice(saved,record):
    document=saved.get('document')
    if document is None:
        invoice=deepcopy(saved.get('invoice'))
        if not isinstance(invoice,dict) or not isinstance(invoice.get('items'),list):raise ValueError('Invalid saved extraction')
        invoice['_document_v2']=from_legacy(invoice,record)
        return invoice
    if saved.get('document_sha256')!=checksum(document):raise ValueError('Saved nested invoice document changed; review or re-read the source')
    if saved.get('projection_sha256')!=checksum(saved.get('invoice')):raise ValueError('Saved invoice projection changed; review or re-read the source')
    if document.get('schema_version')!=VERSION or document.get('source',{}).get('read_sha256')!=record.get('digest'):raise ValueError('Saved invoice document does not match the source/version')
    validate(document.get('invoice'),INVOICE_SCHEMA)
    invoice=to_legacy(document,saved.get('invoice'))
    if checksum({k:v for k,v in invoice.items() if k!='_document_v2'})!=saved.get('projection_sha256'):raise ValueError('Saved invoice projection does not agree with nested facts')
    return invoice


def field_label(path):
    names={'invoice_number':'Invoice number','invoice_date_raw':'Printed invoice date','invoice_date_iso':'Invoice date',
           'totals.grand_total':'Grand total','totals.taxable_total':'Taxable total','place_of_supply':'Place of supply'}
    if path in names:return names[path]
    match=re.fullmatch(r'(items|other_charges)\[([0-9]+)\]\.(.+)',str(path))
    if match:return ('Item ' if match[1]=='items' else 'Charge ')+str(int(match[2])+1)+' — '+match[3].replace('_',' ').title()
    return str(path).replace('gstin','GSTIN').replace('_',' ').replace('.',' — ').title().replace('Gstin','GSTIN')

"""Explicit, cached Gemini PDF extraction; never an automatic approval."""
import base64, hashlib, json, os, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote,quote_plus
from .source_documents import verify_source
from .engine import read_json, write_json

REVISION='gemini-pdf-v1'
DEFAULT_MODEL='gemini-2.5-flash'
FIELDS=('number','date','seller_name','seller_gstin','seller_state','seller_address',
        'buyer_name','buyer_gstin','buyer_registration','buyer_state','buyer_address',
        'buyer_country','place_of_supply','classification','supply','export_mode',
        'currency','taxable','cgst','sgst','igst','cess','round_off','total')
ITEM_FIELDS=('name','hsn','quantity','unit','rate','value','gst_rate',
             'cgst_rate','sgst_rate','igst_rate','unit_basis','unit_reason')
WARNING='Gemini extracted fields: compare with the source PDF and approve in Review'


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'gemini_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    data=read_json(path)
    if data.get('source_sha256')!=record['digest'] or data.get('revision')!=REVISION:
        raise ValueError('Gemini cache does not match this PDF or reader revision')
    inv=data.get('invoice')
    if not isinstance(inv,dict) or not isinstance(inv.get('items'),list):
        raise ValueError('Invalid Gemini extraction cache')
    from copy import deepcopy
    inv=deepcopy(inv)
    infer_api_units(inv,record,'Gemini')
    return {**inv,'source_api':True,'api_provider':'Gemini','api_model':data['model'],
            'api_review_mode':data.get('review_mode','desktop'),
            'extraction_warnings':[] if data.get('review_mode')=='tally' else [WARNING]}


def schema():
    def strings(names):
        return {'type':'OBJECT','properties':{name:{'type':'STRING','nullable':True} for name in names},'required':list(names)}
    invoice=strings(FIELDS)
    invoice['properties']['items']={'type':'ARRAY','items':strings(ITEM_FIELDS)}
    invoice['required'].append('items')
    return invoice


def configured_model():
    model=os.environ.get('GEMINI_INVOICE_MODEL',DEFAULT_MODEL).strip().removeprefix('models/')
    if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+',model):
        raise ValueError('GEMINI_INVOICE_MODEL must be a Gemini model ID, for example gemini-2.5-flash')
    return model


def safe_provider_error(error,key):
    """Keep Google's reason, redact credentials, never print HTML error pages."""
    message='';status=''
    try:
        data=json.loads(error.read(16384))
        detail=data.get('error',{})
        if isinstance(detail,dict):
            message=detail.get('message','');status=detail.get('status','')
    except (ValueError,TypeError,OSError):pass
    if not isinstance(message,str):message=''
    if not isinstance(status,str) or not re.fullmatch(r'[A-Z_]+',status):status=''
    if key:
        for token in (key,quote(key,safe=''),quote_plus(key)):
            message=message.replace(token,'[REDACTED]')
    message=re.sub(r'(?i)([?&](?:key|api_key)=)[^\s&"\']+',r'\1[REDACTED]',message)
    message=re.sub(r'AIza[A-Za-z0-9_-]+','[REDACTED]',message)
    message=re.sub(r'\bAQ\.[A-Za-z0-9_-]{12,}','[REDACTED]',message)
    return status,' '.join(message.split())[:900]


def api_json(path,key,payload=None,timeout=35):
    if not re.fullmatch(r'[A-Za-z0-9._-]{10,512}',key):
        raise ValueError('GEMINI_API_KEY must contain only the key copied from AI Studio, without quotes, a URL or line breaks')
    request=Request('https://generativelanguage.googleapis.com/v1beta/'+path,
                    data=None if payload is None else json.dumps(payload).encode(),
                    method='GET' if payload is None else 'POST',
                    headers={'Content-Type':'application/json','x-goog-api-key':key})
    try:
        with urlopen(request,timeout=timeout) as response:
            raw=response.read(2*1024*1024+1)
    except HTTPError as exc:
        status,message=safe_provider_error(exc,key)
        reasons={400:'Request rejected',401:'Authentication rejected',403:'Access denied',404:'Requested API resource was not found',429:'Quota or rate limit reached; no automatic retry'}
        raise ValueError('Gemini HTTP '+str(exc.code)+(f' [{status}]' if status else '')+': '+(message or reasons.get(exc.code,'Provider request failed'))) from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('Gemini connection failed or timed out; local extraction is unchanged') from None
    if len(raw)>2*1024*1024:raise ValueError('Gemini response exceeded the supported size')
    try:return json.loads(raw)
    except (json.JSONDecodeError,TypeError):raise ValueError('Gemini returned an unreadable API response') from None


def request_invoice(payload,key,model):
    try:response=api_json('models/'+model+':generateContent',key,payload,timeout=120)
    except ValueError as exc:raise ValueError('Model '+model+' — '+str(exc)) from None
    try:
        choices=response.get('candidates',[])
        if len(choices)!=1 or choices[0].get('finishReason')!='STOP':
            raise ValueError('Gemini did not return a complete extraction')
        text=''.join(part.get('text','') for part in choices[0]['content']['parts'])
        return json.loads(text)
    except (json.JSONDecodeError,KeyError,TypeError):
        raise ValueError('Gemini returned an unreadable structured extraction') from None


def extract_selected(root,record,transport=None):
    verify_source(root,record)
    model=configured_model()
    old=cache_path(root,record)
    if old.exists():
        saved=read_json(old)
        if saved.get('model')==model and saved.get('revision')==REVISION:
            result=candidate(root,record)
            from .api_selection import activate
            activate(root,record,'Gemini')
            return result  # No second API call or charge.
    key=os.environ.get('GEMINI_API_KEY','').strip()
    if not key:raise ValueError('Set GEMINI_API_KEY in Windows user environment variables, then reopen the BAT. Do not paste the key into chat.')
    data=Path(record['path']).read_bytes()
    if len(data)>8*1024*1024:raise ValueError('Gemini extraction supports PDFs up to 8 MiB')
    from .groq_reader import prepare_invoice_payload
    shared=prepare_invoice_payload(record,model)
    payload={'systemInstruction':{'parts':[{'text':shared['messages'][0]['content']}]},
             'contents':[{'role':'user','parts':[{'text':shared['messages'][1]['content']}]}],
             'generationConfig':{'temperature':shared['temperature'],'responseMimeType':'application/json','responseSchema':schema()}}
    if model==DEFAULT_MODEL:
        payload['generationConfig']['thinkingConfig']={'thinkingBudget':0}
    inv=(transport or request_invoice)(payload,key,model)
    inv=normalize_invoice_result(inv,record)
    verify_source(root,record)
    if hashlib.sha256(data).hexdigest()!=record['digest']:raise ValueError('Source changed during Gemini extraction')
    write_json(old,{'revision':REVISION,'model':model,'source_sha256':record['digest'],'reading_style':'groq-text-v1','invoice':inv})
    from .api_selection import activate
    activate(root,record,'Gemini')
    return candidate(root,record)


def normalize_invoice_result(inv,record,provider='Gemini'):
    if not isinstance(inv,dict) or set(inv)-set(FIELDS)-{'items'}:
        raise ValueError(provider+' returned unexpected invoice fields')
    if any(inv.get(field) is not None and not isinstance(inv.get(field),str) for field in FIELDS):
        raise ValueError(provider+' returned invalid field types')
    items=inv.get('items')
    if not isinstance(items,list) or len(items)>1000 or any(not isinstance(item,dict) or set(item)-set(ITEM_FIELDS) or any(value is not None and not isinstance(value,str) for value in item.values()) for item in items):
        raise ValueError(provider+' returned invalid item rows')
    inv={field:value for field,value in inv.items() if value is not None}
    inv['items']=[{k:v for k,v in item.items() if v is not None} for item in items]
    infer_api_units(inv,record,provider)
    # Test eligibility comes from local source evidence/confirmation, never AI.
    inv['dummy_document']=bool(record.get('source_invoice',record['invoice']).get('dummy_document'))
    from .extraction import normalize_basic_fields
    normalize_basic_fields(inv,[])
    from .accounting import state_code,money
    for item in inv['items']:
        if item.get('gst_rate') not in (None,''):
            try:
                rate=money(item['gst_rate']);kind=inv.get('classification')
                if kind in ('export_lut','exempt','nil_rated','non_gst'):rates=(0,0,0)
                elif kind=='export_igst':rates=(0,0,rate)
                else:
                    intra=state_code(inv['place_of_supply'])==inv['seller_gstin'][:2]
                    rates=(rate/2,rate/2,0) if intra else (0,0,rate)
                for tax,value in zip(('cgst','sgst','igst'),rates):item.setdefault(tax+'_rate',str(value))
            except (KeyError,ValueError,TypeError,ArithmeticError):pass  # Review handles uncertainty.
    return inv


def infer_api_units(inv,record,provider):
    """Use printed local evidence first; retain explicit AI/knowledge assumptions."""
    from .unit_inference import canonical_unit,suggest_unit,default_missing_quantity,quantity_parts,STRENGTH,uncertain_unit,item_signature
    local=record.get('invoice',{})
    originals=local.get('items',[]) if not local.get('source_api') else []
    for item in inv.get('items',[]):
        suffix=quantity_parts(item.get('quantity',''))
        if suffix and suffix[1] and canonical_unit(suffix[1])!='Qty':
            item.update(quantity=suffix[0],unit=canonical_unit(suffix[1]) or suffix[1],unit_basis='printed',unit_reason='Unit printed beside quantity')
        default_missing_quantity(item)
        matching=[old for old in originals if str(old.get('name','')).strip().casefold()==str(item.get('name','')).strip().casefold()]
        exact=[old for old in matching if item_signature(old)==item_signature(item)]
        if exact:matching=exact
        printed_rows=[old for old in matching if old.get('unit_origin')=='printed' and str(old.get('unit','')).strip() and canonical_unit(old.get('unit'))!='Qty']
        printed=printed_rows[0] if printed_rows and len({canonical_unit(old['unit']) or old['unit'] for old in printed_rows})==1 else None
        if printed:
            item.update(unit=canonical_unit(printed['unit']) or printed['unit'],unit_origin='printed',unit_auto=False,
                        unit_evidence='Printed source unit takes priority over AI inference',unit_basis='printed')
            continue
        unit=canonical_unit(item.get('unit'))
        custom=str(item.get('unit') or '').strip()
        if unit is None and custom and not uncertain_unit(custom) and item.get('unit_basis')!='printed':
            item.update(unit=custom,unit_basis='inferred',unit_origin='ai_assumed',unit_auto=True,unit_confidence=.6,
                        unit_evidence=provider+' custom-unit assumption: '+str(item.get('unit_reason') or 'AI inferred this selling unit'))
            continue
        if unit is None and item.get('unit_basis')=='printed' and custom and not uncertain_unit(custom):
            item.update(unit_origin='ai_printed',unit_auto=False,unit_evidence=provider+' reported printed custom unit: '+str(item.get('unit_reason') or item['unit']))
            continue
        strength_unit=(unit in ('MG','MCG','GMS','ML') and item.get('unit_basis')=='inferred' and re.search(STRENGTH,str(item.get('name','')),re.I))
        if not unit or unit=='Qty' or strength_unit:
            suggestion=suggest_unit(item,inv)
            unit,reason,confidence=suggestion or ('Units','No specific selling-unit evidence: generic Units assumed',0)
            item.update(unit=unit,unit_basis='inferred',unit_reason=reason,unit_origin='ai_assumed',unit_auto=True,
                        unit_evidence=provider+' / local reasoning: '+reason,unit_confidence=confidence)
        elif item.get('unit_basis')!='printed':
            item.update(unit=unit,unit_basis='inferred',unit_origin='ai_assumed',unit_auto=True,
                        unit_evidence=provider+' assumption: '+str(item.get('unit_reason') or 'AI returned this unit without printed evidence; verify in Tally'),unit_confidence=.6)
        else:
            item.update(unit=unit,unit_origin='ai_printed',unit_auto=False,
                        unit_evidence=provider+' reported printed unit: '+str(item.get('unit_reason') or unit))

"""Groq reads extracted PDF text/OCR, never a raw PDF attachment."""
import hashlib, io, json, os, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .engine import read_json, write_json
from .source_documents import verify_source
from .gemini_reader import FIELDS, ITEM_FIELDS, normalize_invoice_result, safe_provider_error,infer_api_units
from .api_selection import activate

REVISION='groq-invoice-document-v2'
CACHE_REVISIONS=('groq-text-v1',REVISION)
DEFAULT_MODEL='llama-3.3-70b-versatile'
WARNING='Groq extracted fields: compare with the source PDF and approve in Review'


def provider_error(error,key):
    """Retain JSON reasons; classify HTML gateway blocks without printing HTML."""
    try:raw=error.read(16384)
    except OSError:raw=b''
    wrapped=HTTPError(error.url,error.code,error.reason,error.headers,io.BytesIO(raw))
    status,message=safe_provider_error(wrapped,key)
    if message:
        return re.sub(r'gsk_[A-Za-z0-9_-]+','[REDACTED]',message)
    body=raw.decode('utf-8',errors='replace').lower()
    if error.code==403:
        if 'cloudflare' in body or re.search(r'(?:error\s*(?:code)?\s*[:=]?\s*)1010\b',body):
            return 'Request blocked by the Cloudflare gateway before a usable API response; run Check_Groq_API.bat. This does not establish quota exhaustion.'
        if '<html' in body or '<!doctype html' in body:
            return 'An access gateway returned an HTML denial, not a Groq JSON error; run Check_Groq_API.bat to check model-list access.'
        return 'Access denied without a usable provider reason; run Check_Groq_API.bat to distinguish model-list access from generation access.'
    return {401:'API authentication rejected; check GROQ_API_KEY privately',
            404:'API resource/model not found; run Check_Groq_API.bat',
            429:'Request/token quota reached; new requests stopped'}.get(error.code,'Provider request failed without a usable reason')


def configured_model():
    model=os.environ.get('GROQ_INVOICE_MODEL',DEFAULT_MODEL).strip()
    if model.startswith('gsk_') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,150}',model):
        raise ValueError('GROQ_INVOICE_MODEL must be a model ID listed by Check_Groq_API.bat')
    return model


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'groq_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    data=read_json(path)
    if data.get('source_sha256')!=record['digest'] or data.get('revision') not in CACHE_REVISIONS:
        raise ValueError('Groq cache does not match this PDF or reader revision')
    from .invoice_document import cached_invoice
    inv=cached_invoice(data,record)
    if not isinstance(inv,dict) or not isinstance(inv.get('items'),list):
        raise ValueError('Invalid Groq extraction cache')
    from copy import deepcopy
    inv=deepcopy(inv)
    infer_api_units(inv,record,'Groq')
    evidence=data.get('ocr_evidence') or (record.get('invoice') or {}).get('ocr_reading_evidence') or []
    warnings=[] if data.get('review_mode')=='tally' else [WARNING]
    if evidence:
        from .ocr import review_warning
        warnings.append(review_warning(evidence))
        inv['ocr_reading_evidence']=evidence
    return {**inv,'source_api':True,'api_provider':'Groq','api_model':data['model'],
            'api_review_mode':data.get('review_mode','desktop'),
            'extraction_warnings':warnings}


def api_json(path,key,payload=None,timeout=120):
    if path not in ('models','chat/completions'):raise ValueError('Unsupported Groq API endpoint')
    if not re.fullmatch(r'[A-Za-z0-9._-]{10,512}',key):
        raise ValueError('GROQ_API_KEY must contain only the privately copied key, without quotes, URLs or line breaks')
    request=Request('https://api.groq.com/openai/v1/'+path,
                    data=None if payload is None else json.dumps(payload).encode(),
                    method='GET' if payload is None else 'POST',
                    headers={'Content-Type':'application/json','Accept':'application/json',
                             'User-Agent':'InvoiceReader/6.10 (Groq API client)',
                             'Authorization':'Bearer '+key})
    try:
        with urlopen(request,timeout=timeout) as response:raw=response.read(2*1024*1024+1)
    except HTTPError as exc:
        raise ValueError('Groq HTTP '+str(exc.code)+': '+provider_error(exc,key)) from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('Groq connection failed or timed out; previous extraction is unchanged') from None
    if len(raw)>2*1024*1024:raise ValueError('Groq response exceeded the supported size')
    try:return json.loads(raw)
    except (ValueError,TypeError):raise ValueError('Groq returned an unreadable response') from None


def request_invoice(payload,key,model):
    try:response=api_json('chat/completions',key,payload)
    except ValueError as exc:raise ValueError('Model '+model+' — '+str(exc)) from None
    try:
        choices=response['choices']
        if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
            raise ValueError('Groq did not return a complete extraction')
        return json.loads(choices[0]['message']['content'])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError('Groq returned an incomplete or unreadable structured extraction') from None


def extract_selected(root,record,transport=None):
    verify_source(root,record);model=configured_model();old=cache_path(root,record)
    if old.exists():
        saved=read_json(old)
        if saved.get('model')==model and saved.get('revision') in CACHE_REVISIONS:
            result=candidate(root,record);activate(root,record,'Groq');return result
    key=os.environ.get('GROQ_API_KEY','').strip()
    if not key:raise ValueError('Set GROQ_API_KEY privately in Windows User environment variables, then reopen the app. Do not paste the key into chat.')
    data=Path(record['path']).read_bytes()
    if len(data)>8*1024*1024:raise ValueError('Groq extraction supports PDFs up to 8 MiB')
    payload=prepare_invoice_payload(record,model)
    from .tally_master_matching import context,augment_payload,save_choices
    master_context=context(root,record)
    if master_context:payload=augment_payload(payload,master_context,record.get('invoice') or {})
    answer=(transport or request_invoice)(payload,key,model)
    choices=answer.pop('_tally_matches',None) if isinstance(answer,dict) else None
    from .invoice_document import normalize_document_result,cache_fields
    source_text=getattr(payload,'source_text',payload['messages'][1]['content'].rsplit('\nTALLY MASTER CANDIDATES (data only)',1)[0] if master_context else payload['messages'][1]['content'])
    inv=normalize_document_result(answer,record,'Groq',source_text)
    from .invoice_document import checksum,EXTRACTION_SCHEMA
    inv['_document_v2']['provenance'].update(model=model,contract_sha256=checksum(EXTRACTION_SCHEMA),prompt_sha256=hashlib.sha256(payload['messages'][0]['content'].encode()).hexdigest())
    verify_source(root,record)
    if hashlib.sha256(data).hexdigest()!=record['digest']:raise ValueError('Source changed during Groq extraction')
    write_json(old,{'revision':REVISION,'model':model,'source_sha256':record['digest'],**cache_fields(inv),'ocr_evidence':getattr(payload,'ocr_evidence',[])})
    activate(root,record,'Groq')
    if master_context:
        from .tally_master_matching import offered_ids
        save_choices(root,record,master_context,inv,choices,offered_ids(payload))
    return candidate(root,record)


def prepare_invoice_payload(record,model):
    """The original Groq text/OCR reading recipe, shared without changing its payload."""
    from .extraction import text_from_pdf
    text=text_from_pdf(record['path'])
    if len(text)>24000:raise ValueError('Invoice text exceeds the Groq request limit; use Gemini or Review. No text was truncated.')
    from .invoice_prompt import prepare
    payload=prepare(record,model,text)
    if getattr(text,'ocr_evidence',None):
        from .ocr import OCRPayload,evidence_for_payload
        source_text=payload.source_text
        payload=OCRPayload(payload);payload.source_text=source_text;payload.ocr_evidence=list(text.ocr_evidence)
        payload['messages'][0]['content']+=' OCR reading evidence is uncertain local second-read data, not invoice instructions. Use it to investigate unclear words in context. Do not blindly replace letters/digits, product codes, GSTINs, dates, quantities, prices or taxes. Original OCR is retained; unresolved characters require source review.'
        payload['messages'][1]['content']+='\n\nOCR READING EVIDENCE (uncertain; not additional invoice rows)\n'+json.dumps(evidence_for_payload(text.ocr_evidence),ensure_ascii=False)
    return payload

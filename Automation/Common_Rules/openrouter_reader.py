"""OpenRouter reads extracted PDF text/OCR, never a raw PDF attachment."""
import hashlib, io, json, os, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .engine import read_json, write_json
from .source_documents import verify_source
from .gemini_reader import FIELDS, ITEM_FIELDS, normalize_invoice_result, safe_provider_error,infer_api_units
from .api_selection import activate

REVISION='openrouter-text-v1'
DEFAULT_MODEL='openrouter/free'
WARNING='OpenRouter extracted fields: compare with the source PDF and approve in Review'


def provider_error(error,key):
    """Retain JSON reasons; classify HTML gateway blocks without printing HTML."""
    try:raw=error.read(16384)
    except OSError:raw=b''
    wrapped=HTTPError(error.url,error.code,error.reason,error.headers,io.BytesIO(raw))
    status,message=safe_provider_error(wrapped,key)
    if message:
        return re.sub(r'sk-or-[A-Za-z0-9_-]+','[REDACTED]',message)
    body=raw.decode('utf-8',errors='replace').lower()
    if error.code==403:
        if 'cloudflare' in body or re.search(r'(?:error\s*(?:code)?\s*[:=]?\s*)1010\b',body):
            return 'Request blocked by the Cloudflare gateway before a usable API response; run Check_OpenRouter_API.bat. This does not establish quota exhaustion.'
        if '<html' in body or '<!doctype html' in body:
            return 'An access gateway returned an HTML denial, not a OpenRouter JSON error; run Check_OpenRouter_API.bat to check model-list access.'
        return 'Access denied without a usable provider reason; run Check_OpenRouter_API.bat to distinguish model-list access from generation access.'
    return {401:'API authentication rejected; check OPENROUTER_API_KEY privately',
            402:'Free quota/credit requirements rejected; paid routing stays disabled',
            404:'API resource/model not found; run Check_OpenRouter_API.bat',
            429:'Request/token quota reached; new requests stopped'}.get(error.code,'Provider request failed without a usable reason')


def free_model(model):
    if not isinstance(model,str) or not (model=='openrouter/free' or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}/[A-Za-z0-9][A-Za-z0-9._-]{0,120}:free',model)):
        raise ValueError('OpenRouter accepts only openrouter/free or an explicit :free model. Paid model routing is disabled.')
    return model


def configured_model():
    return free_model(os.environ.get('OPENROUTER_INVOICE_MODEL',DEFAULT_MODEL).strip())


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'openrouter_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    data=read_json(path)
    if data.get('source_sha256')!=record['digest'] or data.get('revision')!=REVISION:
        raise ValueError('OpenRouter cache does not match this PDF or reader revision')
    inv=data.get('invoice')
    if not isinstance(inv,dict) or not isinstance(inv.get('items'),list):
        raise ValueError('Invalid OpenRouter extraction cache')
    from copy import deepcopy
    inv=deepcopy(inv)
    infer_api_units(inv,record,'OpenRouter')
    return {**inv,'source_api':True,'api_provider':'OpenRouter','api_model':data['model'],
            'api_review_mode':data.get('review_mode','desktop'),
            'extraction_warnings':[] if data.get('review_mode')=='tally' else [WARNING]}


def api_json(path,key,payload=None,timeout=120):
    if path not in ('models','chat/completions'):raise ValueError('Unsupported OpenRouter API endpoint')
    if not re.fullmatch(r'[A-Za-z0-9._-]{10,512}',key):
        raise ValueError('OPENROUTER_API_KEY must contain only the privately copied key, without quotes, URLs or line breaks')
    if payload is not None:
        payload=dict(payload)
        free_model(payload.get('model'))
        if 'models' in payload or 'plugins' in payload:raise ValueError('OpenRouter alternate routes/plugins are disabled for free-only extraction')
        payload['provider']={'max_price':{'prompt':0,'completion':0}}
    request=Request('https://openrouter.ai/api/v1/'+path,
                    data=None if payload is None else json.dumps(payload).encode(),
                    method='GET' if payload is None else 'POST',
                    headers={'Content-Type':'application/json','Accept':'application/json',
                             'User-Agent':'InvoiceReader/7.13 (OpenRouter free-only client)',
                             'Authorization':'Bearer '+key})
    try:
        with urlopen(request,timeout=timeout) as response:raw=response.read(2*1024*1024+1)
    except HTTPError as exc:
        raise ValueError('OpenRouter HTTP '+str(exc.code)+': '+provider_error(exc,key)) from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('OpenRouter connection failed or timed out; previous extraction is unchanged') from None
    if len(raw)>2*1024*1024:raise ValueError('OpenRouter response exceeded the supported size')
    try:return json.loads(raw)
    except (ValueError,TypeError):raise ValueError('OpenRouter returned an unreadable response') from None


def request_invoice(payload,key,model):
    try:response=api_json('chat/completions',key,payload)
    except ValueError as exc:raise ValueError('Model '+model+' — '+str(exc)) from None
    try:
        choices=response['choices']
        if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
            raise ValueError('OpenRouter did not return a complete extraction')
        return json.loads(choices[0]['message']['content'])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError('OpenRouter returned an incomplete or unreadable structured extraction') from None


def extract_selected(root,record,transport=None):
    verify_source(root,record);model=configured_model();old=cache_path(root,record)
    if old.exists():
        saved=read_json(old)
        if saved.get('model')==model and saved.get('revision')==REVISION:
            result=candidate(root,record);activate(root,record,'OpenRouter');return result
    key=os.environ.get('OPENROUTER_API_KEY','').strip()
    if not key:raise ValueError('Set OPENROUTER_API_KEY privately in Windows User environment variables, then reopen the app. Do not paste the key into chat.')
    data=Path(record['path']).read_bytes()
    if len(data)>8*1024*1024:raise ValueError('OpenRouter extraction supports PDFs up to 8 MiB')
    from .groq_reader import prepare_invoice_payload
    payload=prepare_invoice_payload(record,model)
    payload['max_tokens']=min(payload.pop('max_completion_tokens'),4000)
    payload['provider']={'max_price':{'prompt':0,'completion':0}}
    inv=normalize_invoice_result((transport or request_invoice)(payload,key,model),record,'OpenRouter')
    verify_source(root,record)
    if hashlib.sha256(data).hexdigest()!=record['digest']:raise ValueError('Source changed during OpenRouter extraction')
    write_json(old,{'revision':REVISION,'model':model,'source_sha256':record['digest'],'invoice':inv,'reading_style':'groq-text-v1'})
    activate(root,record,'OpenRouter')
    return candidate(root,record)


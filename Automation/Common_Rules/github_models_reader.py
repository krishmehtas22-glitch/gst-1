"""GitHub Models reads extracted PDF text/OCR, never a raw PDF attachment."""
import gzip,hashlib, io, json, os, re,zlib
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .engine import read_json, write_json
from .source_documents import verify_source
from .gemini_reader import FIELDS, ITEM_FIELDS, normalize_invoice_result, safe_provider_error,infer_api_units
from .api_selection import activate

REVISION='github-models-text-v1'
DEFAULT_MODEL='openai/gpt-4o'
WARNING='GitHub Models extracted fields: compare with the source PDF and approve in Review'


def provider_error(error,key):
    """Retain JSON reasons; classify HTML gateway blocks without printing HTML."""
    try:raw=error.read(16384)
    except OSError:raw=b''
    wrapped=HTTPError(error.url,error.code,error.reason,error.headers,io.BytesIO(raw))
    status,message=safe_provider_error(wrapped,key)
    if message:
        return re.sub(r'(?:github_pat_|ghp_|csk_|gsk_)[A-Za-z0-9_-]+','[REDACTED]',message)
    body=raw.decode('utf-8',errors='replace').lower()
    if error.code==403:
        if 'cloudflare' in body or re.search(r'(?:error\s*(?:code)?\s*[:=]?\s*)1010\b',body):
            return 'Request blocked by the Cloudflare gateway before a usable API response; run Check_GitHub_Models_API.bat. This does not establish quota exhaustion.'
        if '<html' in body or '<!doctype html' in body:
            return 'An access gateway returned an HTML denial, not a GitHub Models JSON error; run Check_GitHub_Models_API.bat to check model-list access.'
        return 'Access denied without a usable provider reason; run Check_GitHub_Models_API.bat to distinguish model-list access from generation access.'
    return {401:'API authentication rejected; check GITHUB_MODELS_TOKEN privately',
            404:'API resource/model not found; run Check_GitHub_Models_API.bat',
            429:'Request/token quota reached; new requests stopped'}.get(error.code,'Provider request failed without a usable reason')


def configured_model():
    model=os.environ.get('GITHUB_INVOICE_MODEL',DEFAULT_MODEL).strip()
    if model.startswith(('github_pat_','ghp_','csk_','gsk_','sk-')) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,150}',model):
        raise ValueError('GITHUB_INVOICE_MODEL must be a model ID listed by Check_GitHub_Models_API.bat')
    return model


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'github_models_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    data=read_json(path)
    if data.get('source_sha256')!=record['digest'] or data.get('revision')!=REVISION:
        raise ValueError('GitHub Models cache does not match this PDF or reader revision')
    inv=data.get('invoice')
    if not isinstance(inv,dict) or not isinstance(inv.get('items'),list):
        raise ValueError('Invalid GitHub Models extraction cache')
    from copy import deepcopy
    inv=deepcopy(inv)
    infer_api_units(inv,record,'GitHub Models')
    return {**inv,'source_api':True,'api_provider':'GitHub Models','api_model':data['model'],
            'api_review_mode':data.get('review_mode','desktop'),
            'extraction_warnings':[] if data.get('review_mode')=='tally' else [WARNING]}


def decode_response(response,path):
    """Bounded HTTP decoding; classify non-JSON pages without echoing bodies."""
    limit=2*1024*1024
    raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('GitHub Models response exceeded the supported size')
    headers=getattr(response,'headers',{})
    encoding=str(headers.get('Content-Encoding','')).strip().lower()
    try:
        if encoding=='gzip' or raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(limit+1)
        elif encoding=='deflate':
            try:
                decoder=zlib.decompressobj();raw=decoder.decompress(raw,limit+1)
            except zlib.error:
                decoder=zlib.decompressobj(-zlib.MAX_WBITS);raw=decoder.decompress(raw,limit+1)
            if decoder.unconsumed_tail or len(raw)>limit:raise ValueError('GitHub Models decompressed response exceeded the supported size')
            if not decoder.eof:raise ValueError('GitHub Models returned an incomplete compressed response')
        elif encoding not in ('','identity'):
            raise ValueError('GitHub Models returned unsupported response compression')
    except (OSError,EOFError,zlib.error):
        raise ValueError('GitHub Models returned damaged compressed data; no response body was printed') from None
    if len(raw)>limit:raise ValueError('GitHub Models decompressed response exceeded the supported size')
    if not raw.strip():raise ValueError('GitHub Models returned an empty response; token access is not verified')
    head=raw.lstrip(b'\xef\xbb\xbf \t\r\n')[:100].lower()
    if 'text/html' in str(headers.get('Content-Type','')).lower() or head.startswith((b'<!doctype html',b'<html')):
        raise ValueError('GitHub Models returned an HTML page instead of API JSON (possible sign-in/proxy/network page); token access is not verified')
    try:data=json.loads(raw)
    except (ValueError,TypeError):
        raise ValueError('GitHub Models returned non-JSON data after HTTP decoding; no token or response body was printed') from None
    if not isinstance(data,(dict,list)) or (path!='models' and not isinstance(data,dict)):
        raise ValueError('GitHub Models returned an unexpected JSON structure')
    return data


def api_json(path,key,payload=None,timeout=120):
    if path not in ('models','chat/completions'):raise ValueError('Unsupported GitHub Models API endpoint')
    if not re.fullmatch(r'[A-Za-z0-9._-]{10,512}',key):
        raise ValueError('GITHUB_MODELS_TOKEN must contain only the privately copied key, without quotes, URLs or line breaks')
    endpoint='https://models.github.ai/catalog/models' if path=='models' else 'https://models.github.ai/inference/chat/completions'
    request=Request(endpoint,
                    data=None if payload is None else json.dumps(payload).encode(),
                    method='GET' if payload is None else 'POST',
                    headers={'Content-Type':'application/json','Accept':'application/vnd.github+json' if path=='models' else 'application/json',
                             'Accept-Encoding':'identity','User-Agent':'InvoiceReader/7.7 (GitHub Models API client)',
                             'Authorization':'Bearer '+key,'X-GitHub-Api-Version':'2022-11-28'})
    try:
        with urlopen(request,timeout=timeout) as response:return decode_response(response,path)
    except HTTPError as exc:
        raise ValueError('GitHub Models HTTP '+str(exc.code)+': '+provider_error(exc,key)) from None
    except (URLError,TimeoutError,OSError):
        raise ValueError('GitHub Models connection failed or timed out; previous extraction is unchanged') from None


def request_invoice(payload,key,model):
    try:response=api_json('chat/completions',key,payload)
    except ValueError as exc:raise ValueError('Model '+model+' — '+str(exc)) from None
    try:
        choices=response['choices']
        if len(choices)!=1 or choices[0].get('finish_reason')!='stop':
            raise ValueError('GitHub Models did not return a complete extraction')
        return json.loads(choices[0]['message']['content'])
    except (ValueError,KeyError,TypeError) as exc:
        raise ValueError('GitHub Models returned an incomplete or unreadable structured extraction') from None


def extract_selected(root,record,transport=None):
    verify_source(root,record);model=configured_model();old=cache_path(root,record)
    if old.exists():
        saved=read_json(old)
        if saved.get('model')==model and saved.get('revision')==REVISION:
            result=candidate(root,record);activate(root,record,'GitHub Models');return result
    key=os.environ.get('GITHUB_MODELS_TOKEN','').strip()
    if not key:raise ValueError('Set GITHUB_MODELS_TOKEN privately in Windows User environment variables, then reopen the app. Do not paste the key into chat.')
    data=Path(record['path']).read_bytes()
    if len(data)>8*1024*1024:raise ValueError('GitHub Models extraction supports PDFs up to 8 MiB')
    from .groq_reader import prepare_invoice_payload
    payload=prepare_invoice_payload(record,model)
    # Preserve the shared input/prompt; adapt only GitHub's transport budget.
    payload['max_tokens']=min(payload.pop('max_completion_tokens'),4000)
    inv=normalize_invoice_result((transport or request_invoice)(payload,key,model),record,'GitHub Models')
    verify_source(root,record)
    if hashlib.sha256(data).hexdigest()!=record['digest']:raise ValueError('Source changed during GitHub Models extraction')
    write_json(old,{'revision':REVISION,'model':model,'source_sha256':record['digest'],'reading_style':'groq-text-v1','invoice':inv})
    activate(root,record,'GitHub Models')
    return candidate(root,record)

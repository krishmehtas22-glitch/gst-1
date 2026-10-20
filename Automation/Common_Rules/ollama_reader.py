"""Explicit, local-only Gemma extraction through Ollama; never downloads models."""
import json,hashlib
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import URLError,HTTPError
from .engine import read_json,write_json
from .source_documents import verify_source
from .gemini_reader import normalize_invoice_result,infer_api_units
from .api_selection import activate

PROVIDER='Gemma (local)'
REVISION='ollama-invoice-document-v2'
CACHE_REVISIONS=('ollama-gemma-text-v1',REVISION)
DEFAULT_MODEL='gemma3:4b'
ENDPOINT='http://127.0.0.1:11434/api/chat'


def configured_model():return DEFAULT_MODEL


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'ollama_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    saved=read_json(path)
    if saved.get('source_sha256')!=record['digest'] or saved.get('revision') not in CACHE_REVISIONS or saved.get('model')!=DEFAULT_MODEL:
        raise ValueError('Local Gemma cache does not match this source or model')
    from copy import deepcopy
    from .invoice_document import cached_invoice
    inv=cached_invoice(saved,record)
    if not isinstance(inv,dict) or not isinstance(inv.get('items'),list):raise ValueError('Invalid local Gemma extraction cache')
    infer_api_units(inv,record,PROVIDER)
    warnings=['Local Gemma extraction: compare seller, buyer, items and amounts with the source invoice.']
    evidence=saved.get('ocr_evidence') or []
    if evidence:
        from .ocr import review_warning
        warnings.append(review_warning(evidence));inv['ocr_reading_evidence']=evidence
    return {**inv,'source_api':True,'api_provider':PROVIDER,'api_model':DEFAULT_MODEL,
            'api_review_mode':saved.get('review_mode','desktop'),'extraction_warnings':warnings}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def request_invoice(payload,key,model):
    # Fixed loopback endpoint and no proxy/redirect: no cloud credentials or calls.
    input_bytes=len(json.dumps(payload['messages'],ensure_ascii=False).encode())
    room=16384-input_bytes-512
    if room<1024:raise ValueError('Invoice and context exceed the local model limit. Split/review the source or explicitly choose Groq. No invoice text was truncated and no local request was sent.')
    body={'model':DEFAULT_MODEL,'messages':payload['messages'],'stream':False,'format':'json',
          'options':{'temperature':0,'num_ctx':16384,'num_predict':min(8000,room)}}
    request=Request(ENDPOINT,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=300) as response:
            raw=response.read(2*1024*1024+1)
    except HTTPError as exc:
        if exc.code==404:raise ValueError('Gemma model unavailable. In CMD run: ollama pull gemma3:4b. No cloud fallback or model download was started.') from None
        raise ValueError('Ollama HTTP '+str(exc.code)+': local extraction failed; no cloud fallback was sent.') from None
    except (URLError,OSError,TimeoutError):
        raise ValueError('Cannot read from local Ollama, or the request timed out. Keep Ollama running with gemma3:4b installed. No retry or cloud fallback was sent.') from None
    if len(raw)>2*1024*1024:raise ValueError('Ollama response exceeded the supported size')
    try:
        response=json.loads(raw)
        if response.get('done') is not True or response.get('done_reason') not in (None,'stop') or response.get('error'):
            raise ValueError('Incomplete local extraction')
        answer=json.loads(response['message']['content'])
        if not isinstance(answer,dict):raise ValueError('Expected invoice object')
        return answer
    except (ValueError,KeyError,TypeError,AttributeError):
        raise ValueError('Gemma returned incomplete or invalid invoice JSON; previous extraction is unchanged.') from None


def extract_selected(root,record,transport=None):
    verify_source(root,record);model=DEFAULT_MODEL;path=cache_path(root,record)
    if path.exists():
        saved=read_json(path)
        if saved.get('model')==model and saved.get('revision') in CACHE_REVISIONS:
            result=candidate(root,record);activate(root,record,PROVIDER);return result
    from .groq_reader import prepare_invoice_payload
    from .tally_master_matching import context,augment_payload,save_choices,offered_ids
    payload=prepare_invoice_payload(record,model)
    master_context=context(root,record)
    if master_context:payload=augment_payload(payload,master_context,record.get('invoice') or {})
    answer=(transport or request_invoice)(payload,None,model)
    choices=answer.pop('_tally_matches',None) if isinstance(answer,dict) else None
    from .invoice_document import normalize_document_result,cache_fields
    source_text=getattr(payload,'source_text',payload['messages'][1]['content'].rsplit('\nTALLY MASTER CANDIDATES (data only)',1)[0] if master_context else payload['messages'][1]['content'])
    inv=normalize_document_result(answer,record,PROVIDER,source_text)
    from .invoice_document import checksum,EXTRACTION_SCHEMA
    inv['_document_v2']['provenance'].update(model=model,contract_sha256=checksum(EXTRACTION_SCHEMA),prompt_sha256=hashlib.sha256(payload['messages'][0]['content'].encode()).hexdigest())
    verify_source(root,record)
    write_json(path,{'revision':REVISION,'model':model,'source_sha256':record['digest'],
                     **cache_fields(inv),'ocr_evidence':getattr(payload,'ocr_evidence',[])})
    activate(root,record,PROVIDER)
    if master_context:save_choices(root,record,master_context,inv,choices,offered_ids(payload))
    return candidate(root,record)


def match_cached(root,record,budget,stop_event=None,transport=None):
    """Keep matching of reviewed/cached local sources on the local model too."""
    from .tally_master_matching import context,loaded_choices,save_choices,matching_payload,offered_ids
    ctx=context(root,record)
    if not ctx or loaded_choices(root,record,ctx) is not None:return False
    inv=record.get('invoice') or {}
    if not inv.get('buyer_name') and not inv.get('items'):return False
    if not any(ctx['data'].get(kind) for kind in ('ledgers','stock_items','units')):return False
    if (stop_event and stop_event.is_set()) or not budget.claim():return False
    payload=matching_payload(DEFAULT_MODEL,inv,ctx)
    answer=(transport or request_invoice)(payload,None,DEFAULT_MODEL)
    verify_source(root,record)
    save_choices(root,record,ctx,inv,answer.get('_tally_matches'),offered_ids(payload))
    return True

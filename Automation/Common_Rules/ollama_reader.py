"""Explicit, local-only Gemma extraction through Ollama; never downloads models."""
import json
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import URLError,HTTPError
from .engine import read_json,write_json
from .source_documents import verify_source
from .gemini_reader import normalize_invoice_result,infer_api_units
from .api_selection import activate

PROVIDER='Gemma (local)'
REVISION='ollama-gemma-text-v1'
DEFAULT_MODEL='gemma3:4b'
ENDPOINT='http://127.0.0.1:11434/api/chat'


def configured_model():return DEFAULT_MODEL


def cache_path(root,record):
    return Path(root)/'.invoice_app'/'ollama_extraction'/(record['digest']+'.json')


def candidate(root,record):
    path=cache_path(root,record)
    if not path.exists():return None
    saved=read_json(path)
    if saved.get('source_sha256')!=record['digest'] or saved.get('revision')!=REVISION or saved.get('model')!=DEFAULT_MODEL:
        raise ValueError('Local Gemma cache does not match this source or model')
    from copy import deepcopy
    inv=deepcopy(saved.get('invoice'))
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
    body={'model':DEFAULT_MODEL,'messages':payload['messages'],'stream':False,'format':'json',
          'options':{'temperature':0,'num_ctx':16384,'num_predict':8000}}
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
        if saved.get('model')==model and saved.get('revision')==REVISION:
            result=candidate(root,record);activate(root,record,PROVIDER);return result
    from .groq_reader import prepare_invoice_payload
    from .tally_master_matching import context,augment_payload,save_choices,shortlist
    payload=prepare_invoice_payload(record,model)
    master_context=context(root,record)
    if master_context:payload=augment_payload(payload,master_context,record.get('invoice') or {})
    answer=(transport or request_invoice)(payload,None,model)
    choices=answer.pop('_tally_matches',None) if isinstance(answer,dict) else None
    inv=normalize_invoice_result(answer,record,PROVIDER)
    verify_source(root,record)
    write_json(path,{'revision':REVISION,'model':model,'source_sha256':record['digest'],
                     'invoice':inv,'ocr_evidence':getattr(payload,'ocr_evidence',[])})
    activate(root,record,PROVIDER)
    if master_context:save_choices(root,record,master_context,inv,choices,shortlist(master_context,record.get('invoice') or {}))
    return candidate(root,record)


def match_cached(root,record,budget,stop_event=None,transport=None):
    """Keep matching of reviewed/cached local sources on the local model too."""
    from .tally_master_matching import context,loaded_choices,shortlist,save_choices,INSTRUCTION
    ctx=context(root,record)
    if not ctx or loaded_choices(root,record,ctx) is not None:return False
    inv=record.get('invoice') or {}
    if not inv.get('buyer_name') and not inv.get('items'):return False
    if not any(ctx['data'].get(kind) for kind in ('ledgers','stock_items','units')):return False
    if (stop_event and stop_event.is_set()) or not budget.claim():return False
    payload={'messages':[{'role':'system','content':INSTRUCTION+' Return only {"_tally_matches": ...}.'},
                         {'role':'user','content':json.dumps({'invoice':inv,'masters':shortlist(ctx,inv)},ensure_ascii=False)}]}
    answer=(transport or request_invoice)(payload,None,DEFAULT_MODEL)
    verify_source(root,record)
    save_choices(root,record,ctx,inv,answer.get('_tally_matches'))
    return True

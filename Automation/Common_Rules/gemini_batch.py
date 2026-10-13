"""Explicit batch extraction with a paced queue and durable per-PDF results."""
import time
from pathlib import Path
from .engine import read_json, write_json
from .source_documents import verify_source, confirm_test_document


def read_batch(root, records, progress=lambda message: None, extract=None,
               wait=time.sleep, clock=time.monotonic, provider='Gemini', confirm_test=False):
    from . import gemini_reader, groq_reader
    if provider not in ('Gemini','Groq'):raise ValueError('Unknown invoice API provider')
    reader=gemini_reader if provider=='Gemini' else groq_reader
    extract=extract or reader.extract_selected
    cache_path=reader.cache_path;configured_model=reader.configured_model;REVISION=reader.REVISION
    results=[];last_request=None;model=configured_model();stopped=False
    for index,record in enumerate(records,1):
        progress(f'{provider} batch {index}/{len(records)}: '+record.get('invoice',{}).get('number',Path(record['path']).name))
        result={'client':record['client'],'path':record['path'],'digest':record.get('digest'),'status':'failed'}
        try:
            verify_source(root,record)
            path=cache_path(root,record)
            saved=read_json(path) if path.exists() else {}
            cached=(saved.get('model')==model and saved.get('revision')==REVISION and saved.get('source_sha256')==record['digest'])
            if stopped and not cached:
                result.update(status='not attempted',error=f'Batch stopped after {provider} access/model/quota error; no cached extraction available')
                results.append(result)
                continue
            if not cached:
                if last_request is not None:wait(max(0,13-(clock()-last_request)))
                last_request=clock()
            extract(root,record)
            verify_source(root,record)
            saved=read_json(path)
            # Explicit batch choice defers comparison to Tally. Never record
            # a human approval or change saved financial/import history.
            saved['review_mode']='tally'
            write_json(path,saved)
            if confirm_test:confirm_test_document(root,record)
            result.update(status='extracted',cached=cached,review_mode='tally')
        except (ValueError,OSError,KeyError,TypeError) as exc:
            result['error']=str(exc)
        results.append(result)
        if any(provider+' HTTP '+str(code) in result.get('error','') for code in (401,403,404,429)):
            stopped=True  # Keep applying cached successes without more API calls.
    write_json(Path(root)/'.invoice_app'/(provider.lower()+'_batch_results.json'),{'provider':provider,'results':results})
    return results

"""Explicit batch extraction with a paced queue and durable per-PDF results."""
import time
from pathlib import Path
from .gemini_reader import extract_selected, cache_path, configured_model, REVISION
from .engine import read_json, write_json
from .source_documents import verify_source


def read_batch(root, records, progress=lambda message: None, extract=extract_selected,
               wait=time.sleep, clock=time.monotonic):
    results=[];last_request=None;model=configured_model()
    for index,record in enumerate(records,1):
        progress(f'Gemini batch {index}/{len(records)}: '+record.get('invoice',{}).get('number',Path(record['path']).name))
        result={'client':record['client'],'path':record['path'],'digest':record.get('digest'),'status':'failed'}
        try:
            verify_source(root,record)
            path=cache_path(root,record)
            saved=read_json(path) if path.exists() else {}
            cached=(saved.get('model')==model and saved.get('revision')==REVISION and saved.get('source_sha256')==record['digest'])
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
            result.update(status='extracted',cached=cached,review_mode='tally')
        except (ValueError,OSError,KeyError,TypeError) as exc:
            result['error']=str(exc)
        results.append(result)
        if 'Gemini HTTP 429' in result.get('error',''):
            for pending in records[index:]:
                results.append({'client':pending['client'],'path':pending['path'],'digest':pending.get('digest'),
                                'status':'not attempted','error':'Batch stopped: Gemini quota/rate limit reached'})
            break
    write_json(Path(root)/'.invoice_app'/'gemini_batch_results.json',{'results':results})
    return results

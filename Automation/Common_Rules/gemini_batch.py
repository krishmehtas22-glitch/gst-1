"""Explicit batch extraction with a paced queue and durable per-PDF results."""
import time
import os
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
        except Exception as exc:
            result['error']=provider+' extraction failed ('+type(exc).__name__+'); previous successful reads retained'
        results.append(result)
        if any(provider+' HTTP '+str(code) in result.get('error','') for code in (401,403,404,429)):
            stopped=True  # Keep applying cached successes without more API calls.
    write_json(Path(root)/'.invoice_app'/(provider.lower()+'_batch_results.json'),{'provider':provider,'results':results})
    return results


def read_with_fallback(root,records,primary='Gemini',progress=lambda message:None,confirm_test=False,
                       batch_reader=read_batch):
    """Retain each success, then try the other configured API and finally Python."""
    from .tally_review_export import enable
    for client in {r['client'] for r in records}:enable(root,client)
    providers=[primary,'Groq' if primary=='Gemini' else 'Gemini'];remaining=list(records);results={}
    for provider in providers:
        if not remaining:break
        from . import gemini_reader,groq_reader
        reader=gemini_reader if provider=='Gemini' else groq_reader
        if provider!=primary and not os.environ.get(provider.upper()+'_API_KEY','').strip() and not any(reader.cache_path(root,r).exists() for r in remaining):continue
        progress('Reading remaining invoices with '+provider+'; successful prior reads are retained')
        try:attempts=batch_reader(root,remaining,provider=provider,progress=progress,confirm_test=confirm_test)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            attempts=[{'status':'failed','error':str(exc)} for _ in remaining]
        except Exception as exc:
            attempts=[{'status':'failed','error':provider+' batch failed ('+type(exc).__name__+'); using remaining fallback'} for _ in remaining]
        for record,result in zip(remaining,attempts):
            token=(record['client'],record.get('digest'),record['path'])
            result['provider']=provider;results.setdefault(token,{'attempts':[]})['attempts'].append(result)
            if result['status']=='extracted':results[token].update(status='extracted',provider=provider)
        remaining=[r for r in remaining if results[(r['client'],r.get('digest'),r['path'])].get('status')!='extracted']
    for record in remaining:
        token=(record['client'],record.get('digest'),record['path'])
        results.setdefault(token,{'attempts':[]}).update(status='local fallback',provider='Python')
        if confirm_test and record.get('digest'):
            try:confirm_test_document(root,record)
            except (ValueError,OSError):results[token]['confirmation_note']='Source could not be confirmed; retained for Tally review'
    final=[{'client':r['client'],'path':r['path'],'digest':r.get('digest'),**results[(r['client'],r.get('digest'),r['path'])]} for r in records]
    write_json(Path(root)/'.invoice_app'/'ai_batch_results.json',{'results':final})
    return final

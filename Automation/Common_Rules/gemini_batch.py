"""Explicit batch extraction with a paced queue and durable per-PDF results."""
import time
import os
from pathlib import Path
from .engine import read_json, write_json
from .source_documents import verify_source, confirm_test_document


def retained_result(root, record, provider=None):
    """A verified saved extraction is success, independent of batch bookkeeping."""
    from .ai_providers import reader
    from .api_selection import activate
    try:
        verify_source(root, record)
        if provider is None:
            selected=read_json(Path(root)/'.invoice_app'/'api_selection'/(record['digest']+'.json'))
            if selected.get('source_sha256')!=record['digest']:return None
            provider=selected.get('provider')
        source=reader(provider)
        if source.candidate(root,record) is None:return None
        result={'status':'extracted','provider':provider,'cached':True,'review_mode':'tally'}
        try:
            path=source.cache_path(root,record)
            saved=read_json(path);saved['review_mode']='tally';write_json(path,saved)
            activate(root,record,provider)
        except OSError as exc:
            result['bookkeeping_note']=str(exc)
        return result
    except (ValueError,OSError,KeyError,TypeError):return None


def read_batch(root, records, progress=lambda message: None, extract=None,
               wait=time.sleep, clock=time.monotonic, provider='Gemini', confirm_test=False, stop_event=None):
    from .ai_providers import reader as get_reader,INTERVALS
    reader=get_reader(provider)
    extract=extract or reader.extract_selected
    cache_path=reader.cache_path;configured_model=reader.configured_model;REVISION=reader.REVISION
    results=[];last_request=None;model=configured_model();stopped=False
    for index,record in enumerate(records,1):
        if stop_event is not None and stop_event.is_set():break
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
                if last_request is not None:
                    delay=max(0,INTERVALS[provider]-(clock()-last_request))
                    if stop_event is not None:
                        if stop_event.wait(delay):break
                    else:wait(delay)
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
        if result['status']!='extracted':
            retained=retained_result(root,record,provider)
            if retained:result.update(retained)
        results.append(result)
        if any(provider+' HTTP '+str(code) in result.get('error','') for code in (401,403,404,429)):
            stopped=True  # Keep applying cached successes without more API calls.
    write_json(Path(root)/'.invoice_app'/(provider.lower().replace(' ','_')+'_batch_results.json'),{'provider':provider,'results':results})
    return results


def read_with_fallback(root,records,primary='Gemini',progress=lambda message:None,confirm_test=False,
                       batch_reader=read_batch,stop_event=None):
    """Retain each success, then try the other configured API and finally Python."""
    from .tally_review_export import enable
    for client in {r['client'] for r in records}:enable(root,client)
    from .ai_providers import PROVIDERS,ACTIVE_PROVIDERS,KEY_VARIABLES,reader as get_reader
    if primary not in PROVIDERS:raise ValueError('Unknown invoice API provider')
    providers=[primary]+[p for p in ACTIVE_PROVIDERS if p!=primary];remaining=list(records);results={}
    # Never replace a successful selected read just because another button was used.
    for record in records:
        retained=retained_result(root,record)
        if retained:
            token=(record['client'],record.get('digest'),record['path'])
            results[token]={**retained,'attempts':[]}
    remaining=[r for r in remaining if (r['client'],r.get('digest'),r['path']) not in results]
    for provider in providers:
        if not remaining or (stop_event is not None and stop_event.is_set()):break
        reader=get_reader(provider)
        if provider!=primary and not os.environ.get(KEY_VARIABLES[provider],'').strip() and not any(reader.cache_path(root,r).exists() for r in remaining):continue
        progress(f'Reading {len(remaining)} remaining invoices with {provider}; {len(records)-len(remaining)} successful prior reads are retained')
        try:
            options={'provider':provider,'progress':progress,'confirm_test':confirm_test}
            if stop_event is not None:options['stop_event']=stop_event
            attempts=batch_reader(root,remaining,**options)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            attempts=[{'status':'failed','error':str(exc)} for _ in remaining]
        except Exception as exc:
            attempts=[{'status':'failed','error':provider+' batch failed ('+type(exc).__name__+'); using remaining fallback'} for _ in remaining]
        for index,record in enumerate(remaining):
            result=attempts[index] if index<len(attempts) else {'status':'not attempted'}
            if result.get('status')!='extracted':
                retained=retained_result(root,record,provider)
                if retained:result={**result,**retained}
            token=(record['client'],record.get('digest'),record['path'])
            result['provider']=provider;results.setdefault(token,{'attempts':[]})['attempts'].append(result)
            if result['status']=='extracted':results[token].update(status='extracted',provider=provider)
        remaining=[r for r in remaining if results[(r['client'],r.get('digest'),r['path'])].get('status')!='extracted']
    for record in remaining:
        token=(record['client'],record.get('digest'),record['path'])
        results.setdefault(token,{'attempts':[]}).update(status='local fallback',provider='Python')
        if stop_event is not None and stop_event.is_set():results[token]['ai_stopped']=True
        if confirm_test and record.get('digest'):
            try:confirm_test_document(root,record)
            except (ValueError,OSError):results[token]['confirmation_note']='Source could not be confirmed; retained for Tally review'
    if confirm_test:
        for record in records:
            token=(record['client'],record.get('digest'),record['path'])
            if results[token]['status']=='extracted':
                try:confirm_test_document(root,record)
                except (ValueError,OSError):results[token]['confirmation_note']='Saved extraction retained; test confirmation could not be saved'
    final=[{'client':r['client'],'path':r['path'],'digest':r.get('digest'),**results[(r['client'],r.get('digest'),r['path'])]} for r in records]
    write_json(Path(root)/'.invoice_app'/'ai_batch_results.json',{'results':final})
    return final

"""Explicit batch extraction with a paced queue and durable per-PDF results."""
import time
import os
import threading
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


def find_retained(root,record,primary):
    """Recover orphaned saved reads before spending quota with any provider."""
    # An explicit local choice never switches to a cloud provider's extraction.
    if primary=='Gemma (local)':return retained_result(root,record,primary)
    saved=retained_result(root,record)
    if saved:return saved
    from .ai_providers import ACTIVE_PROVIDERS
    for provider in [primary]+[p for p in ACTIVE_PROVIDERS if p!=primary]:
        saved=retained_result(root,record,provider)
        if saved:return saved
    return None


def save_report(path,data,progress):
    try:write_json(path,data)
    except OSError:
        progress('Batch report could not be saved; retained AI reads will still be used for XML.')


class RequestBudget:
    """Conservative cap on fresh extraction attempts, shared by all providers."""
    def __init__(self,limit):
        self.limit=max(0,int(limit));self.used=0;self._lock=threading.Lock()
    def claim(self):
        with self._lock:
            if self.used>=self.limit:return False
            self.used+=1;return True


def read_batch(root, records, progress=lambda message: None, extract=None,
               wait=time.sleep, clock=time.monotonic, provider='Gemini', confirm_test=False, stop_event=None,on_result=None,request_budget=None,*,_parallel=True,_save_report=True):
    if provider=='Gemma (local)' and _parallel and len(records)>1:
        from .local_parallel import read_local_batch
        return read_local_batch(root,records,progress,extract,wait,clock,confirm_test,stop_event,on_result,request_budget)
    from .ai_providers import reader as get_reader,INTERVALS
    reader=get_reader(provider)
    extract=extract or reader.extract_selected
    cache_path=reader.cache_path;configured_model=reader.configured_model;REVISION=reader.REVISION
    results=[];last_request=None;model=configured_model();stopped=False
    for index,record in enumerate(records,1):
        if stop_event is not None and stop_event.is_set():break
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
            if not cached and request_budget is not None and request_budget.used>=request_budget.limit:
                result.update(status='not attempted',error='Shared new-AI-attempt limit reached; local XML retained')
                results.append(result);continue
            progress(f'{provider} {index}/{len(records)}: '+('reusing saved read: ' if cached else 'requesting AI read: ')+record.get('invoice',{}).get('number',Path(record['path']).name))
            if not cached:
                if last_request is not None:
                    delay=max(0,INTERVALS[provider]-(clock()-last_request))
                    if stop_event is not None:
                        if stop_event.wait(delay):break
                    else:wait(delay)
                if request_budget is not None and not request_budget.claim():break
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
        progress(f'{provider} result {index}/{len(records)}: '+result['status']+(' — '+result['error'] if result.get('error') else ''))
        if on_result is not None:on_result(record,result)
        if any(provider+' HTTP '+str(code) in result.get('error','') for code in (401,402,403,404,429)):
            stopped=True  # Keep applying cached successes without more API calls.
    if _save_report:save_report(Path(root)/'.invoice_app'/(provider.lower().replace(' ','_')+'_batch_results.json'),{'provider':provider,'results':results},progress)
    return results


def read_with_fallback(root,records,primary='Gemini',progress=lambda message:None,confirm_test=False,
                       batch_reader=read_batch,stop_event=None,on_result=None,request_budget=None):
    """Retain each success, then try the other configured API and finally Python."""
    if request_budget is None:request_budget=RequestBudget(len(records))
    from .tally_review_export import enable
    for client in {r['client'] for r in records}:enable(root,client)
    from .ai_providers import PROVIDERS,ACTIVE_PROVIDERS,KEY_VARIABLES,reader as get_reader
    if primary not in PROVIDERS:raise ValueError('Unknown invoice API provider')
    providers=([primary] if primary=='Gemma (local)' else [primary]+[p for p in ACTIVE_PROVIDERS if p!=primary]);remaining=list(records);results={}
    # Never replace a successful selected read just because another button was used.
    notified=set()
    def notify(record,result):
        token=(record['client'],record.get('digest'),record['path'])
        if result.get('status')=='extracted' and token not in notified:
            notified.add(token)
            if on_result is not None:on_result(record,result)
    for record in records:
        retained=find_retained(root,record,primary)
        if retained:
            token=(record['client'],record.get('digest'),record['path'])
            results[token]={**retained,'attempts':[]}
            notify(record,retained)
    remaining=[r for r in remaining if (r['client'],r.get('digest'),r['path']) not in results]
    for provider in providers:
        if not remaining or (stop_event is not None and stop_event.is_set()):break
        if request_budget is not None and request_budget.used>=request_budget.limit:
            progress('Shared AI request limit reached; no more API attempts. Using Python for remaining XML.')
            break
        reader=get_reader(provider)
        if provider!=primary and not os.environ.get(KEY_VARIABLES[provider],'').strip() and not any(reader.cache_path(root,r).exists() for r in remaining):continue
        progress(f'Reading {len(remaining)} remaining invoices with {provider}; {len(records)-len(remaining)} successful prior reads are retained')
        try:
            options={'provider':provider,'progress':progress,'confirm_test':confirm_test}
            if stop_event is not None:options['stop_event']=stop_event
            if on_result is not None:options['on_result']=notify
            if request_budget is not None:options['request_budget']=request_budget
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
            if result['status']=='extracted':
                results[token].update(status='extracted',provider=provider)
                notify(record,result)
        completed=sum(results[(r['client'],r.get('digest'),r['path'])].get('status')=='extracted' for r in records if (r['client'],r.get('digest'),r['path']) in results)
        progress(f'{provider} finished: {completed}/{len(records)} successful reads retained; only {len(records)-completed} unfinished sources may need fallback.')
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
    report={'results':final}
    if request_budget is not None:report.update(new_ai_attempts=request_budget.used,new_ai_attempt_limit=request_budget.limit)
    save_report(Path(root)/'.invoice_app'/'ai_batch_results.json',report,progress)
    return final


def run_batch_to_xml(root,records,primary,exporter,progress=lambda message:None,
                     confirm_test=False,stop_event=None,batch_runner=read_with_fallback,max_new_requests=None):
    """Checkpoint XML during reads and always export after Stop or AI failure."""
    from .tally_review_export import enable
    for client in {r['client'] for r in records}:enable(root,client)
    warnings=[];latest=[];successes=set()
    budget=RequestBudget(len(records) if max_new_requests is None else max_new_requests)
    def checkpoint(label):
        nonlocal latest
        try:
            latest=exporter()
            count=sum(bool(r.get('output_path')) and not r.get('errors') for r in latest)
            progress(f'{label}: {count} XML vouchers prepared; {len(successes)} successful AI reads retained.')
        except Exception as exc:
            warnings.append('XML checkpoint failed: '+str(exc))
            progress(warnings[-1])
    def completed(record,result):
        token=(record['client'],record.get('digest'),record['path'])
        successes.add(token)
        if len(successes)==1 or len(successes)%10==0:checkpoint('Saving AI progress')
    results=[]
    checkpoint('Preparing starting XML from saved AI/local results')
    try:
        results=batch_runner(root,records,primary=primary,progress=progress,
                             confirm_test=confirm_test,stop_event=stop_event,on_result=completed,request_budget=budget)
    except Exception as exc:
        warnings.append('AI batch stopped: '+str(exc))
        progress(warnings[-1]+'; preparing XML from retained AI/local results.')
    finally:
        checkpoint('Final XML')
    if not latest:raise ValueError('No XML could be prepared. '+ '; '.join(warnings))
    return results,latest,warnings

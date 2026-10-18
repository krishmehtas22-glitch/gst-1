"""Two in-flight requests for the chosen provider, retaining cloud start pacing."""
from concurrent.futures import ThreadPoolExecutor,wait as completed,FIRST_COMPLETED
from pathlib import Path
import threading


def read_parallel_batch(root,records,provider,progress,extract,wait,clock,confirm_test,stop_event,on_result,budget):
    from .gemini_batch import read_batch,RequestBudget,save_report
    from .ai_providers import reader,INTERVALS
    from .engine import read_json
    module=reader(provider);model=module.configured_model();extract=extract or module.extract_selected
    budget=budget if budget is not None else RequestBudget(len(records))
    locks={r['digest']:threading.Lock() for r in records};gate=threading.Lock();last=[None];access_failed=threading.Event()
    results=[None]*len(records);pending={};index=0
    def cached(record):
        path=module.cache_path(root,record)
        try:
            data=read_json(path) if path.exists() else {}
            return data.get('source_sha256')==record['digest'] and data.get('revision')==module.REVISION and data.get('model')==model
        except (ValueError,OSError):return False
    def stopped():return access_failed.is_set() or bool(stop_event and stop_event.is_set())
    def paced_extract(data_root,record):
        if not cached(record):
            with gate:
                if stopped():raise ValueError('No new request sent: processing stopped or provider access/quota failed.')
                delay=max(0,INTERVALS[provider]-(clock()-last[0])) if last[0] is not None else 0
                if delay:
                    if stop_event:
                        if stop_event.wait(delay):raise ValueError('No new request sent: processing stopped.')
                    else:wait(delay)
                if stopped():raise ValueError('No new request sent: provider access/quota failed or processing stopped.')
                last[0]=clock()
        return extract(data_root,record)
    def task(number):
        record=records[number]
        with locks[record['digest']]:
            if stopped() and not cached(record):return skipped(record)
            rows=read_batch(root,[record],progress,paced_extract,wait,clock,provider,
                confirm_test,stop_event,None,budget,_parallel=False,_save_report=False)
            result=rows[0] if rows else skipped(record)
            if any(provider+' HTTP '+str(code) in result.get('error','') for code in (401,402,403,404,429)):
                access_failed.set()
            return result
    def skipped(record):
        return {'client':record['client'],'path':record['path'],'digest':record.get('digest'),
                'status':'not attempted','error':'No new request sent: stopped, quota/access failure or request budget reached.'}
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='InvoiceAI') as pool:
        while index<len(records) or pending:
            while index<len(records) and len(pending)<2:
                if stopped() and not cached(records[index]):results[index]=skipped(records[index]);index+=1;continue
                pending[pool.submit(task,index)]=index;index+=1
            if not pending:break
            done,_=completed(pending,return_when=FIRST_COMPLETED)
            for future in done:
                number=pending.pop(future);results[number]=future.result()
                if on_result:on_result(records[number],results[number])
    save_report(Path(root)/'.invoice_app'/(provider.lower().replace(' ','_')+'_batch_results.json'),
        {'provider':provider,'parallel_requests':2,'results':results},progress)
    return results

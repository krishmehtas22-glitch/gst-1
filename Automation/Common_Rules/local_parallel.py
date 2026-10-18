"""Two local invoice requests at most; bounded scheduling, no cloud fallback."""
from concurrent.futures import ThreadPoolExecutor,wait as completed,FIRST_COMPLETED
from pathlib import Path
import threading


def read_local_batch(root,records,progress,extract,wait,clock,confirm_test,stop_event,on_result,budget):
    from .gemini_batch import read_batch,RequestBudget,save_report
    budget=budget if budget is not None else RequestBudget(len(records))
    results=[None]*len(records);locks={r['digest']:threading.Lock() for r in records}
    def task(index):
        record=records[index]
        with locks[record['digest']]:
            rows=read_batch(root,[record],progress,extract,wait,clock,'Gemma (local)',
                confirm_test,stop_event,None,budget,_parallel=False,_save_report=False)
        return rows[0] if rows else {'client':record['client'],'path':record['path'],
            'digest':record.get('digest'),'status':'not attempted','error':'Stopped or local request limit reached'}
    index=0;pending={}
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='GemmaInvoice') as pool:
        while index<len(records) or pending:
            while index<len(records) and len(pending)<2 and not (stop_event and stop_event.is_set()):
                pending[pool.submit(task,index)]=index;index+=1
            if not pending:break
            done,_=completed(pending,return_when=FIRST_COMPLETED)
            for future in done:
                number=pending.pop(future)
                results[number]=future.result()
                if on_result is not None:on_result(records[number],results[number])
    for index,row in enumerate(results):
        if row is None:
            record=records[index]
            results[index]={'client':record['client'],'path':record['path'],'digest':record.get('digest'),
                            'status':'not attempted','error':'Local processing stopped'}
    save_report(Path(root)/'.invoice_app'/'gemma_(local)_batch_results.json',
                {'provider':'Gemma (local)','parallel_requests':2,'results':results},progress)
    return results

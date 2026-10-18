"""Local transport, selected-source isolation and two-request scheduling."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import json,shutil,threading,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from Common_Rules import ollama_reader as local
from Common_Rules.desktop import inspect_sources
from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
from Common_Rules.gemini_batch import read_batch,read_with_fallback,RequestBudget


def records(tmp_path,count=5):
    folder=tmp_path/'Client';folder.mkdir()
    for file in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:count]:shutil.copy2(file,folder/file.name)
    return inspect_sources(tmp_path)


def answer(record):
    invoice=deepcopy(record['invoice'])
    result={k:invoice.get(k) for k in FIELDS}
    result['items']=[{k:item.get(k) for k in ITEM_FIELDS} for item in invoice['items']]
    return result


def test_local_extract_normalizes_and_reuses_cache_without_cloud_keys(tmp_path,monkeypatch):
    record=records(tmp_path,1)[0];calls=[]
    def transport(payload,key,model):
        assert key is None and model=='gemma3:4b'
        calls.append(payload);return answer(record)
    result=local.extract_selected(tmp_path,record,transport)
    assert result['api_provider']=='Gemma (local)' and result['number']==record['invoice']['number']
    assert result['items'] and result['extraction_warnings']
    assert local.extract_selected(tmp_path,record,lambda *a:pytest.fail('cached'))==result
    assert len(calls)==1


def test_http_is_fixed_loopback_no_proxy_no_auth_and_nonstreaming(monkeypatch):
    captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,size):return json.dumps({'done':True,'done_reason':'stop','message':{'content':'{"items": []}'}}).encode()
    class Opener:
        def open(self,request,timeout):
            captured.append(request)
            assert request.full_url=='http://127.0.0.1:11434/api/chat' and timeout==300
            assert request.get_header('Authorization') is None
            body=json.loads(request.data);assert body['stream'] is False and body['format']=='json'
            assert body['model']=='gemma3:4b' and body['options']['temperature']==0
            return Response()
    def opener(proxy,redirect):
        assert proxy.proxies=={} and isinstance(redirect,local.NoRedirect)
        return Opener()
    monkeypatch.setattr(local,'build_opener',opener)
    assert local.request_invoice({'messages':[{'role':'user','content':'invoice'}]},None,'gemma3:4b')=={'items':[]}
    assert len(captured)==1
    assert local.NoRedirect().redirect_request(None,None,None,None,None,None) is None


@pytest.mark.parametrize('response',[
    {'done':False,'message':{'content':'{}'}},
    {'done':True,'done_reason':'length','message':{'content':'{}'}},
    {'done':True,'message':{'content':'not json'}},
    {'done':True,'message':{'content':'[]'}},
])
def test_incomplete_model_results_are_rejected(monkeypatch,response):
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,size):return json.dumps(response).encode()
    monkeypatch.setattr(local,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**kw:Reply()))
    with pytest.raises(ValueError,match='incomplete or invalid'):local.request_invoice({'messages':[]},None,'gemma3:4b')


def test_local_failure_never_tries_a_cloud_provider(tmp_path):
    selected=records(tmp_path,1);providers=[]
    def batch(root,rows,**options):
        providers.append(options['provider'])
        return [{'status':'failed','error':'Ollama offline'}]
    result=read_with_fallback(tmp_path,selected,primary='Gemma (local)',batch_reader=batch)
    assert providers==['Gemma (local)'] and result[0]['status']=='local fallback'


def test_two_requests_overlap_with_ordered_results_and_serial_callbacks(tmp_path):
    selected=records(tmp_path);barrier=threading.Barrier(2);lock=threading.Lock()
    state={'active':0,'maximum':0,'calls':0};owner=threading.get_ident();callbacks=[]
    def extract(root,record):
        with lock:
            state['active']+=1;state['calls']+=1;sequence=state['calls']
            state['maximum']=max(state['maximum'],state['active'])
        try:
            if sequence<=2:barrier.wait(timeout=5)
            time.sleep(.01)
            return local.extract_selected(root,record,lambda *a:answer(record))
        finally:
            with lock:state['active']-=1
    budget=RequestBudget(len(selected))
    result=read_batch(tmp_path,selected,provider='Gemma (local)',extract=extract,request_budget=budget,
        on_result=lambda record,row:callbacks.append(threading.get_ident()))
    assert state['maximum']==2 and state['calls']==budget.used==5
    assert [row['digest'] for row in result]==[r['digest'] for r in selected]
    assert all(row['status']=='extracted' for row in result)
    assert callbacks==[owner]*5


def test_parallel_stop_does_not_launch_remaining_invoices(tmp_path):
    selected=records(tmp_path);stop=threading.Event();calls=[]
    def extract(root,record):
        calls.append(record['digest']);stop.set()
        return local.extract_selected(root,record,lambda *a:answer(record))
    result=read_batch(tmp_path,selected,provider='Gemma (local)',extract=extract,stop_event=stop)
    assert 1<=len(calls)<=2 and len(result)==5
    assert sum(r['status']=='extracted' for r in result)==len(calls)


def test_budget_is_atomic_across_workers():
    budget=RequestBudget(3)
    with ThreadPoolExecutor(max_workers=20) as pool:claims=list(pool.map(lambda _:budget.claim(),range(100)))
    assert sum(claims)==budget.used==3


def test_single_pdf_uses_selected_provider_without_expanding_selection():
    from BillSync_UI import BillSyncApp
    calls=[]
    app=SimpleNamespace(busy=False,records=[{'path':str(i)} for i in range(100)],
        table=SimpleNamespace(selection=lambda:list(map(str,range(100))),focus=lambda:'73'),
        ai_primary=SimpleNamespace(get=lambda:'Gemma (local)'),
        analyse_selected=lambda provider,records:calls.append((provider,records)))
    BillSyncApp.analyse_one_pdf(app)
    assert calls==[('Gemma (local)',[app.records[73]])]


def test_duplicate_source_is_serialized_and_reused(tmp_path):
    record=records(tmp_path,1)[0];calls=[];budget=RequestBudget(2)
    def extract(root,row):
        return local.extract_selected(root,row,lambda *a:calls.append(row['digest']) or answer(row))
    result=read_batch(tmp_path,[record,deepcopy(record)],provider='Gemma (local)',extract=extract,request_budget=budget)
    assert len(calls)==budget.used==1 and len(result)==2
    assert all(r['status']=='extracted' for r in result)


def test_parallel_budget_never_exceeded(tmp_path):
    selected=records(tmp_path);calls=[];budget=RequestBudget(1)
    def extract(root,row):
        return local.extract_selected(root,row,lambda *a:calls.append(row['digest']) or answer(row))
    result=read_batch(tmp_path,selected,provider='Gemma (local)',extract=extract,request_budget=budget)
    assert len(calls)==budget.used==1
    assert sum(r['status']=='extracted' for r in result)==1


def test_failed_read_preserves_previous_cache(tmp_path):
    record=records(tmp_path,1)[0];path=local.cache_path(tmp_path,record)
    path.parent.mkdir(parents=True);path.write_text('{"revision":"old","invoice":{"number":"KEEP"}}')
    previous=path.read_bytes()
    def fail(*args):raise ValueError('Ollama offline')
    with pytest.raises(ValueError,match='offline'):local.extract_selected(tmp_path,record,fail)
    assert path.read_bytes()==previous


def test_single_pdf_override_changes_only_the_provider_dispatch():
    import ast,inspect,textwrap
    from Invoice_Desktop import InvoiceApp
    from BillSync_UI import BillSyncApp
    before=inspect.getsource(InvoiceApp.analyse_one_pdf).replace("self.analyse_selected('Groq',records=","self.analyse_selected(self.ai_primary.get(),records=")
    assert ast.dump(ast.parse(textwrap.dedent(before)))==ast.dump(ast.parse(textwrap.dedent(inspect.getsource(BillSyncApp.analyse_one_pdf))))


def test_ai_first_local_selection_produces_xml_without_cloud_or_tally(tmp_path,monkeypatch):
    from Common_Rules.ai_first import run_ai_first
    from Common_Rules import groq_reader,tally_import
    import xml.etree.ElementTree as ET
    selected=records(tmp_path,2);record=selected[0];calls=[]
    monkeypatch.setattr(local,'request_invoice',lambda *args:calls.append(args) or answer(record))
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('No cloud calls'))
    monkeypatch.setattr(tally_import,'post_xml',lambda *a:pytest.fail('No Tally writes'))
    updated,report=run_ai_first(tmp_path,primary='Gemma (local)',selected_paths=[record['path']],max_new_requests=1,confirm_test=True)
    assert report['new_ai_attempts']==len(calls)==1 and report['tally_imports']==0
    assert local.cache_path(tmp_path,record).exists() and not local.cache_path(tmp_path,selected[1]).exists()
    assert report['sources'][0]['provider']=='Gemma (local)'
    folder=Path(updated[0]['output_path']);doc=ET.parse(folder/'Sales_Vouchers.xml')
    voucher=next(v for v in doc.findall('.//VOUCHER') if v.findtext('VOUCHERNUMBER')==record['invoice']['number'])
    assert voucher.findtext('REFERENCE')==record['invoice']['number']
    assert voucher.findtext('PARTYNAME')==record['invoice']['buyer_name']
    assert voucher.find('GUID') is not None


def test_cached_master_matching_uses_local_model_and_shared_budget(tmp_path,monkeypatch):
    from Common_Rules import tally_master_matching as matching
    record=records(tmp_path,1)[0];budget=RequestBudget(1);saved=[];calls=[]
    context={'data':{'ledgers':[{'name':'Buyer'}]}}
    monkeypatch.setattr(matching,'context',lambda *a:context)
    monkeypatch.setattr(matching,'loaded_choices',lambda *a:None)
    monkeypatch.setattr(matching,'shortlist',lambda *a:{'ledgers':[]})
    monkeypatch.setattr(matching,'save_choices',lambda *a:saved.append(a))
    assert local.match_cached(tmp_path,record,budget,transport=lambda payload,key,model:calls.append((key,model)) or {'_tally_matches':{}})
    assert calls==[(None,'gemma3:4b')] and budget.used==len(saved)==1
    assert not local.match_cached(tmp_path,record,budget,transport=lambda *a:pytest.fail('budget exhausted'))


def test_ai_first_routes_reviewed_invoice_master_matching_locally(tmp_path,monkeypatch):
    from Common_Rules import ai_first,desktop,tally_master_matching as matching
    record=records(tmp_path,1)[0];calls=[]
    monkeypatch.setattr(matching,'context',lambda *a:{'data':{}})
    monkeypatch.setattr(matching,'match_cached',lambda *a:pytest.fail('Never use cloud master matching in local mode'))
    monkeypatch.setattr(local,'match_cached',lambda *a:calls.append(a[1]['digest']) or True)
    monkeypatch.setattr(ai_first,'approved_result',lambda *a:{'status':'approved_review'})
    monkeypatch.setattr(desktop,'process_sources',lambda *a,**kw:[])
    _,report=ai_first.run_ai_first(tmp_path,primary='Gemma (local)',selected_paths=[record['path']])
    assert calls==[record['digest']] and report['approved_reviews_retained']==1

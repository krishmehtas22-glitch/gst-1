from copy import deepcopy
from pathlib import Path
import json
import queue
import shutil
import threading
import xml.etree.ElementTree as ET

import pytest

from Common_Rules import desktop, groq_reader, gemini_reader
from Common_Rules.ai_first import run_ai_first, configured_primary, save_primary
from Common_Rules.gemini_batch import read_batch, read_with_fallback
from Common_Rules.engine import read_json, write_json


def sources(root):
    folder=root/'Client';folder.mkdir()
    for p in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:3]:
        shutil.copyfile(p,folder/p.name)
    return desktop.inspect_sources(root)


def runner(events, monkeypatch, quota=False):
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    for name in ('GITHUB_MODELS_TOKEN','GEMINI_API_KEY','OPENROUTER_API_KEY'):
        monkeypatch.delenv(name,raising=False)
    if quota:monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    def batch(root,records,provider,**kwargs):
        reader=groq_reader if provider=='Groq' else gemini_reader
        def extract(root,row):
            def transport(*args):
                events.append(('ai',provider,row['digest']))
                if quota and provider=='Groq':raise ValueError('Groq HTTP 429: quota')
                original=row['invoice']
                return {**{k:original.get(k) for k in reader.FIELDS},'items':[
                    {k:item.get(k) for k in reader.ITEM_FIELDS} for item in original['items']]}
            return reader.extract_selected(root,row,transport)
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    return lambda *a,**kw:read_with_fallback(*a,batch_reader=batch,**kw)


def test_ai_reads_every_new_invoice_before_any_xml_conversion(tmp_path,monkeypatch):
    sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    original=desktop.process_sources
    def convert(*args,**kwargs):events.append(('xml',));return original(*args,**kwargs)
    monkeypatch.setattr(desktop,'process_sources',convert)
    updated,report=run_ai_first(tmp_path,batch_runner=batch)
    assert [e[0] for e in events]==['ai','ai','ai','xml']
    assert report['ai_read_invoices']==3 and report['new_ai_attempts']==3
    assert report['local_or_review_fallbacks']==0 and report['xml_prepared']==3
    assert all(not r['errors'] for r in updated)
    assert not list((tmp_path/'.invoice_app/document_settings').glob('*.json'))
    folder=Path(updated[0]['output_path'])
    assert all((folder/name).exists() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml'))
    assert len(ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER'))==3
    saved=read_json(tmp_path/'.invoice_app/AI_First_Last_Run.json')
    assert saved['mode']=='desktop_ai_first' and saved['tally_imports']==0


def test_saved_ai_and_human_review_are_terminal_on_later_scans(tmp_path,monkeypatch):
    sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    rows,first=run_ai_first(tmp_path,batch_runner=batch)
    row=rows[0];desktop.save_review(tmp_path,row,deepcopy(row['invoice']))
    approval=tmp_path/'.invoice_app/reviews'/(row['digest']+'.json');original=approval.read_bytes()
    def no_new(*args):pytest.fail('Saved reads must not trigger API calls')
    monkeypatch.setattr(groq_reader,'request_invoice',no_new)
    rows,again=run_ai_first(tmp_path)
    assert again['new_ai_attempts']==0 and again['ai_read_invoices']==2
    assert again['approved_reviews_retained']==1 and again['xml_prepared']==3
    assert approval.read_bytes()==original and len(events)==3


def test_new_file_is_the_only_fresh_read_in_a_later_folder_scan(tmp_path,monkeypatch):
    sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    run_ai_first(tmp_path,batch_runner=batch)
    extra=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[3]
    shutil.copyfile(extra,tmp_path/'Client'/extra.name)
    _,report=run_ai_first(tmp_path,batch_runner=batch)
    assert len(events)==4 and report['new_ai_attempts']==1
    assert report['ai_read_invoices']==4 and report['xml_prepared']==4


def test_quota_uses_configured_fallback_with_one_shared_budget(tmp_path,monkeypatch):
    sources(tmp_path);events=[];batch=runner(events,monkeypatch,quota=True)
    updated,report=run_ai_first(tmp_path,batch_runner=batch)
    assert report['new_ai_attempts']==report['new_ai_attempt_limit']==3
    assert [e[1] for e in events]==['Groq','Gemini','Gemini']
    assert report['ai_read_invoices']==2 and report['local_or_review_fallbacks']==1
    assert report['xml_prepared']==3
    manifest=read_json(Path(updated[0]['output_path'])/'Batch_Report.json')
    assert any('AI-first extraction was not completed' in ' '.join(r['warnings']) for r in manifest['invoices'])


def test_stop_still_prepares_python_review_xml_without_claiming_ai_read(tmp_path,monkeypatch):
    sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    stop=threading.Event();stop.set()
    _,report=run_ai_first(tmp_path,batch_runner=batch,stop_event=stop)
    assert not events and report['ai_stopped']
    assert report['ai_read_invoices']==0 and report['local_or_review_fallbacks']==3
    assert report['xml_prepared']==3 and report['new_ai_attempts']==0


def test_worker_failure_preserves_successful_cache_without_retry(tmp_path,monkeypatch):
    records=sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    def failing(root,records,**kwargs):
        batch(root,records[:1],**kwargs)
        raise RuntimeError('private failure details')
    _,report=run_ai_first(tmp_path,batch_runner=failing)
    assert len(events)==1 and report['ai_read_invoices']==1 and report['xml_prepared']==3
    assert 'private failure details' not in json.dumps(report)


def test_selected_read_uses_ai_before_xml_and_confirms_only_the_selected_test_pdf(tmp_path,monkeypatch):
    from Common_Rules.ai_first import token
    records=sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    original=desktop.process_sources
    def convert(*a,**kw):events.append(('xml',));return original(*a,**kw)
    monkeypatch.setattr(desktop,'process_sources',convert)
    _,report=run_ai_first(tmp_path,batch_runner=batch,selected_source=token(records[0]),confirm_test=True)
    assert [e[0] for e in events]==['ai','xml']
    assert events[0][2]==records[0]['digest'] and report['new_ai_attempts']==1
    assert report['local_or_review_fallbacks']==2 and report['xml_prepared']==3
    assert len(list((tmp_path/'.invoice_app/document_settings').glob('*.json')))==1


def test_invalid_review_is_not_overwritten_or_uploaded_to_ai(tmp_path):
    records=sources(tmp_path)
    for r in records:
        write_json(tmp_path/'.invoice_app/reviews'/(r['digest']+'.json'),
                   {'source_sha256':'wrong','approved':True,'invoice':r['invoice']})
    _,report=run_ai_first(tmp_path,batch_runner=lambda *a,**kw:pytest.fail('Review requires attention'))
    assert report['new_ai_attempts']==0 and report['local_or_review_fallbacks']==3
    assert all(r['status']=='saved_review_needs_attention' for r in report['sources'])


def test_primary_provider_choice_is_persisted_and_invalid_values_are_rejected(tmp_path):
    assert configured_primary(tmp_path)=='Groq'
    save_primary(tmp_path,'Gemini')
    assert configured_primary(tmp_path)=='Gemini'
    with pytest.raises(ValueError):save_primary(tmp_path,'Cerebras')
    assert configured_primary(tmp_path)=='Gemini'


def test_report_failure_does_not_discard_completed_xml(tmp_path,monkeypatch):
    from Common_Rules import ai_first
    sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    monkeypatch.setattr(ai_first,'write_json',lambda *a:(_ for _ in ()).throw(OSError('report unavailable')))
    updated,report=run_ai_first(tmp_path,batch_runner=batch)
    assert len(updated)==3 and report['xml_prepared']==3 and report['warnings']


@pytest.mark.parametrize('new_pdf',[False,True])
def test_watch_acknowledges_own_metadata_but_preserves_new_pdf_trigger(monkeypatch,new_pdf):
    import Invoice_Desktop as gui
    class Value:
        def __init__(self,value):self.value=value
        def get(self):return self.value
    class Table:
        def get_children(self):return []
        def delete(self,*args):pass
    class Widget:
        def config(self,**kwargs):pass
        def after(self,*args):pass
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.events=queue.Queue();app.events.put(('ok',[]));app.selected=lambda:None
    app.status=Widget();app.table=Table();app.window=Widget();app.closing=False
    app.auto=Value(False);app.refresh_clients=lambda:None
    previous=(True,True,False,'All clients','old source','Groq','old metadata')
    latest=(True,True,False,'All clients','new source' if new_pdf else 'old source','Groq','new metadata')
    app.last=previous;app.observed=previous;app.ai_scan_snapshot=previous
    app.watch_signature=lambda:latest
    app.tick()
    assert app.ai_scan_snapshot is None
    starts=[];app.start=lambda:starts.append(1);app.auto.value=True
    app.tick();app.tick()
    assert len(starts)==(1 if new_pdf else 0)


def test_desktop_scan_dispatches_ai_first_flow(tmp_path,monkeypatch):
    import Invoice_Desktop as gui
    from Common_Rules import ai_first
    class Value:
        def __init__(self,value):self.value=value
        def get(self):return self.value
    class Widget:
        def config(self,**kwargs):pass
    class ImmediateThread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.busy=False;app.root=tmp_path;app.status=Widget();app.events=queue.Queue()
    app.demo=Value(True);app.auto_units=Value(True);app.summary_accounting=Value(False)
    app.client_scope=Value('Folder: Client');app.ai_primary=Value('Gemini');app.watch_signature=lambda:()
    calls=[]
    def run(root,demo,clients,units,summary,**kwargs):
        calls.append((root,clients,kwargs['primary'],kwargs['stop_event']))
        return [],dict(ai_read_invoices=0,approved_reviews_retained=0,local_or_review_fallbacks=0,xml_prepared=0)
    monkeypatch.setattr(ai_first,'run_ai_first',run);monkeypatch.setattr(gui.threading,'Thread',ImmediateThread)
    app.start()
    assert calls[0][1]==['Client'] and calls[0][2]=='Gemini'
    assert app.events.get()[0]=='ok'

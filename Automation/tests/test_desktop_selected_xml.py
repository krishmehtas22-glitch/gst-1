from copy import deepcopy
from pathlib import Path
import json
import queue
import shutil
import threading
import xml.etree.ElementTree as ET

import pytest

from Common_Rules import groq_reader
from Common_Rules.api_selection import activate
from Common_Rules.desktop import inspect_sources, process_sources, save_review
from Common_Rules.desktop_ai import selected_to_xml
from Common_Rules.engine import write_json
from Common_Rules.printed_unit_evidence import verify_printed_units
from Common_Rules.tally_review_export import enabled


def sources(root, cached=True):
    folder=root/'Client';folder.mkdir()
    fixtures=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:3]
    for p in fixtures:shutil.copyfile(p,folder/p.name)
    records=inspect_sources(root)
    if cached:
        for record in records:
            invoice=deepcopy(record['invoice']);invoice['dummy_document']=False
            write_json(groq_reader.cache_path(root,record),dict(revision=groq_reader.REVISION,
                model=groq_reader.configured_model(),source_sha256=record['digest'],invoice=invoice))
            activate(root,record,'Groq')
    return records


def test_selected_ai_prepares_complete_client_xml_from_saved_reads(tmp_path,monkeypatch):
    sources(tmp_path)
    before=process_sources(tmp_path)
    assert len(before)==3 and all(r['errors'] and not r.get('output_path') for r in before)
    approval=deepcopy(before[1]['invoice']);save_review(tmp_path,before[1],approval)
    approved=tmp_path/'.invoice_app/reviews'/(before[1]['digest']+'.json');original=approved.read_bytes()
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('Saved reads must be terminal'))
    results,updated,warnings=selected_to_xml(tmp_path,before[0],'Groq',True,True,False)
    assert enabled(tmp_path,'Client') and len(updated)==3 and not warnings
    assert all(not r['errors'] and r.get('output_path') for r in updated)
    folder=Path(updated[0]['output_path'])
    assert all((folder/name).exists() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml'))
    assert len(ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER'))==3
    assert approved.read_bytes()==original
    assert not list((tmp_path/'.invoice_app/companies').rglob('*'))
    report=json.loads((tmp_path/'.invoice_app/ai_batch_results.json').read_text())
    assert report['new_ai_attempts']==0 and report['new_ai_attempt_limit']==1
    assert len(results)==1 and results[0]['cached']


@pytest.mark.parametrize('stopped',[False,True])
def test_selected_failure_or_stop_still_exports_entire_client_without_extra_requests(tmp_path,monkeypatch,stopped):
    records=sources(tmp_path,cached=False);calls=[]
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    def quota(*args):calls.append(1);raise ValueError('Groq HTTP 429: quota')
    monkeypatch.setattr(groq_reader,'request_invoice',quota)
    stop=threading.Event()
    if stopped:stop.set()
    results,updated,warnings=selected_to_xml(tmp_path,records[0],'Groq',True,True,False,stop_event=stop)
    assert len(calls)==(0 if stopped else 1)
    assert len(updated)==3 and all(r.get('output_path') for r in updated)
    assert len(ET.parse(Path(updated[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==3
    assert all(r['client']=='Client' for r in updated)


def test_selected_client_does_not_process_or_change_other_client_policy(tmp_path,monkeypatch):
    records=sources(tmp_path);other=tmp_path/'Other';other.mkdir()
    shutil.copyfile(records[0]['path'],other/'invoice.pdf')
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('No request expected'))
    _,updated,_=selected_to_xml(tmp_path,records[0],'Groq',True,True,False)
    assert {r['client'] for r in updated}=={'Client'} and not enabled(tmp_path,'Other')


def test_desktop_selected_button_dispatches_complete_xml_workflow(tmp_path,monkeypatch):
    import Invoice_Desktop as gui
    from Common_Rules import desktop_ai
    record=sources(tmp_path)[0]
    class Value:
        def __init__(self,value):self.value=value
        def get(self):return self.value
        def set(self,value):self.value=value
    class Status:
        def config(self,**kwargs):pass
    class ImmediateThread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.selected=lambda:record;app.busy=False;app.root=tmp_path
    app.demo=Value(True);app.auto_units=Value(True);app.summary_accounting=Value(False)
    app.auto=Value(True);app.status=Status();app.events=queue.Queue()
    prompts=[];calls=[]
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda title,body:prompts.append(body) or True)
    monkeypatch.setattr(gui.threading,'Thread',ImmediateThread)
    def dispatch(root,row,provider,demo,units,summary,**kwargs):
        calls.append((row,provider,kwargs['stop_event']))
        return [],[{**row,'output_path':'review-output','errors':[]}],[]
    monkeypatch.setattr(desktop_ai,'selected_to_xml',dispatch)
    app.read_gemini('Groq')
    assert calls[0][0] is record and calls[0][1]=='Groq'
    assert 'At most one new AI attempt' in prompts[0] and 'fictional test data' in prompts[0]
    assert app.events.get()[0]=='ok'


def test_matching_printed_unit_updates_only_provenance():
    from test_goods_layout import source
    from Common_Rules.extraction import parse_text
    local=parse_text(source());invoice=deepcopy(local)
    invoice['items'][0].update(unit_origin='ai_assumed',unit_basis='inferred',unit_auto=True)
    record={'invoice':invoice};before=deepcopy(invoice)
    verify_printed_units(record,local)
    item=record['invoice']['items'][0]
    assert item['unit_origin']=='printed' and item['unit_auto'] is False
    assert all(item[k]==before['items'][0][k] for k in ('quantity','unit','rate','value','name','hsn'))


@pytest.mark.parametrize('change',['quantity','rate','unit','name','partial','manual'])
def test_ambiguous_or_manual_units_are_never_relabelled(change):
    from test_goods_layout import source
    from Common_Rules.extraction import parse_text
    local=parse_text(source());invoice=deepcopy(local)
    invoice['items'][0].update(unit_origin='ai_assumed',unit_basis='inferred',unit_auto=True)
    if change=='manual':invoice['items'][0]['unit_origin']='manual'
    elif change=='partial':local['items']=[]
    else:invoice['items'][0][change]='DIFFERENT'
    before=deepcopy(invoice)
    verify_printed_units({'invoice':invoice},local)
    assert invoice==before

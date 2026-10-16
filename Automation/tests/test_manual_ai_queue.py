from pathlib import Path
from copy import deepcopy
import queue

import pytest

from Common_Rules.invoice_queue import list_sources


def test_listing_one_hundred_pdfs_reads_no_contents_and_creates_no_output(tmp_path,monkeypatch):
    from Common_Rules import desktop, ai_first, extraction, tally_review_export
    folder=tmp_path/'Client';folder.mkdir()
    for i in range(100):(folder/f'invoice-{i:03}.pdf').write_bytes(b'not parsed')
    fail=lambda *a,**kw:pytest.fail('Listing must not analyse, call AI or create XML')
    monkeypatch.setattr(desktop,'inspect_sources',fail)
    monkeypatch.setattr(ai_first,'run_ai_first',fail)
    monkeypatch.setattr(extraction,'text_from_pdf',fail)
    monkeypatch.setattr(tally_review_export,'export_all',fail)
    monkeypatch.setattr(Path,'read_bytes',fail)
    records=list_sources(tmp_path)
    assert len(records)==100 and all(r['listing_only'] and not r.get('digest') for r in records)
    assert not (tmp_path/'.invoice_app').exists()
    (folder/'new.pdf').write_bytes(b'new file')
    assert len(list_sources(tmp_path,previous=records))==101


def test_unchanged_analysis_display_is_retained_but_changed_file_is_queued(tmp_path):
    folder=tmp_path/'Client';folder.mkdir();path=folder/'invoice.pdf';path.write_bytes(b'PDF')
    previous=list_sources(tmp_path)
    previous[0].update(listing_only=False,digest='saved',output_path='existing-output')
    previous[0]['invoice']={'number':'KNOWN','items':[],'total':'123'}
    assert list_sources(tmp_path,previous=previous)[0]['invoice']['total']=='123'
    path.write_bytes(b'changed PDF')
    new=list_sources(tmp_path,previous=previous)[0]
    assert new['listing_only'] and not new.get('digest') and not new.get('output_path')


class Value:
    def __init__(self,value):self.value=value
    def get(self):return self.value
    def set(self,value):self.value=value


def controller(tmp_path,count):
    import Invoice_Desktop as gui
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.records=[dict(path=str(tmp_path/'Client'/f'{i}.pdf'),client='Client',listing_only=True,
                      invoice={},errors=[]) for i in range(count)]
    class Table:
        def selection(self):return [str(i) for i in range(count)]
    class Status:
        def config(self,**kw):pass
    app.table=Table();app.root=tmp_path;app.busy=False;app.events=queue.Queue();app.status=Status()
    app.demo=Value(False);app.auto_units=Value(True);app.summary_accounting=Value(False)
    app.ai_primary=Value('Groq');app.auto=Value(True)
    return app


@pytest.mark.parametrize('count',[1,100])
@pytest.mark.parametrize('approved',[False,True])
def test_ai_requires_confirmation_for_the_exact_selected_scope(tmp_path,monkeypatch,count,approved):
    import Invoice_Desktop as gui
    from Common_Rules import desktop_ai
    app=controller(tmp_path,count);calls=[];prompts=[]
    class ImmediateThread:
        def __init__(self,target,**kw):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(gui.threading,'Thread',ImmediateThread)
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda title,text:prompts.append(text) or approved)
    def run(root,records,provider,*args,**kw):
        calls.append((records,provider))
        return [],dict(ai_read_invoices=0,approved_reviews_retained=0,local_or_review_fallbacks=0,xml_prepared=0)
    monkeypatch.setattr(desktop_ai,'analyse_paths',run)
    app.analyse_selected()
    assert f'exactly {count} selected PDFs' in prompts[0]
    assert len(calls)==int(approved)
    if approved:assert len(calls[0][0])==count and calls[0][1]=='Groq' and app.auto.get()
    else:assert not app.busy and app.events.empty()


def test_selected_paths_are_frozen_and_cap_requests_before_new_file_can_join(tmp_path,monkeypatch):
    from test_ai_first_flow import sources, runner
    from Common_Rules.ai_first import run_ai_first
    records=sources(tmp_path);events=[];batch=runner(events,monkeypatch)
    approved=[records[0]['source_path'],records[1]['source_path']]
    _,report=run_ai_first(tmp_path,batch_runner=batch,selected_paths=approved,max_new_requests=2)
    assert len(events)==2 and report['new_ai_attempts']==report['new_ai_attempt_limit']==2
    assert {e[2] for e in events}=={r['digest'] for r in records[:2]}
    assert next(r for r in report['sources'] if r['digest']==records[2]['digest'])['status']=='not_selected_for_new_ai'

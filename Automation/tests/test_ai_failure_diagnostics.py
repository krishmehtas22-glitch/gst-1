"""Groq failure -> visible review reason -> human correction, without live AI."""
from copy import deepcopy
from pathlib import Path
import json,hashlib,runpy,zipfile
import xml.etree.ElementTree as ET
import pytest
from test_ai_first_flow import sources,runner
from Common_Rules.ai_first import run_ai_first,summary_text
from Common_Rules.workflow_validation import enable,MARKER,cannot_override
from Common_Rules.ai_failure_diagnostics import failure_details,recovery_instruction
from Common_Rules.desktop import save_review,process_sources


@pytest.mark.parametrize('error',[
    'Groq HTTP 429: Request/token quota reached; new requests stopped',
    'Groq HTTP 401: API authentication rejected; check GROQ_API_KEY privately',
    'Groq connection failed or timed out; previous extraction is unchanged',
    'Set GROQ_API_KEY privately in Windows User environment variables, then reopen the app.',
])
def test_provider_failure_survives_summary_record_and_import_review(tmp_path,monkeypatch,error):
    rows=sources(tmp_path);enable(tmp_path)
    from Common_Rules import groq_reader
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:(_ for _ in ()).throw(ValueError(error)))
    from Common_Rules.gemini_batch import read_with_fallback,read_batch
    def batch(root,records,**kwargs):
        return read_with_fallback(root,records,batch_reader=lambda root,rows,**options:read_batch(root,rows,wait=lambda _:None,**options),**kwargs)
    updated,report=run_ai_first(tmp_path,batch_runner=batch,selected_paths=[rows[0]['path']],max_new_requests=1)
    failed=next(r for r in updated if r['digest']==rows[0]['digest'])
    assert error in failed['ai_failure_reason']
    assert error in summary_text(report)
    saved=json.loads((tmp_path/'.invoice_app/AI_First_Last_Run.json').read_text())
    assert error in saved['extraction_failures'][0]['reason']
    xml=ET.parse(Path(failed['output_path'])/'Sales_Vouchers.xml')
    entries=json.loads(xml.getroot().get(MARKER))['entries']
    problem=next(p for e in entries if e['read_sha256']==failed['digest'] for p in e['issues'] if p['field']=='AI extraction')
    assert error in problem['reason'] and cannot_override(problem)
    assert 'private-test-key' not in json.dumps(saved)


def test_manual_correction_clears_only_that_invoice_and_preserves_other_failures(tmp_path,monkeypatch):
    rows=sources(tmp_path);enable(tmp_path)
    def failed(root,records,**kwargs):
        return [{**{k:r[k] for k in ('client','path','digest')},'status':'local fallback','provider':'Python',
            'attempts':[{'provider':'Groq','status':'failed','error':'Groq HTTP 429: quota'}]} for r in records]
    updated,_=run_ai_first(tmp_path,batch_runner=failed)
    from Common_Rules import groq_reader
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('Manual review must not call AI'))
    reviewed=updated[0];save_review(tmp_path,reviewed,deepcopy(reviewed['invoice']))
    changed=process_sources(tmp_path)
    corrected=next(r for r in changed if r['digest']==reviewed['digest'])
    assert corrected['ai_first_status']=='approved_review'
    assert not any(p['field']=='AI extraction' for p in corrected['workflow_issues'])
    for row in changed:
        if row['digest']==reviewed['digest']:continue
        problem=next(p for p in row['workflow_issues'] if p['field']=='AI extraction')
        assert cannot_override(problem) and 'Groq HTTP 429' in problem['reason']


def test_cache_success_clears_failure_without_new_request(tmp_path,monkeypatch):
    sources(tmp_path);enable(tmp_path);events=[]
    rows,_=run_ai_first(tmp_path,batch_runner=runner(events,monkeypatch))
    monkeypatch.delenv('GROQ_API_KEY')
    current=process_sources(tmp_path)
    assert all(r['ai_first_status']=='extracted' for r in current)
    assert not any(p['field']=='AI extraction' for r in current for p in r['workflow_issues'])


def test_instructions_distinguish_provider_failure_from_stale_source():
    assert 'Analyse' in recovery_instruction('AI extraction')
    assert 'Save changes to XML' in recovery_instruction('AI extraction')
    assert 'Restore the exact source' in recovery_instruction('Source invoice')
    assert failure_details({'status':'extracted'},'Groq')=={}
    assert 'stopped' in failure_details({'status':'local fallback'},'Groq',True)['ai_failure_reason']


def test_failure_diagnostic_release_and_installer_match():
    root=Path(__file__).parents[2]
    change=json.loads((root/'Automation/AI_FAILURE_DIAGNOSTICS_CHANGE.json').read_text())
    package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(root/change['backup']) as backup:
        for name,entry in change['files'].items():
            assert hashlib.sha256(backup.read(name)).hexdigest()==entry['baseline_sha256']
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==entry['authorized_sha256']
    for name in [*change['files'],*change['new_files']]:
        if name.startswith('Automation/') and name.endswith('.py'):
            assert package['FILES'][name.removeprefix('Automation/')].encode()==(root/name).read_bytes()


def test_warning_only_import_consent_and_blocked_extraction_in_real_dialog(monkeypatch):
    import os
    if not os.environ.get('DISPLAY') and os.name!='nt':pytest.skip('Requires a desktop display')
    import tkinter as tk
    from tkinter import ttk
    from Common_Rules.workflow_validation import WorkflowReviewRequired,issue
    from Workflow_Review_Dialog import open_workflow_review
    from BillSync_Theme import install_theme,descendants
    window=tk.Tk();window.geometry('1200x750');install_theme(window);window.update()
    try:
        for field,blocked in [('Buyer GSTIN',False),('Buyer state',False),('AI extraction',True)]:
            results=[]
            top=open_workflow_review(window,WorkflowReviewRequired([issue('INV-1',field,'bad','','Review',True)],'token','Test'),results.append)
            window.update()
            consent=next(w for w in descendants(top) if isinstance(w,ttk.Checkbutton))
            submit=next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Import to Tally anyway')
            assert consent.instate(['disabled'])==blocked
            assert submit.instate(['disabled'])
            consent.invoke();window.update()
            assert submit.instate(['disabled'])==blocked
            if not blocked:
                submit.invoke();window.update();assert results==[True]
            else:top.destroy()
    finally:window.destroy()


@pytest.mark.parametrize('mode',['import','cancel','edit','partial'])
def test_real_import_worker_review_roundtrip_with_mock_tally(tmp_path,monkeypatch,mode):
    import os,time
    if not os.environ.get('DISPLAY') and os.name!='nt':pytest.skip('Requires a desktop display')
    import tkinter as tk
    from BillSync_UI import BillSyncApp
    from test_ai_workflow_validation import exercise_import_review_roundtrip
    window=tk.Tk();window.geometry('1200x750');app=BillSyncApp(window,data_root=tmp_path)
    try:
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:window.update();time.sleep(.01)
        app.table.insert('','end',iid='0',values=('Client','INV','Seller','100','','Review','',''))
        app.table.selection_set('0');app.table.focus('0')
        exercise_import_review_roundtrip(window,app,monkeypatch,mode)
    finally:
        app.closing=True;window.destroy()

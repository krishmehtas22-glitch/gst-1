"""Provider scheduling must preserve completed results and working voucher data."""
import json
import threading
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from Common_Rules import github_models_reader as github
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.gemini_batch import read_batch,read_with_fallback


def sources(root):
    folder=root/'Client';folder.mkdir()
    for pdf in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:12]:
        shutil.copy2(pdf,folder/pdf.name)
    return inspect_sources(root)


def extract(root,row):
    def response(*args):
        invoice=row['invoice']
        return {**{k:invoice.get(k) for k in github.FIELDS},'items':[
            {k:item.get(k) for k in github.ITEM_FIELDS} for item in invoice['items']]}
    return github.extract_selected(root,row,response)


def setup(monkeypatch):
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','private-test-key')
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')


def test_twelve_successes_no_other_provider_and_rerun_preserves_output(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        assert provider=='GitHub Models'
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    results=read_with_fallback(tmp_path,rows,primary='GitHub Models',batch_reader=batch,confirm_test=True)
    assert len(results)==12 and all(r['status']=='extracted' for r in results)
    assert calls==['GitHub Models']
    first=process_sources(tmp_path)
    original=ET.parse(Path(first[0]['output_path'])/'Sales_Vouchers.xml')
    first_xml=ET.tostring(original.getroot())
    cached=[github.cache_path(tmp_path,r).read_bytes() for r in rows]
    # Selecting a different batch provider must reuse successes, not overwrite them.
    again=read_with_fallback(tmp_path,rows,primary='Groq',batch_reader=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No API needed')))
    assert all(r['provider']=='GitHub Models' for r in again)
    assert cached==[github.cache_path(tmp_path,r).read_bytes() for r in rows]
    second=process_sources(tmp_path)
    assert first_xml==ET.tostring(ET.parse(Path(second[0]['output_path'])/'Sales_Vouchers.xml').getroot())


def test_late_batch_failure_keeps_all_cached_successes(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        assert provider=='GitHub Models'
        for row in records:extract(root,row)
        raise OSError('Batch report save failed after twelve successful reads')
    results=read_with_fallback(tmp_path,rows,primary='GitHub Models',batch_reader=batch,confirm_test=True)
    assert calls==['GitHub Models']
    assert all(r['status']=='extracted' and r['provider']=='GitHub Models' for r in results)


def test_stop_after_one_retains_success_no_fallback_all_xml(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);stop=threading.Event();calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        def one(root,row):
            result=extract(root,row);stop.set();return result
        return read_batch(root,records,provider=provider,extract=one,wait=lambda _:None,**kwargs)
    result=read_with_fallback(tmp_path,rows,primary='GitHub Models',batch_reader=batch,confirm_test=True,stop_event=stop)
    assert calls==['GitHub Models']
    assert result[0]['status']=='extracted'
    assert all(r['ai_stopped'] and r['provider']=='Python' for r in result[1:])
    updated=process_sources(tmp_path)
    assert len(updated)==12
    assert len(ET.parse(Path(updated[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==12


def test_stop_during_pacing_prevents_next_request(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path)[:2];calls=[]
    class StopOnWait:
        def is_set(self):return False
        def wait(self,seconds):return True
    def one(root,row):calls.append(row['digest']);return extract(root,row)
    result=read_batch(tmp_path,rows,provider='GitHub Models',extract=one,stop_event=StopOnWait())
    assert len(result)==len(calls)==1


def test_confirmation_failure_does_not_send_success_to_other_provider(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path)[:1]
    from Common_Rules import gemini_batch
    def fail(*args):raise OSError('Cannot save test confirmation')
    monkeypatch.setattr(gemini_batch,'confirm_test_document',fail)
    calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    result=read_with_fallback(tmp_path,rows,primary='GitHub Models',batch_reader=batch,confirm_test=True)
    assert calls==['GitHub Models'] and result[0]['status']=='extracted'
    assert result[0]['confirmation_note']


def test_stop_button_sets_event_keeps_busy_until_worker_finishes():
    import Invoice_Desktop
    app=Invoice_Desktop.InvoiceApp.__new__(Invoice_Desktop.InvoiceApp)
    app.ai_stop=threading.Event();app.busy=True
    class Status:
        def config(self,**kwargs):self.text=kwargs['text']
    app.status=Status();app.stop_ai()
    assert app.ai_stop.is_set() and app.busy
    assert 'completed reads are retained' in app.status.text
    app.ai_stop=None;app.stop_ai()  # idle button is harmless


def test_partial_late_failure_fallback_only_receives_unfinished_sources(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);calls=[]
    from Common_Rules import groq_reader
    def batch(root,records,provider,**kwargs):
        calls.append((provider,[r['digest'] for r in records]))
        if provider=='GitHub Models':
            for row in records[:5]:extract(root,row)
            raise OSError('Report failure after five saved extractions')
        assert provider=='Groq'
        def groq_extract(root,row):
            invoice=row['invoice']
            data={**{k:invoice.get(k) for k in github.FIELDS},'items':[
                {k:item.get(k) for k in github.ITEM_FIELDS} for item in invoice['items']]}
            return groq_reader.extract_selected(root,row,lambda *args:deepcopy(data))
        return read_batch(root,records,provider=provider,extract=groq_extract,wait=lambda _:None,**kwargs)
    result=read_with_fallback(tmp_path,rows,primary='GitHub Models',batch_reader=batch)
    assert len(calls)==2
    assert calls[1]==('Groq',[r['digest'] for r in rows[5:]])
    assert [r['provider'] for r in result]==['GitHub Models']*5+['Groq']*7

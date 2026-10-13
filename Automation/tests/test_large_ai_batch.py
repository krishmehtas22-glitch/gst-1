"""Large batches cannot multiply API attempts or lose XML after cancellation."""
import json
import threading
from pathlib import Path
from pypdf import PdfReader,PdfWriter
import xml.etree.ElementTree as ET
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.gemini_batch import read_batch,read_with_fallback,run_batch_to_xml
from Common_Rules import groq_reader,github_models_reader


def sources(root,count=50):
    folder=root/'Client';folder.mkdir()
    fixtures=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))
    for i in range(count):
        writer=PdfWriter();writer.add_page(PdfReader(fixtures[i%len(fixtures)]).pages[0])
        writer.add_metadata({'/BatchTest':str(i)})
        with (folder/f'invoice-{i:03}.pdf').open('wb') as output:writer.write(output)
    return inspect_sources(root)


def setup(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','private-test-key')
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')


def reply(row,reader):
    original=row['invoice']
    return {**{k:original.get(k) for k in reader.FIELDS},'items':[
        {k:item.get(k) for k in reader.ITEM_FIELDS} for item in original['items']]}


def xml_count(updated):
    run=Path(updated[0]['output_path'])
    return sum(len(ET.parse(p).findall('.//VOUCHER')) for p in run.rglob('Sales_Vouchers.xml'))


def test_fifty_successes_groq_only_with_incremental_xml(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);providers=[];http=[];checkpoints=[]
    def batch(root,records,provider,**kwargs):
        providers.append(provider);assert provider=='Groq'
        def extract(root,row):
            def transport(*args):http.append(row['digest']);return reply(row,groq_reader)
            return groq_reader.extract_selected(root,row,transport)
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    def runner(*args,**kwargs):return read_with_fallback(*args,batch_reader=batch,**kwargs)
    def export():
        updated=process_sources(tmp_path);checkpoints.append(xml_count(updated));return updated
    # Avoid real provider pacing in this simulated regression, including Event.wait.
    result,updated,warnings=run_batch_to_xml(tmp_path,rows,'Groq',export,batch_runner=runner,confirm_test=True)
    assert providers==['Groq'] and len(http)==50 and len(set(http))==50
    assert len(result)==50 and all(r['provider']=='Groq' for r in result)
    assert xml_count(updated)==50 and len(checkpoints)>=7 and set(checkpoints)=={50}
    assert not warnings
    saved=json.loads((tmp_path/'.invoice_app/ai_batch_results.json').read_text())
    assert saved['new_ai_attempts']==saved['new_ai_attempt_limit']==50


def test_fifty_bad_responses_do_not_multiply_requests_across_three_apis(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path);providers=[];attempts=[]
    def batch(root,records,provider,**kwargs):
        providers.append(provider)
        def extract(root,row):attempts.append(row['digest']);raise ValueError('Groq returned invalid field types')
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    def runner(*args,**kwargs):return read_with_fallback(*args,batch_reader=batch,**kwargs)
    result,updated,warnings=run_batch_to_xml(tmp_path,rows,'Groq',lambda:process_sources(tmp_path),batch_runner=runner,confirm_test=True)
    assert providers==['Groq'] and len(attempts)==50
    assert all(r['provider']=='Python' for r in result)
    assert xml_count(updated)==50


def test_stop_during_gemini_still_returns_complete_xml(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path,5);stop=threading.Event();providers=[]
    def batch(root,records,provider,**kwargs):
        providers.append(provider)
        def extract(root,row):
            if provider=='Groq':raise ValueError('Groq HTTP 429: quota reached')
            if provider=='GitHub Models':raise ValueError('GitHub Models HTTP 429: quota reached')
            from Common_Rules import gemini_reader
            result=gemini_reader.extract_selected(root,row,lambda *args:reply(row,gemini_reader))
            stop.set();return result
        # Bypass pacing for this simulated test while retaining stop checks.
        class FastStop:
            def is_set(self):return stop.is_set()
            def wait(self,delay):return stop.is_set()
        kwargs['stop_event']=FastStop()
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    def runner(*args,**kwargs):return read_with_fallback(*args,batch_reader=batch,**kwargs)
    result,updated,warnings=run_batch_to_xml(tmp_path,rows,'Groq',lambda:process_sources(tmp_path),stop_event=stop,batch_runner=runner,confirm_test=True)
    assert providers==['Groq','GitHub Models','Gemini']
    assert sum(r['status']=='extracted' for r in result)==1
    assert xml_count(updated)==5 and stop.is_set()


def test_orphaned_saved_reads_reused_without_another_request(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path,3)
    for row in rows:
        github_models_reader.extract_selected(tmp_path,row,lambda *args:reply(row,github_models_reader))
        (tmp_path/'.invoice_app/api_selection'/(row['digest']+'.json')).unlink()
    def no_requests(*args,**kwargs):raise AssertionError('Cached results must prevent all requests')
    result=read_with_fallback(tmp_path,rows,primary='Groq',batch_reader=no_requests)
    assert all(r['provider']=='GitHub Models' and r['status']=='extracted' for r in result)


def test_report_save_failure_does_not_bypass_xml(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path,3)
    from Common_Rules import gemini_batch
    real_write=gemini_batch.write_json
    def write(path,data):
        if Path(path).name.endswith('batch_results.json'):raise OSError('Report file unavailable')
        return real_write(path,data)
    monkeypatch.setattr(gemini_batch,'write_json',write)
    def batch(root,records,provider,**kwargs):
        return read_batch(root,records,provider=provider,extract=lambda root,row:groq_reader.extract_selected(root,row,lambda *args:reply(row,groq_reader)),wait=lambda _:None,**kwargs)
    def runner(*args,**kwargs):return read_with_fallback(*args,batch_reader=batch,**kwargs)
    result,updated,warnings=run_batch_to_xml(tmp_path,rows,'Groq',lambda:process_sources(tmp_path),batch_runner=runner,confirm_test=True)
    assert xml_count(updated)==3 and all(r['provider']=='Groq' for r in result)


def test_unexpected_batch_failure_always_runs_final_export(tmp_path,monkeypatch):
    setup(monkeypatch);rows=sources(tmp_path,3);exports=[]
    def fail(*args,**kwargs):raise RuntimeError('Worker failed')
    def export():exports.append(True);return process_sources(tmp_path)
    result,updated,warnings=run_batch_to_xml(tmp_path,rows,'Groq',export,batch_runner=fail,confirm_test=True)
    assert len(exports)==2 and xml_count(updated)==3 and warnings

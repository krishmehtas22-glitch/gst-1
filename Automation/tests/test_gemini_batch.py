from copy import deepcopy
from pathlib import Path
import shutil
from Common_Rules.desktop import inspect_sources, process_sources
from Common_Rules.gemini_reader import extract_selected, candidate, FIELDS, ITEM_FIELDS
from Common_Rules.gemini_batch import read_batch


def records(tmp_path):
    shutil.copytree(Path(__file__).parent/'fixtures/client23',tmp_path/'Client')
    return inspect_sources(tmp_path)


def test_twenty_invoice_batch_applies_api_fields_and_generates_xml(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    monkeypatch.delenv('GEMINI_INVOICE_MODEL',raising=False)
    scanned=records(tmp_path);calls=[];waits=[]
    def extract(root,record):
        original=deepcopy(record['invoice'])
        response={k:original.get(k) for k in FIELDS}
        response['items']=[{k:item.get(k) for k in ITEM_FIELDS} for item in original['items']]
        def transport(*args):
            calls.append(record['digest']);return response
        return extract_selected(root,record,transport)
    results=read_batch(tmp_path,scanned,extract=extract,wait=waits.append,clock=lambda:0)
    assert len(results)==len(calls)==20
    assert waits==[13]*19
    assert all(r['status']=='extracted' for r in results)
    assert all(candidate(tmp_path,r)['extraction_warnings']==[] for r in scanned)
    assert not (tmp_path/'.invoice_app/reviews').exists()
    output=process_sources(tmp_path)
    assert len(output)==20 and all(not r['errors'] for r in output)
    assert list(tmp_path.rglob('Sales_Vouchers.xml'))
    calls.clear();waits.clear()
    read_batch(tmp_path,scanned,extract=extract,wait=waits.append,clock=lambda:0)
    assert not calls and not waits


def test_quota_error_stops_remaining_requests_and_reports_all_twenty(tmp_path,monkeypatch):
    monkeypatch.delenv('GEMINI_INVOICE_MODEL',raising=False)
    scanned=records(tmp_path);calls=[]
    def extract(*args):
        calls.append(1);raise ValueError('Gemini HTTP 429: Quota reached')
    results=read_batch(tmp_path,scanned,extract=extract,wait=lambda _:None)
    assert len(calls)==1 and len(results)==20
    assert results[0]['status']=='failed'
    assert all(r['status']=='not attempted' for r in results[1:])
    assert not list(tmp_path.rglob('Sales_Vouchers.xml'))


def test_one_failed_invoice_does_not_drop_remaining_sources(tmp_path,monkeypatch):
    monkeypatch.delenv('GEMINI_INVOICE_MODEL',raising=False)
    scanned=records(tmp_path);calls=[]
    def extract(*args):
        calls.append(1);raise ValueError('Gemini HTTP 503: high demand')
    results=read_batch(tmp_path,scanned,extract=extract,wait=lambda _:None)
    assert len(calls)==len(results)==20
    assert all(r['status']=='failed' for r in results)

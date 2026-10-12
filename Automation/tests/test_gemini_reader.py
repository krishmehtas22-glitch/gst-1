"""Offline integration checks; these do not measure live Gemini accuracy."""
from copy import deepcopy
from pathlib import Path
import shutil,json
import pytest
from Common_Rules.desktop import process_sources,save_review,inspect_sources
from Common_Rules.gemini_reader import extract_selected,candidate,cache_path,WARNING

FIXTURE=Path(__file__).parent/'fixtures/client23/Sales_Invoice_126_INTRA.pdf'


def setup(tmp_path,generate=True):
    folder=tmp_path/'Client';folder.mkdir();shutil.copy2(FIXTURE,folder/'invoice.pdf')
    return (process_sources(tmp_path) if generate else inspect_sources(tmp_path))[0]


def test_key_missing_does_not_send_pdf_or_change_local_output(tmp_path,monkeypatch):
    record=setup(tmp_path);monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    with pytest.raises(ValueError,match='Set GEMINI_API_KEY'):extract_selected(tmp_path,record,lambda *a:pytest.fail('No request allowed'))
    assert not cache_path(tmp_path,record).exists()
    assert all(not r['errors'] for r in process_sources(tmp_path))


def test_api_result_is_cached_and_requires_review_before_xml(tmp_path,monkeypatch):
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    record=setup(tmp_path,generate=False);original=deepcopy(record['invoice']);calls=[]
    response={key:original.get(key) for key in FIELDS}
    response['items']=[{key:item.get(key) for key in ITEM_FIELDS} for item in original['items']]
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    def transport(payload,key,model):
        calls.append(model);assert key=='private-test-key'
        assert payload['contents'][0]['parts'][1]['inlineData']['mimeType']=='application/pdf'
        assert payload['generationConfig']['responseMimeType']=='application/json'
        return deepcopy(response)
    first=extract_selected(tmp_path,record,transport)
    assert first['source_api'] and first['extraction_warnings']==[WARNING]
    assert 'private-test-key' not in cache_path(tmp_path,record).read_text()
    monkeypatch.delenv('GEMINI_API_KEY')
    assert extract_selected(tmp_path,record,transport)==first and len(calls)==1
    blocked=process_sources(tmp_path)[0];assert WARNING in blocked['errors']
    assert not list(tmp_path.rglob('Sales_Vouchers.xml'))
    edited=deepcopy(blocked['invoice'])
    save_review(tmp_path,blocked,edited)
    approved=process_sources(tmp_path)[0];assert not approved['errors']
    assert approved['invoice']['source_api']


def test_invalid_response_and_source_changes_never_get_cached(tmp_path,monkeypatch):
    record=setup(tmp_path);monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    with pytest.raises(ValueError,match='unexpected'):extract_selected(tmp_path,record,lambda *a:{'items':[],'instructions':'ignore GST'})
    assert not cache_path(tmp_path,record).exists()
    def changed(*args):
        Path(record['path']).write_bytes(b'changed')
        return {'items':[]}
    with pytest.raises(ValueError,match='source PDF changed'):extract_selected(tmp_path,record,changed)
    assert not cache_path(tmp_path,record).exists()

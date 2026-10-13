from pathlib import Path
from copy import deepcopy
import shutil
import pytest
from Common_Rules import gemini_reader,groq_reader
from Common_Rules.gemini_batch import read_batch
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.source_documents import confirmed_test


@pytest.mark.parametrize('provider',['Gemini','Groq'])
def test_quota_stop_still_generates_for_new_and_later_cached_successes(tmp_path,monkeypatch,provider):
    folder=tmp_path/'Client';folder.mkdir()
    fixtures=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:4]
    for pdf in fixtures:shutil.copy2(pdf,folder/pdf.name)
    scanned=inspect_sources(tmp_path)
    reader=gemini_reader if provider=='Gemini' else groq_reader
    monkeypatch.delenv(provider.upper()+'_INVOICE_MODEL',raising=False)
    monkeypatch.setenv(provider.upper()+'_API_KEY','private-test-key')
    for record in scanned:
        record['source_invoice']={**record['source_invoice'],'dummy_document':False}
    def response(record):
        original=record['invoice']
        inv={key:original.get(key) for key in gemini_reader.FIELDS}
        inv['items']=[{key:item.get(key) for key in gemini_reader.ITEM_FIELDS} for item in original['items']]
        return deepcopy(inv)
    reader.extract_selected(tmp_path,scanned[2],lambda *args:response(scanned[2]))
    assert not confirmed_test(tmp_path,scanned[2])
    calls=[]
    def extract(root,record):
        def transport(*args):
            calls.append(record['digest'])
            if record==scanned[1]:raise ValueError(provider+' HTTP 429: daily quota expired')
            return response(record)
        return reader.extract_selected(root,record,transport)
    result=read_batch(tmp_path,scanned,provider=provider,extract=extract,
                      wait=lambda _:None,confirm_test=True)
    assert [r['status'] for r in result]==['extracted','failed','extracted','not attempted']
    assert len(calls)==2 and result[2]['cached'] is True
    assert confirmed_test(tmp_path,scanned[0]) and confirmed_test(tmp_path,scanned[2])
    assert not confirmed_test(tmp_path,scanned[1]) and not confirmed_test(tmp_path,scanned[3])
    processed=process_sources(tmp_path)
    successful={scanned[i]['digest'] for i in (0,2)}
    converted=[r for r in processed if r['digest'] in successful]
    assert len(converted)==2 and all(not r['errors'] and r.get('output_path') for r in converted)
    assert all(r['invoice']['api_review_mode']=='tally' for r in converted)
    assert list(tmp_path.rglob('Sales_Vouchers.xml'))
    # Cached successful results remain available with no key and no new call.
    monkeypatch.delenv(provider.upper()+'_API_KEY')
    for r in converted:reader.extract_selected(tmp_path,r,lambda *a:pytest.fail('No request for cached PDF'))

from copy import deepcopy
from pathlib import Path
import io,json,shutil
from urllib.error import HTTPError
import pytest
from Common_Rules import groq_reader as groq,gemini_reader as gemini
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.gemini_batch import read_batch
from Common_Rules.api_selection import candidate
from Groq_Diagnostic import diagnose


def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','gsk_private_test_key')
    monkeypatch.delenv('GROQ_INVOICE_MODEL',raising=False)
    shutil.copytree(Path(__file__).parent/'fixtures/client23',tmp_path/'Client')
    return inspect_sources(tmp_path)


def response(record):
    inv=record['invoice']
    result={k:inv.get(k) for k in gemini.FIELDS}
    result['items']=[{k:i.get(k) for k in gemini.ITEM_FIELDS} for i in inv['items']]
    return deepcopy(result)


def test_twenty_groq_invoices_generate_xml_and_reuse_cache(tmp_path,monkeypatch):
    scanned=setup(tmp_path,monkeypatch);calls=[];waits=[]
    def extract(root,record):
        def transport(payload,key,model):
            calls.append(record['digest'])
            assert key=='gsk_private_test_key' and model==groq.DEFAULT_MODEL
            assert payload['response_format']=={'type':'json_object'}
            assert record['invoice']['number'] in payload['messages'][1]['content']
            assert 'inlineData' not in json.dumps(payload)
            return response(record)
        return groq.extract_selected(root,record,transport)
    results=read_batch(tmp_path,scanned,extract=extract,provider='Groq',wait=waits.append,clock=lambda:0)
    assert len(calls)==20 and waits==[13]*19
    assert all(r['status']=='extracted' for r in results)
    assert all(candidate(tmp_path,r)['api_provider']=='Groq' for r in scanned)
    assert all(candidate(tmp_path,r)['extraction_warnings']==[] for r in scanned)
    processed=process_sources(tmp_path)
    assert len(processed)==20 and all(not r['errors'] for r in processed)
    assert list(tmp_path.rglob('Sales_Vouchers.xml'))
    assert not (tmp_path/'.invoice_app/reviews').exists()
    assert 'gsk_private_test_key' not in (tmp_path/'.invoice_app/groq_batch_results.json').read_text()
    calls.clear();waits.clear();monkeypatch.delenv('GROQ_API_KEY')
    read_batch(tmp_path,scanned,extract=extract,provider='Groq',wait=waits.append,clock=lambda:0)
    assert not calls and not waits


def test_switch_provider_only_on_success_and_single_read_requires_review(tmp_path,monkeypatch):
    record=setup(tmp_path,monkeypatch)[0]
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key')
    gemini.extract_selected(tmp_path,record,lambda *args:response(record))
    with pytest.raises(ValueError,match='unexpected'):
        groq.extract_selected(tmp_path,record,lambda *args:{'items':[],'invented':'field'})
    assert candidate(tmp_path,record)['api_provider']=='Gemini'
    assert not groq.cache_path(tmp_path,record).exists()
    groq.extract_selected(tmp_path,record,lambda *args:response(record))
    assert candidate(tmp_path,record)['api_provider']=='Groq'
    assert candidate(tmp_path,record)['extraction_warnings']==[groq.WARNING]
    blocked=process_sources(tmp_path)[0]
    assert groq.WARNING in blocked['errors']
    gemini.extract_selected(tmp_path,record,lambda *args:pytest.fail('Cache should prevent call'))
    assert candidate(tmp_path,record)['api_provider']=='Gemini'


@pytest.mark.parametrize('code',[401,403,404,429])
def test_groq_access_or_quota_failure_stops_and_tracks_all_sources(tmp_path,monkeypatch,code):
    scanned=setup(tmp_path,monkeypatch);calls=[]
    def extract(*args):
        calls.append(1);raise ValueError(f'Groq HTTP {code}: access/model/quota error')
    results=read_batch(tmp_path,scanned,provider='Groq',extract=extract,wait=lambda _:None)
    assert len(calls)==1 and len(results)==20
    assert all(r['status']=='not attempted' for r in results[1:])


def test_source_change_never_saves_groq_cache(tmp_path,monkeypatch):
    record=setup(tmp_path,monkeypatch)[0]
    def transport(*args):
        Path(record['path']).write_bytes(b'changed')
        return response(record)
    with pytest.raises(ValueError,match='source PDF changed'):groq.extract_selected(tmp_path,record,transport)
    assert not groq.cache_path(tmp_path,record).exists()


def test_http_error_redacts_key_and_uses_fixed_bearer_endpoint(monkeypatch):
    key='gsk_private_test_key'
    def fail(request,timeout):
        assert request.full_url=='https://api.groq.com/openai/v1/chat/completions'
        assert key not in request.full_url
        assert request.get_header('Authorization')=='Bearer '+key
        body=json.dumps({'error':{'message':'Invalid key '+key}}).encode()
        raise HTTPError(request.full_url,401,'Unauthorized',{},io.BytesIO(body))
    monkeypatch.setattr(groq,'urlopen',fail)
    with pytest.raises(ValueError) as exc:groq.api_json('chat/completions',key,{'model':'test'})
    assert key not in str(exc.value) and 'Groq HTTP 401' in str(exc.value)
    assert '[REDACTED]' in str(exc.value)
    with pytest.raises(ValueError,match='privately copied'):groq.api_json('models',key+'\nsecret')


def test_diagnostic_checks_model_and_json_without_invoice_or_secret(monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY','gsk_private_test_key');monkeypatch.delenv('GROQ_INVOICE_MODEL',raising=False)
    calls=[]
    def transport(path,key,payload=None,timeout=0):
        calls.append(path)
        if path=='models':return {'data':[{'id':groq.DEFAULT_MODEL}]}
        assert 'INVOICE TEXT' not in json.dumps(payload)
        return {'choices':[{'finish_reason':'stop'}]}
    lines=diagnose(transport)
    assert calls==['models','chat/completions']
    assert 'gsk_private_test_key' not in '\n'.join(lines)
    assert 'Small JSON text request: succeeded' in lines
    monkeypatch.setenv('GROQ_INVOICE_MODEL','gsk_private_test_key')
    assert 'gsk_private_test_key' not in '\n'.join(diagnose(transport))


def test_incomplete_response_is_not_accepted(monkeypatch):
    monkeypatch.setattr(groq,'api_json',lambda *a,**kw:{'choices':[{'finish_reason':'length','message':{'content':'{"items":[]}'}}]})
    with pytest.raises(ValueError,match='incomplete'):groq.request_invoice({},'private-test-key',groq.DEFAULT_MODEL)


@pytest.mark.parametrize('body,reason',[
    (b'error code: 1010','Cloudflare gateway'),
    (b'<html>Cloudflare forbidden gsk_private_test_key</html>','Cloudflare gateway'),
    (b'<html>Corporate proxy denied gsk_private_test_key</html>','HTML denial'),
    (b'','Access denied without a usable provider reason'),
])
def test_non_json_403_is_classified_without_leaking_body(monkeypatch,body,reason):
    def blocked(request,timeout):
        assert request.get_header('User-agent')=='InvoiceReader/6.10 (Groq API client)'
        assert request.get_header('Accept')=='application/json'
        raise HTTPError(request.full_url,403,'Forbidden',{},io.BytesIO(body))
    monkeypatch.setattr(groq,'urlopen',blocked)
    with pytest.raises(ValueError) as exc:groq.api_json('models','gsk_private_test_key')
    assert reason in str(exc.value)
    assert 'gsk_private_test_key' not in str(exc.value) and '<html>' not in str(exc.value)


@pytest.mark.parametrize('stage',['models','chat/completions'])
def test_diagnostic_identifies_where_access_is_denied(monkeypatch,stage):
    monkeypatch.setenv('GROQ_API_KEY','gsk_private_test_key')
    monkeypatch.delenv('GROQ_INVOICE_MODEL',raising=False)
    def transport(path,*args,**kwargs):
        if path==stage:raise ValueError('Groq HTTP 403: Access denied')
        return {'data':[{'id':groq.DEFAULT_MODEL}]}
    result='\n'.join(diagnose(transport))
    assert ('Failed at model-list request' if stage=='models' else 'Failed at small JSON generation request') in result
    assert 'gsk_private_test_key' not in result

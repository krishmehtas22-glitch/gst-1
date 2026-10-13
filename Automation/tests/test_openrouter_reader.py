"""OpenRouter adds free-only transport, retaining shared extraction/output rules."""
import io,json,shutil
from pathlib import Path
from urllib.error import HTTPError
import xml.etree.ElementTree as ET
import pytest
from Common_Rules import openrouter_reader as router,groq_reader
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.gemini_batch import read_batch,read_with_fallback
from OpenRouter_Diagnostic import diagnose


def source(root):
    folder=root/'Client';folder.mkdir()
    for pdf in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:3]:shutil.copy2(pdf,folder/pdf.name)
    return inspect_sources(root)


def reply(row):
    invoice=row['invoice']
    return {**{k:invoice.get(k) for k in router.FIELDS},'items':[
        {k:item.get(k) for k in router.ITEM_FIELDS} for item in invoice['items']]}


@pytest.mark.parametrize('model',['openrouter/free','vendor/model:free'])
def test_only_explicit_free_models_allowed(monkeypatch,model):
    monkeypatch.setenv('OPENROUTER_INVOICE_MODEL',model)
    assert router.configured_model()==model


@pytest.mark.parametrize('model',['openai/gpt-4o','vendor/model','sk-or-v1-private-key','https://bad.example/model:free'])
def test_paid_or_invalid_models_rejected_before_any_request(monkeypatch,model):
    monkeypatch.setenv('OPENROUTER_INVOICE_MODEL',model)
    monkeypatch.setattr(router,'urlopen',lambda *a,**kw:pytest.fail('No request permitted'))
    with pytest.raises(ValueError,match='Paid model routing is disabled'):router.configured_model()


def test_fixed_endpoint_free_routing_and_no_paid_alternates(monkeypatch):
    captured=[]
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    def open_request(request,**kwargs):
        captured.append(request)
        return Response(b'{"choices": []}')
    monkeypatch.setattr(router,'urlopen',open_request)
    router.api_json('chat/completions','private-test-key',{'model':'openrouter/free','provider':{'max_price':{'prompt':99}}})
    assert captured[0].full_url=='https://openrouter.ai/api/v1/chat/completions'
    assert json.loads(captured[0].data)['provider']=={'max_price':{'prompt':0,'completion':0}}
    with pytest.raises(ValueError,match='Paid'):router.api_json('chat/completions','private-test-key',{'model':'paid/model'})
    with pytest.raises(ValueError,match='alternate'):router.api_json('chat/completions','private-test-key',{'model':'openrouter/free','models':['paid/model']})
    assert len(captured)==1


def test_shared_groq_input_cached_reuse_and_complete_xml(tmp_path,monkeypatch):
    rows=source(tmp_path);calls=[]
    monkeypatch.setenv('OPENROUTER_API_KEY','private-test-key')
    monkeypatch.delenv('OPENROUTER_INVOICE_MODEL',raising=False)
    def batch(root,records,provider,**kwargs):
        assert provider=='OpenRouter'
        def extract(root,row):
            def transport(payload,key,model):
                calls.append(payload)
                assert payload['messages']==groq_reader.prepare_invoice_payload(row,model)['messages']
                assert payload['provider']['max_price']=={'prompt':0,'completion':0}
                return reply(row)
            return router.extract_selected(root,row,transport)
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    result=read_with_fallback(tmp_path,rows,primary='OpenRouter',batch_reader=batch,confirm_test=True)
    assert len(calls)==3 and all(r['provider']=='OpenRouter' for r in result)
    updated=process_sources(tmp_path)
    assert len(ET.parse(Path(updated[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==3
    monkeypatch.delenv('OPENROUTER_API_KEY')
    read_with_fallback(tmp_path,rows,primary='Groq',batch_reader=lambda *a,**kw:pytest.fail('Never reread successful cache'))


def test_no_other_provider_key_reuse(tmp_path,monkeypatch):
    row=source(tmp_path)[0]
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    with pytest.raises(ValueError,match='OPENROUTER_API_KEY'):router.extract_selected(tmp_path,row,lambda *a:pytest.fail('No OpenRouter key'))


def test_credit_error_stops_free_provider_and_preserves_successes(tmp_path,monkeypatch):
    rows=source(tmp_path);calls=[]
    monkeypatch.setenv('OPENROUTER_API_KEY','private-test-key')
    def extract(root,row):
        calls.append(row['digest'])
        if len(calls)==2:raise ValueError('OpenRouter HTTP 402: quota/credit rejection')
        return router.extract_selected(root,row,lambda *a:reply(row))
    result=read_batch(tmp_path,rows,provider='OpenRouter',extract=extract,wait=lambda _:None)
    assert len(calls)==2 and [r['status'] for r in result]==['extracted','failed','not attempted']


def test_http_errors_hide_private_key(monkeypatch):
    key='sk-or-v1-private-12345'
    def fail(request,**kwargs):
        raise HTTPError(request.full_url,429,'quota',{},io.BytesIO(json.dumps({'error':{'message':'quota '+key}}).encode()))
    monkeypatch.setattr(router,'urlopen',fail)
    with pytest.raises(ValueError) as exc:router.api_json('models',key)
    assert key not in str(exc.value) and 'HTTP 429' in str(exc.value)


def test_diagnostic_only_sends_free_tiny_request(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','private-test-key');calls=[]
    def transport(path,key,payload=None,**kwargs):
        calls.append((path,payload))
        return {'data':[]} if path=='models' else {'choices':[{'finish_reason':'stop'}]}
    lines=diagnose(transport)
    assert len(calls)==2 and calls[1][1]['model']=='openrouter/free'
    assert calls[1][1]['provider']['max_price']=={'prompt':0,'completion':0}
    assert 'private-test-key' not in '\n'.join(lines)

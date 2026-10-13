from pathlib import Path
import io,json,shutil
import xml.etree.ElementTree as ET
from urllib.error import HTTPError
import pytest
from Common_Rules import github_models_reader as github_models,gemini_reader,groq_reader
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.gemini_batch import read_batch,read_with_fallback
from Common_Rules.api_selection import candidate
from GitHub_Models_Diagnostic import diagnose


def setup(root,monkeypatch):
    shutil.copytree(Path(__file__).parent/'fixtures/client23',root/'Client')
    for provider in ('GEMINI','GROQ'):
        monkeypatch.setenv(provider+'_API_KEY','private-test-key')
        monkeypatch.delenv(provider+'_INVOICE_MODEL',raising=False)
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','private-test-key')
    monkeypatch.delenv('GITHUB_INVOICE_MODEL',raising=False)
    return inspect_sources(root)


def response(record):
    inv=record['invoice'];result={k:inv.get(k) for k in gemini_reader.FIELDS}
    result['items']=[{k:i.get(k) for k in gemini_reader.ITEM_FIELDS} for i in inv['items']]
    return result


def test_github_models_20_cached_results_and_every_buyer_master(tmp_path,monkeypatch):
    records=setup(tmp_path,monkeypatch);calls=[];waits=[]
    def extract(root,record):
        def transport(payload,key,model):
            calls.append(record['digest'])
            assert model==github_models.DEFAULT_MODEL and key=='private-test-key'
            assert payload['max_tokens']==4000
            assert payload['response_format']=={'type':'json_object'}
            prompt=payload['messages'][0]['content']
            assert 'Bill To' in prompt and 'Ship To' in prompt and 'unit_reason' in prompt
            assert record['invoice']['number'] in payload['messages'][1]['content']
            return response(record)
        return github_models.extract_selected(root,record,transport)
    results=read_batch(tmp_path,records,extract=extract,provider='GitHub Models',wait=waits.append,clock=lambda:0)
    assert len(calls)==20 and waits==pytest.approx([4.1]*19)
    assert all(r['status']=='extracted' for r in results)
    assert all(candidate(tmp_path,r)['api_provider']=='GitHub Models' for r in records)
    monkeypatch.delenv('GITHUB_MODELS_TOKEN');calls.clear();waits.clear()
    read_batch(tmp_path,records,extract=extract,provider='GitHub Models',wait=waits.append,clock=lambda:0)
    assert not calls and not waits
    from Common_Rules.tally_review_export import enable
    enable(tmp_path,'Client');output=process_sources(tmp_path)
    folder=Path(output[0]['output_path']);masters=ET.parse(folder/'Masters.xml');vouchers=ET.parse(folder/'Sales_Vouchers.xml')
    buyers={v.findtext('PARTYLEDGERNAME') for v in vouchers.findall('.//VOUCHER')}
    debtors={m.attrib['NAME'] for m in masters.findall('.//LEDGER') if m.findtext('PARENT')=='Sundry Debtors'}
    assert buyers==debtors and len(vouchers.findall('.//VOUCHER'))==20
    report=json.loads((folder/'Batch_Report.json').read_text())
    assert {r['buyer_ledger'] for r in report['invoices']}==buyers
    assert all(r['buyer']==r['extracted_invoice']['buyer_name'] for r in report['invoices'])


def test_three_provider_exhaustion_keeps_all_twenty_outputs(tmp_path,monkeypatch):
    records=setup(tmp_path,monkeypatch);calls={'GitHub Models':0,'Groq':0,'Gemini':0}
    readers={'GitHub Models':github_models,'Groq':groq_reader,'Gemini':gemini_reader}
    quotas={'GitHub Models':3,'Groq':3,'Gemini':2}
    def batch(root,pending,provider,**kwargs):
        reader=readers[provider]
        def extract(root,record):
            def transport(*args):
                calls[provider]+=1
                if calls[provider]>quotas[provider]:raise ValueError(provider+' HTTP 429: free quota')
                return response(record)
            return reader.extract_selected(root,record,transport)
        return read_batch(root,pending,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    results=read_with_fallback(tmp_path,records,primary='GitHub Models',batch_reader=batch)
    assert calls=={'GitHub Models':4,'Groq':4,'Gemini':3}
    assert sum(r['status']=='extracted' for r in results)==8
    assert sum(r['provider']=='Python' for r in results)==12
    output=process_sources(tmp_path)
    assert all(not r['errors'] for r in output)
    assert len(ET.parse(Path(output[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==20


def test_github_models_http_redaction_and_fixed_endpoint(monkeypatch):
    key='github_pat_private_test_key'
    def fail(request,timeout):
        assert request.full_url=='https://models.github.ai/inference/chat/completions'
        assert request.get_header('Authorization')=='Bearer '+key
        assert request.get_header('User-agent')=='InvoiceReader/7.7 (GitHub Models API client)'
        body=json.dumps({'error':{'message':'Denied '+key}}).encode()
        raise HTTPError(request.full_url,401,'Unauthorized',{},io.BytesIO(body))
    monkeypatch.setattr(github_models,'urlopen',fail)
    with pytest.raises(ValueError) as exc:github_models.api_json('chat/completions',key,{})
    assert 'GitHub Models HTTP 401' in str(exc.value) and key not in str(exc.value)
    with pytest.raises(ValueError,match='privately copied'):github_models.api_json('models',key+'\nprivate')


def test_github_models_diagnostic_uses_no_invoice_and_no_key_output(monkeypatch):
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','github_pat_private_test_key');monkeypatch.delenv('GITHUB_INVOICE_MODEL',raising=False)
    calls=[]
    def transport(path,key,payload=None,timeout=0):
        calls.append(path)
        if path=='models':return {'data':[{'id':github_models.DEFAULT_MODEL}]}
        assert payload['max_tokens']==64 and 'INVOICE TEXT' not in json.dumps(payload)
        return {'choices':[{'finish_reason':'stop'}]}
    output='\n'.join(diagnose(transport))
    assert calls==['models','chat/completions']
    assert 'Small JSON text request: succeeded' in output and 'github_pat_private_test_key' not in output


def test_failed_github_models_response_preserves_prior_groq_selection(tmp_path,monkeypatch):
    record=setup(tmp_path,monkeypatch)[0]
    groq_reader.extract_selected(tmp_path,record,lambda *a:response(record))
    with pytest.raises(ValueError,match='unexpected'):github_models.extract_selected(tmp_path,record,lambda *a:{'items':[],'invented':'field'})
    assert candidate(tmp_path,record)['api_provider']=='Groq'
    assert not github_models.cache_path(tmp_path,record).exists()


@pytest.mark.parametrize('provider',['GitHub Models','Groq','Gemini'])
def test_every_provider_prompt_contains_same_party_unit_rules(tmp_path,monkeypatch,provider):
    from Common_Rules.ai_providers import reader
    from Common_Rules.ai_invoice_rules import RULES
    record=setup(tmp_path,monkeypatch)[0]
    def transport(payload,*args):
        prompt=payload['systemInstruction']['parts'][0]['text'] if provider=='Gemini' else payload['messages'][0]['content']
        assert RULES in prompt
        assert 'never copy the seller into buyer' in prompt
        assert 'Printed selling units and explicit quantity suffixes' in prompt
        return response(record)
    reader(provider).extract_selected(tmp_path,record,transport)
    assert candidate(tmp_path,record)['api_provider']==provider


@pytest.mark.parametrize('wrapped',[False,True])
def test_catalog_shapes_and_model_endpoint(monkeypatch,wrapped):
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','github_pat_private_test_key')
    monkeypatch.delenv('GITHUB_INVOICE_MODEL',raising=False)
    calls=[]
    def transport(path,key,payload=None,timeout=0):
        calls.append(path)
        if path=='models':
            catalog=[{'id':github_models.DEFAULT_MODEL}]
            return {'data':catalog} if wrapped else catalog
        return {'choices':[{'finish_reason':'stop'}]}
    assert 'Small JSON text request: succeeded' in '\n'.join(diagnose(transport))
    assert calls==['models','chat/completions']
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return b'[]'
    def request(req,timeout):
        assert req.full_url=='https://models.github.ai/catalog/models'
        assert req.get_method()=='GET'
        return Response()
    monkeypatch.setattr(github_models,'urlopen',request)
    assert github_models.api_json('models','github_pat_private_test_key')==[]


def test_repository_auth_and_cerebras_are_not_used_for_models(tmp_path,monkeypatch):
    record=setup(tmp_path,monkeypatch)[0]
    monkeypatch.delenv('GITHUB_MODELS_TOKEN')
    monkeypatch.setenv('GITHUB_TOKEN','repository-only-token')
    monkeypatch.setenv('CEREBRAS_API_KEY','private-cerebras-key')
    with pytest.raises(ValueError,match='Set GITHUB_MODELS_TOKEN'):
        github_models.extract_selected(tmp_path,record,lambda *a:pytest.fail('Must not reuse repository token'))
    calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        return [{'status':'failed','error':'quota'} for _ in records]
    read_with_fallback(tmp_path,[record],primary='GitHub Models',batch_reader=batch)
    assert calls==['GitHub Models','Groq','Gemini'] and 'Cerebras' not in calls

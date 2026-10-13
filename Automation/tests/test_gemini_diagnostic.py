import io,json
from urllib.error import HTTPError
import pytest
from Common_Rules import gemini_reader as reader
from Gemini_Diagnostic import diagnose


def test_provider_404_reason_and_model_are_visible_but_key_is_redacted(monkeypatch):
    key='private-test-key'
    def fail(request,timeout):
        assert request.full_url=='https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent'
        assert key not in request.full_url
        body={'error':{'status':'NOT_FOUND','message':'Specific project resource missing; key='+key+'; key URL https://example.test/?key='+key}}
        raise HTTPError(request.full_url,404,'Not Found',{},io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(reader,'urlopen',fail)
    with pytest.raises(ValueError) as caught:reader.request_invoice({},key,'gemini-2.5-flash')
    message=str(caught.value)
    assert 'Specific project resource missing' in message and '[NOT_FOUND]' in message
    assert 'Model gemini-2.5-flash' in message and key not in message


def test_successful_structured_http_response_is_decoded(monkeypatch):
    expected={'number':'INV-1','items':[]}
    def reply(request,timeout):
        assert request.get_header('X-goog-api-key')=='private-test-key'
        assert request.method=='POST'
        assert json.loads(request.data)=={'contents':[]}
        result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(expected)}]}}]}
        return io.BytesIO(json.dumps(result).encode())
    monkeypatch.setattr(reader,'urlopen',reply)
    assert reader.request_invoice({'contents':[]},'private-test-key','gemini-2.5-flash')==expected


def test_diagnostic_distinguishes_list_access_from_generation_failure(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key');monkeypatch.setenv('GEMINI_INVOICE_MODEL','gemini-2.5-flash')
    calls=[]
    def transport(path,key,payload=None,timeout=35):
        calls.append((path,payload))
        if payload is None:return {'models':[{'name':'models/gemini-2.5-flash','supportedGenerationMethods':['generateContent']}]}
        assert payload['contents']==[{'parts':[{'text':'Reply only OK.'}]}]
        raise ValueError('Gemini HTTP 404 [NOT_FOUND]: Resource missing')
    lines=diagnose(transport);text='\n'.join(lines)
    assert 'Model-list request: succeeded' in text and 'Configured model listed for generateContent: yes' in text
    assert 'Small text-generation request failed' in text
    assert 'private-test-key' not in text and len(calls)==2
    assert not any('inlineData' in str(payload) for _,payload in calls)


def test_diagnostic_missing_key_does_not_make_network_request(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    assert 'GEMINI_API_KEY present: no' in diagnose(lambda *a,**kw:pytest.fail('No request allowed'))


def test_model_not_listed_does_not_request_generation(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key');monkeypatch.setenv('GEMINI_INVOICE_MODEL','gemini-2.5-flash')
    def transport(path,key,payload=None,timeout=35):
        assert payload is None
        return {'models':[{'name':'models/gemini-2.5-pro','supportedGenerationMethods':['generateContent']}]}
    text='\n'.join(diagnose(transport))
    assert 'Configured model listed for generateContent: no' in text and 'gemini-2.5-pro' in text


def test_invalid_key_cannot_leak_through_http_header_exception(monkeypatch):
    key='private-test-key\ninvalid'
    monkeypatch.setattr(reader,'urlopen',lambda *a,**kw:pytest.fail('No network request allowed'))
    with pytest.raises(ValueError) as caught:reader.api_json('models',key)
    assert key not in str(caught.value) and 'without quotes' in str(caught.value)

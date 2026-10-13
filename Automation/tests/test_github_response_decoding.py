import gzip,io,json,zlib
import pytest
from Common_Rules import github_models_reader as reader
from GitHub_Models_Diagnostic import diagnose


class Response:
    def __init__(self,body,headers=None):self.stream=io.BytesIO(body);self.headers=headers or {}
    def read(self,limit):return self.stream.read(limit)
    def __enter__(self):return self
    def __exit__(self,*args):pass


@pytest.mark.parametrize('encoding',['plain','gzip','gzip-no-header','deflate','raw-deflate'])
def test_supported_http_encodings_preserve_json(encoding):
    payload=[{'id':'openai/gpt-4o'}];raw=json.dumps(payload).encode();headers={}
    if encoding.startswith('gzip'):
        raw=gzip.compress(raw)
        if encoding=='gzip':headers['Content-Encoding']='gzip'
    elif encoding=='deflate':raw=zlib.compress(raw);headers['Content-Encoding']='deflate'
    elif encoding=='raw-deflate':raw=zlib.compress(raw)[2:-4];headers['Content-Encoding']='deflate'
    assert reader.decode_response(Response(raw,headers),'models')==payload


def test_utf_bom_is_valid_json():
    assert reader.decode_response(Response(b'\xef\xbb\xbf[]'),'models')==[]


@pytest.mark.parametrize('body',[b'',b'<html>github_pat_private_test_key</html>',b'not-json github_pat_private_test_key'])
def test_bad_response_gives_reason_without_leaking_body(body):
    with pytest.raises(ValueError) as exc:reader.decode_response(Response(body),'models')
    assert 'github_pat_private_test_key' not in str(exc.value)
    assert 'empty response' in str(exc.value) or 'HTML page' in str(exc.value) or 'non-JSON data' in str(exc.value)


def test_decompressed_size_limit_is_enforced():
    with pytest.raises(ValueError,match='exceeded'):reader.decode_response(Response(gzip.compress(b' '* (2*1024*1024+2)),{'Content-Encoding':'gzip'}),'models')


def test_catalog_failure_does_not_hide_successful_inference(monkeypatch):
    monkeypatch.setenv('GITHUB_MODELS_TOKEN','private-test-key');monkeypatch.delenv('GITHUB_INVOICE_MODEL',raising=False)
    calls=[]
    def transport(path,*args,**kwargs):
        calls.append(path)
        if path=='models':raise ValueError('GitHub Models returned an HTML page instead of API JSON')
        return {'choices':[{'finish_reason':'stop'}]}
    output='\n'.join(diagnose(transport))
    assert calls==['models','chat/completions']
    assert 'Model-list request failed:' in output
    assert 'Small JSON text request: succeeded' in output
    assert 'private-test-key' not in output


def test_json_accept_and_identity_encoding_are_sent(monkeypatch):
    def transport(request,timeout):
        assert request.get_header('Accept')=='application/vnd.github+json'
        assert request.get_header('Accept-encoding')=='identity'
        assert request.get_header('Authorization')=='Bearer private-test-key'
        return Response(b'[]')
    monkeypatch.setattr(reader,'urlopen',transport)
    assert reader.api_json('models','private-test-key')==[]

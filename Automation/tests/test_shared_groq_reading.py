from copy import deepcopy
from pathlib import Path
import json,shutil
import pytest
from Common_Rules import groq_reader,gemini_reader,github_models_reader,openrouter_reader
from Common_Rules.desktop import inspect_sources
from Common_Rules.engine import read_json


def test_active_providers_read_exactly_same_groq_prompt_and_document(tmp_path,monkeypatch):
    folder=tmp_path/'Client';folder.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/client23/Sales_Invoice_126_INTRA.pdf',folder/'invoice.pdf')
    record=inspect_sources(tmp_path)[0];original=deepcopy(record['invoice'])
    for name in ('GEMINI_INVOICE_MODEL','GROQ_INVOICE_MODEL','GITHUB_INVOICE_MODEL','OPENROUTER_INVOICE_MODEL'):monkeypatch.delenv(name,raising=False)
    for name in ('GEMINI_API_KEY','GROQ_API_KEY','GITHUB_MODELS_TOKEN','OPENROUTER_API_KEY'):monkeypatch.setenv(name,'private-test-key')
    captured={};results={}
    for provider,reader in [('Groq',groq_reader),('Gemini',gemini_reader),('GitHub Models',github_models_reader),('OpenRouter',openrouter_reader)]:
        def transport(payload,key,model):
            captured[provider]=deepcopy(payload)
            result={field:original.get(field) for field in gemini_reader.FIELDS}
            result['items']=[{field:item.get(field) for field in gemini_reader.ITEM_FIELDS} for item in original['items']]
            return result
        results[provider]=reader.extract_selected(tmp_path,record,transport)
    groq=captured['Groq'];gemini=captured['Gemini'];github=captured['GitHub Models']
    assert github['messages']==groq['messages']
    assert captured['OpenRouter']['messages']==groq['messages']
    assert captured['OpenRouter']['temperature']==groq['temperature']
    assert captured['OpenRouter']['provider']['max_price']=={'prompt':0,'completion':0}
    assert gemini['systemInstruction']['parts'][0]['text']==groq['messages'][0]['content']
    assert gemini['contents'][0]['parts'][0]['text']==groq['messages'][1]['content']
    assert 'inlineData' not in json.dumps(gemini)
    assert groq['temperature']==github['temperature']==gemini['generationConfig']['temperature']==0
    def facts(result):
        invoice={key:result.get(key) for key in gemini_reader.FIELDS}
        invoice['items']=[{key:item.get(key) for key in gemini_reader.ITEM_FIELDS} for item in result['items']]
        return invoice
    # Provider-labelled audit evidence differs; extracted business fields do not.
    assert all(facts(result)==facts(results['Groq']) for result in results.values())
    assert read_json(gemini_reader.cache_path(tmp_path,record))['reading_style']=='groq-text-v1'
    assert read_json(github_models_reader.cache_path(tmp_path,record))['reading_style']=='groq-text-v1'
    assert read_json(openrouter_reader.cache_path(tmp_path,record))['reading_style']=='groq-text-v1'


@pytest.mark.parametrize('provider',['Groq','Gemini','GitHub Models','OpenRouter'])
def test_local_ocr_text_is_the_provider_document_input(tmp_path,monkeypatch,provider):
    from Common_Rules.ai_providers import reader
    folder=tmp_path/'Client';folder.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/client23/Sales_Invoice_126_INTRA.pdf',folder/'invoice.pdf')
    record=inspect_sources(tmp_path)[0]
    import Common_Rules.extraction as extraction
    ocr='OCR EXTRACTED TEXT - MANUAL VERIFICATION REQUIRED\nInvoice text from a scanned page'
    monkeypatch.setattr(extraction,'text_from_pdf',lambda path:ocr)
    for name in ('GEMINI_API_KEY','GROQ_API_KEY','GITHUB_MODELS_TOKEN','OPENROUTER_API_KEY'):monkeypatch.setenv(name,'private-test-key')
    for name in ('GEMINI_INVOICE_MODEL','GROQ_INVOICE_MODEL','GITHUB_INVOICE_MODEL','OPENROUTER_INVOICE_MODEL'):monkeypatch.delenv(name,raising=False)
    def transport(payload,*args):
        text=payload['contents'][0]['parts'][0]['text'] if provider=='Gemini' else payload['messages'][1]['content']
        assert text=='INVOICE TEXT\n'+ocr
        return {'items':[]}
    reader(provider).extract_selected(tmp_path,record,transport)

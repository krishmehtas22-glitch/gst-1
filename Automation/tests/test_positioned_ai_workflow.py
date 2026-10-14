from copy import deepcopy
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from Reading_V2.ai_assist import Budget, assist, check_evidence, payload
from Reading_V2.pipeline import run


def source(tmp_path):
    path = tmp_path/'source.pdf'
    path.write_bytes(b'contract-test-source')
    words = ['INV-123', '2026-01-02', '12.50', 'Widget', '2.5', 'KG', '5.00']
    tokens = [{'id': f'p1w{i+1}', 'text': value, 'box': [.1,.1,.2,.2],
               'origin': 'pdf', 'ocr_confidence': None} for i,value in enumerate(words)]
    result = {'version': 'test-reader', 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'document': {'version': 'test-document', 'pages': [{'number': 1, 'tokens': tokens,
                   'lines': [{'id': 'p1l1', 'text': ' '.join(words), 'box': [.1,.1,.2,.2], 'tokens': tokens}]}]},
              'invoice': {'number': 'OLD', 'items': []}, 'warnings': [], 'review_required': True,
              'invoice_grouping_required': False, 'document_kind': 'invoice_candidate'}
    response = {'invoice': {'number':'INV-123','date':'2026-01-02','total':'12.50',
                           'items':[{'name':'Widget','quantity':'2.5','unit':'KG','rate':'5.00',
                                     'value':'12.50','unit_basis':'printed'}]},
                'evidence': {'fields': {'number':['p1w1'],'date':['p1w2'],'total':['p1w3']},
                             'items':[{'name':['p1w4'],'quantity':['p1w5'],'unit':['p1w6'],
                                       'rate':['p1w7'],'value':['p1w3']}]}}
    return path,result,response


def test_cached_success_is_terminal_even_after_budget_expires(tmp_path):
    path,result,response = source(tmp_path)
    calls = []
    def transport(*args):
        calls.append(1)
        return deepcopy(response)
    first = assist(path,result,tmp_path/'cache',Budget(1),transport=transport,model='test-model')
    second = assist(path,result,tmp_path/'cache',Budget(0),transport=transport,model='test-model')
    assert first['status']=='extracted' and second['status']=='cached' and len(calls)==1
    assert second['result']['invoice']['items'][0]['quantity']=='2.5'
    assert second['result']['review_required'] and result['invoice']['number']=='OLD'


@pytest.mark.parametrize('mutation', ['unknown_id','invented_total','scaled_quantity','wrong_date','repeated_id'])
def test_source_evidence_rejects_invented_values(tmp_path,mutation):
    path,result,response = source(tmp_path)
    if mutation=='unknown_id':response['evidence']['fields']['total']=['p99w99']
    if mutation=='invented_total':response['invoice']['total']='999.00'
    if mutation=='scaled_quantity':response['invoice']['items'][0]['quantity']='2500'
    if mutation=='wrong_date':response['invoice']['date']='2026-02-01'
    if mutation=='repeated_id':response['evidence']['fields']['total']=['p1w3','p1w3']
    with pytest.raises(ValueError):check_evidence(response,result)


def test_rate_limit_disables_primary_without_discarding_local_read(tmp_path):
    path,result,response = source(tmp_path)
    budget=Budget(3)
    def quota(*args):raise ValueError('Groq HTTP 429: quota reached')
    primary=assist(path,result,tmp_path/'cache',budget,transport=quota,model='test-model')
    assert primary['status']=='rate_limited' and primary['result'] is result
    assert not budget.stopped and 'Groq' in budget.disabled
    again=assist(path,result,tmp_path/'cache',budget,transport=quota,model='test-model')
    assert again['status']=='provider_unavailable' and budget.used==1
    secondary=assist(path,result,tmp_path/'cache',budget,provider='Gemini',
                     transport=lambda *args:deepcopy(response),model='test-model')
    assert secondary['status']=='extracted' and budget.used==2


def test_unknown_connection_failure_is_not_retried(tmp_path):
    path,result,response=source(tmp_path)
    budget=Budget(3);calls=[]
    def timeout(*args):
        calls.append(1)
        raise TimeoutError('sensitive response detail')
    first=assist(path,result,tmp_path/'cache',budget,transport=timeout,model='test-model')
    second=assist(path,result,tmp_path/'cache',budget,transport=timeout,model='test-model')
    assert first['status']=='request_failed' and second['status']=='stopped'
    assert len(calls)==1 and 'sensitive' not in json.dumps(first)


def test_unconfigured_provider_consumes_no_request(tmp_path,monkeypatch):
    path,result,_=source(tmp_path);monkeypatch.delenv('GROQ_API_KEY',raising=False)
    budget=Budget(10)
    answer=assist(path,result,tmp_path/'cache',budget,model='test-model')
    assert answer['status']=='not_configured' and budget.used==0
    assert not (tmp_path/'cache').exists()


def test_source_changes_are_rejected_before_call(tmp_path):
    path,result,response=source(tmp_path);path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='Source changed'):
        assist(path,result,tmp_path/'cache',Budget(1),transport=lambda *args:response,model='test-model')


def test_missing_quantity_is_not_filled_by_unit_normalization(tmp_path):
    path,result,response=source(tmp_path)
    response['invoice']['items'][0]['quantity']=None
    answer=assist(path,result,tmp_path/'cache',Budget(1),transport=lambda *args:response,model='test-model')
    assert 'quantity' not in answer['result']['invoice']['items'][0]


def test_partial_ai_items_do_not_erase_local_items(tmp_path):
    path,result,response=source(tmp_path)
    result['invoice']['items']=[{'name':'Source row 1'},{'name':'Source row 2'}]
    answer=assist(path,result,tmp_path/'cache',Budget(1),transport=lambda *args:response,model='test-model')
    assert answer['result']['invoice']['items']==result['invoice']['items']


def test_multiple_invoices_and_budget_limit_never_send_requests(tmp_path):
    path,result,response=source(tmp_path)
    result['invoice_grouping_required']=True
    answer=assist(path,result,tmp_path/'cache',Budget(1),transport=lambda *args:pytest.fail('request'),model='test-model')
    assert answer['status']=='grouping_or_document_review'
    result['invoice_grouping_required']=False
    answer=assist(path,result,tmp_path/'cache',Budget(0),transport=lambda *args:pytest.fail('request'),model='test-model')
    assert answer['status']=='budget_exhausted'


def test_separate_workflow_produces_all_three_xml_without_tally(tmp_path):
    paths=sorted((Path(__file__).parent/'fixtures/client1').glob('*.pdf'))[:2]
    originals={p:p.read_bytes() for p in paths}
    summary=run(paths,tmp_path/'report',xml=True,progress=lambda _:None)
    assert summary['read_pdfs']==len(paths) and summary['failed_pdfs']==0
    assert summary['ai_requests']==summary['tally_imports']==0
    assert summary['xml']['voucher_count']==len(paths)
    assert not summary['xml']['financial_accuracy_proven']
    for folder in summary['xml']['folders']:
        assert all((Path(folder)/name).is_file() for name in ['Units.xml','Masters.xml','Sales_Vouchers.xml'])
        assert len(ET.parse(Path(folder)/'Sales_Vouchers.xml').findall('.//VOUCHER'))==len(paths)
    assert all(p.read_bytes()==raw for p,raw in originals.items())


def test_saved_human_corrections_are_retained_without_ai_requests(tmp_path):
    import shutil
    fixture=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    source_root=tmp_path/'source';source_root.mkdir()
    source=source_root/'invoice.pdf';shutil.copyfile(fixture,source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    reviews=source_root/'.invoice_app/reviews';reviews.mkdir(parents=True)
    saved=reviews/(digest+'.json')
    invoice={'number':'HUMAN-99','date':'2026-01-02','buyer_name':'Approved Buyer','items':[],'total':'12.50'}
    saved.write_text(json.dumps({'source_sha256':digest,'approved':True,'invoice':invoice}))
    original=saved.read_bytes()
    result=run([source],tmp_path/'out',providers=['Groq'],maximum=1,
               source_root=source_root,transport=lambda *args:pytest.fail('unnecessary request'),progress=lambda _:None)
    assert result['ai_requests']==0 and result['documents'][0]['ai_status']=='approved_review'
    output=json.loads((tmp_path/'out'/result['documents'][0]['result_file']).read_text())
    assert output['invoice']==invoice and saved.read_bytes()==original


def test_rejected_ai_evidence_retains_source_and_xml(tmp_path,monkeypatch):
    from Reading_V2 import pipeline
    original=pipeline.read_invoice
    def needs_review(*args,**kwargs):
        result=original(*args,**kwargs);result['review_required']=True;return result
    monkeypatch.setattr(pipeline,'read_invoice',needs_review)
    source=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    response={'invoice':{'total':'9999','items':[]},'evidence':{'fields':{'total':['unknown']},'items':[]}}
    result=run([source],tmp_path/'out',providers=['Groq'],maximum=1,xml=True,
               transport=lambda *args:response,progress=lambda _:None)
    assert result['read_pdfs']==1 and result['failed_pdfs']==0
    assert result['xml']['voucher_count']==1 and result['ai_requests']==1
    assert result['documents'][0]['ai_status']=='evidence_or_configuration_rejected'

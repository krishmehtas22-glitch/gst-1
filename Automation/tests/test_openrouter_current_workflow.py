"""Explicit free-only OpenRouter integration; no external API/Tally requests."""
import json
from pathlib import Path
import pytest
from Common_Rules import openrouter_reader as router
from Common_Rules.gemini_batch import RequestBudget,read_with_fallback
from Common_Rules.invoice_document import from_legacy
from Common_Rules.workflow_validation import checks
from test_ai_workflow_validation import source_row,output,server


def test_nested_openrouter_read_reuses_verified_cache_and_produces_xml(tmp_path,monkeypatch):
    row=source_row(tmp_path);monkeypatch.setenv('OPENROUTER_API_KEY','private-test-key')
    monkeypatch.setattr('Common_Rules.extraction.text_from_pdf',lambda path:'Invoice No: '+row['invoice']['number'])
    answer={'schema_version':2,'invoices':[from_legacy(row['invoice'],row)['invoice']]}
    calls=[]
    def transport(payload,*args):
        calls.append(payload)
        assert payload['provider']['max_price']=={'prompt':0,'completion':0}
        assert 'schema_version' in payload['messages'][0]['content']
        return answer
    result=router.extract_selected(tmp_path,row,transport)
    assert result['_document_v2']['schema_version']==2
    saved=json.loads(router.cache_path(tmp_path,row).read_text())
    assert saved['document']['provenance']['provider']=='OpenRouter'
    router.extract_selected(tmp_path,row,lambda *a:pytest.fail('No reread'))
    assert len(calls)==1
    row['invoice']=result
    folder,plan,voucher=output(tmp_path,row)
    assert voucher.findtext('VOUCHERNUMBER')==result['number']
    assert voucher.findtext('DATE')==result['date'].replace('-','')


def test_router_failure_never_requests_a_different_provider(tmp_path,monkeypatch):
    row=source_row(tmp_path);seen=[]
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    def batch(root,records,provider,request_budget,**kwargs):
        seen.append(provider);assert request_budget.claim()
        return [{'client':r['client'],'path':r['path'],'digest':r['digest'],'status':'failed','error':'OpenRouter HTTP 429: quota'} for r in records]
    result=read_with_fallback(tmp_path,[row],primary='OpenRouter',batch_reader=batch)
    assert seen==['OpenRouter'] and result[0]['status']!='extracted'


def test_retained_read_matching_uses_only_openrouter_key_and_budget(tmp_path,monkeypatch):
    from test_tally_master_matching import setup,choices
    from Common_Rules.tally_master_matching import match_path
    row,ctx=setup(tmp_path);match_path(tmp_path,row).unlink();calls=[]
    import hashlib
    Path(row['path']).write_bytes(b'Matching fixture source')
    row['digest']=hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
    monkeypatch.delenv('GROQ_API_KEY',raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY','router-private-test-key')
    def transport(payload,key,model):
        calls.append(key);assert payload['provider']['max_price']['prompt']==0
        return {'_tally_matches':choices()}
    budget=RequestBudget(1)
    assert router.match_cached(tmp_path,row,budget,transport=transport)
    assert calls==['router-private-test-key'] and budget.used==1
    assert not router.match_cached(tmp_path,row,budget,transport=transport)


def test_legacy_router_cache_migrates_without_call(tmp_path):
    row=source_row(tmp_path);path=router.cache_path(tmp_path,row);path.parent.mkdir(parents=True)
    saved={'revision':'openrouter-text-v1','model':router.configured_model(),'source_sha256':row['digest'],'invoice':row['invoice']}
    path.write_text(json.dumps(saved));before=path.read_bytes()
    result=router.extract_selected(tmp_path,row,lambda *a:pytest.fail('No migration call'))
    assert result['_document_v2']['schema_version']==2 and path.read_bytes()==before


def test_gstin_check_digit_never_causes_invoice_rejection(tmp_path):
    row=source_row(tmp_path);invoice=row['invoice']
    for role in ('seller','buyer'):
        value=invoice[role+'_gstin'];invoice[role+'_gstin']=value[:-1]+('0' if value[-1]!='0' else '1')
    assert not any('GSTIN' in issue['field'] for issue in checks(invoice))


def test_missing_company_gstin_is_reviewable_and_not_called_unregistered(tmp_path):
    from Common_Rules.workflow_validation import require_plan,WorkflowReviewRequired,cannot_override
    row=source_row(tmp_path);folder,plan,voucher=output(tmp_path,row)
    transport,writes,reads=server()
    def without_gstin(payload):
        value=transport(payload)
        if 'BillSyncWorkflowCompany' in payload.decode():
            import re
            value=re.sub(rb'<GSTIN>.*?</GSTIN>',b'',value)
        return value
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',without_gstin)
    issue=next(i for i in caught.value.issues if i['field']=='Destination GSTIN')
    assert 'does not mean it is unregistered' in issue['reason']
    assert not cannot_override(issue) and not writes

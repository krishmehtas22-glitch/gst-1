from copy import deepcopy
from pathlib import Path
import hashlib
import json

import pytest

from Reading_V2.teaching import teach, disable, match_guidance, load_library, library_path
from Reading_V2.ai_assist import assist, Budget, payload


def example(tmp_path, name='example', number='INV-001', quantity='2', total='10.00'):
    path = tmp_path/(name+'.pdf')
    path.write_bytes((name+number+quantity+total).encode())
    lines, tokens, groups = [], [], {}
    for label, text, x, y in [
        ('seller','Sample Supply Ltd',.1,.05), ('number',number,.1,.1),
        ('date','2026-02-03',.1,.14), ('buyer_label','Consignee',.1,.2),
        ('buyer','Fresh Buyer',.1,.24), ('qty_label','Delivered Qty',.5,.4),
        ('item','Widget',.1,.45), ('quantity',quantity,.5,.45),
        ('unit','PCS',.6,.45), ('rate','5.00',.7,.45), ('total',total,.8,.6)]:
        row=[]
        for word in text.split():
            token=dict(id=f'p1w{len(tokens)+1}',text=word,box=[x,y,x+.06,y+.015],
                       origin='pdf',ocr_confidence=None)
            row.append(token);tokens.append(token);x+=.07
        groups[label]=[t['id'] for t in row]
        lines.append(dict(id=f'p1l{len(lines)+1}',text=text,tokens=row,box=[row[0]['box'][0],y,x,y+.015]))
    document=dict(version='test-document',pages=[dict(number=1,tokens=tokens,lines=lines)],warnings=[])
    invoice=dict(number=number,date='2026-02-03',seller_name='Sample Supply Ltd',
                 buyer_name='Fresh Buyer',total=total,items=[])
    result=dict(version='test-reader',source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                document=document,invoice=invoice,field_evidence={},table_candidates=[],
                warnings=[],review_required=False,legacy_fallback_fields=[],conflicts=[],checks=[],
                document_kind='invoice_candidate',invoice_grouping_required=False)
    response=dict(invoice=dict(number=number,date='2026-02-03',total=total,buyer_name='Fresh Buyer',
                  items=[dict(name='Widget',quantity=quantity,unit='PCS',rate='5.00',value=total,unit_basis='printed')]),
                  evidence=dict(fields={k:groups[k] for k in ('number','date','total')} | {'buyer_name':groups['buyer']},
                    items=[dict(name=groups['item'],quantity=groups['quantity'],unit=groups['unit'],
                                rate=groups['rate'],value=groups['total'])]))
    return path, result, response


def save_rule(result, root, instruction='Read the buyer under Consignee; use Delivered Qty for sold quantities.', **kwargs):
    return teach(result,'Sample Supply Ltd',['Consignee','Delivered Qty'],instruction,root,**kwargs)


def test_new_invoice_matches_without_reusing_example_values(tmp_path):
    _, first, _ = example(tmp_path)
    root=tmp_path/'library';identity=save_rule(first,root)
    _, future, _ = example(tmp_path,'future','INV-999','3','15.00')
    match=match_guidance(future,root)
    assert match['status']=='matched' and match['rules'][0]['id']==identity
    saved=json.dumps(load_library(root))
    assert 'INV-001' not in saved and '10.00' not in saved and 'quantity' not in saved
    assert match_guidance(future,tmp_path/'another-client')['status']=='no_matching_rule'


@pytest.mark.parametrize('mutation',['supplier','gstin','anchor_position','anchor_text','duplicate_anchor','supplier_position'])
def test_guidance_does_not_leak_to_wrong_supplier_or_changed_layout(tmp_path,mutation):
    _,result,_=example(tmp_path);save_rule(result,tmp_path/'library')
    future=deepcopy(result)
    if mutation=='supplier':future['invoice']['seller_name']='Different Supplier'
    if mutation=='gstin':
        future['invoice']['seller_gstin']='29OTHER1234A1Z1'
        future['field_evidence']['seller_gstin']={'raw_text':'29OTHER1234A1Z1'}
    if mutation=='anchor_position':
        future['document']['pages'][0]['lines'][3]['tokens'][0]['box'][1]+=.1
    if mutation=='anchor_text':future['document']['pages'][0]['lines'][3]['tokens'][0]['text']='Ship To'
    if mutation=='duplicate_anchor':
        future['document']['pages'][0]['lines'].append(deepcopy(future['document']['pages'][0]['lines'][3]))
    if mutation=='supplier_position':future['document']['pages'][0]['lines'][0]['tokens'][0]['box'][0]+=.1
    answer=match_guidance(future,tmp_path/'library')
    assert answer['status']!='matched' and answer['rules']==[]


def test_conflicting_rules_require_explicit_replacement(tmp_path):
    _,result,_=example(tmp_path);root=tmp_path/'library'
    first=save_rule(result,root)
    second=save_rule(result,root,'Check the Delivered Qty heading for this supplier.')
    assert match_guidance(result,root)['status']=='ambiguous_rules'
    disable(second,root)
    replacement=save_rule(result,root,'Use Consignee as a buyer hint, verify its role.',replace=first)
    assert match_guidance(result,root)['rules'][0]['id']==replacement
    assert not next(r for r in load_library(root)['rules'] if r['id']==first)['enabled']


def test_teaching_rejects_unverified_supplier_or_missing_anchor(tmp_path):
    _,result,_=example(tmp_path);root=tmp_path/'library'
    with pytest.raises(ValueError):teach(result,'Other',['Consignee','Delivered Qty'],'Use headings',root)
    with pytest.raises(ValueError):teach(result,'Sample Supply Ltd',['Consignee','Missing'],'Use headings',root)
    assert not library_path(root).exists()


def test_corrupt_library_and_busy_lock_are_preserved(tmp_path):
    _,result,_=example(tmp_path);root=tmp_path/'library';save_rule(result,root)
    path=library_path(root);original=path.read_bytes();lock=path.with_suffix('.lock');lock.write_text('busy')
    with pytest.raises(ValueError,match='lock'):save_rule(result,root)
    assert path.read_bytes()==original and lock.exists()
    lock.unlink();saved=json.loads(original);saved['rules'][0]['instruction']='tampered';path.write_text(json.dumps(saved))
    with pytest.raises(ValueError):match_guidance(result,root)


def test_prompt_applies_hint_to_both_providers_without_relaxing_source_checks(tmp_path):
    _,result,_=example(tmp_path);root=tmp_path/'library';save_rule(result,root)
    result['reading_guidance']=match_guidance(result,root)
    for provider in ('Groq','Gemini'):
        request=payload(result,provider,'test-model')
        text=json.dumps(request)
        assert 'Read the buyer under Consignee' in text
        assert 'They cannot override' in text and 'source-token-id' in text


def test_cached_success_stays_terminal_after_rule_is_changed(tmp_path):
    path,result,response=example(tmp_path);root=tmp_path/'library';first=save_rule(result,root)
    result['reading_guidance']=match_guidance(result,root)
    answer=assist(path,result,tmp_path/'cache',Budget(1),model='test-model',transport=lambda *args:deepcopy(response))
    assert answer['result']['reading_guidance_usage']=={'status':'used_for_new_request','rule_ids':[first]}
    save_rule(result,root,'Use the same two printed headings carefully.',replace=first)
    result['reading_guidance']=match_guidance(result,root)
    cached=assist(path,result,tmp_path/'cache',Budget(0),model='test-model',transport=lambda *args:pytest.fail('unnecessary request'))
    assert cached['status']=='cached' and cached['result']['reading_guidance_usage']=={
        'status':'cached_success_retained','rule_ids':[first]}


def test_new_pipeline_read_uses_guidance_even_if_local_checks_pass(tmp_path,monkeypatch):
    from Reading_V2 import pipeline
    _,first,_=example(tmp_path);root=tmp_path/'library';save_rule(first,root)
    path,future,response=example(tmp_path,'future','INV-999','3','15.00')
    monkeypatch.setattr(pipeline,'read_invoice',lambda path:deepcopy(future))
    calls=[]
    def request(payload,*args):
        calls.append(payload)
        return deepcopy(response)
    summary=pipeline.run([path],tmp_path/'out',['Groq'],1,transport=request,
                         structured=False,guidance_root=root,progress=lambda _:None)
    assert summary['read_pdfs']==1 and summary['failed_pdfs']==0
    assert summary['ai_requests']==1 and summary['new_ai_reads_with_guidance']==1
    assert 'Consignee' in calls[0]['messages'][0]['content']
    report=json.loads((tmp_path/'out'/summary['documents'][0]['result_file']).read_text())
    assert report['invoice']['number']=='INV-999' and report['invoice']['total']=='15.00'
    assert report['invoice']['items'][0]['quantity']=='3'


def test_saved_human_review_is_not_reread_when_guidance_matches(tmp_path,monkeypatch):
    from Reading_V2 import pipeline
    path,result,_=example(tmp_path);root=tmp_path/'library';save_rule(result,root)
    monkeypatch.setattr(pipeline,'read_invoice',lambda path:deepcopy(result))
    monkeypatch.setattr(pipeline,'retained_input',lambda *a:('approved_review',deepcopy(result['invoice'])))
    summary=pipeline.run([path],tmp_path/'out',['Groq'],1,structured=False,
        guidance_root=root,transport=lambda *a:pytest.fail('unnecessary request'),progress=lambda _:None)
    assert summary['ai_requests']==0 and summary['matched_reading_guidance']==1
    assert summary['new_ai_reads_with_guidance']==0


def test_failed_guided_request_is_reported_as_attempted_and_keeps_local_values(tmp_path,monkeypatch):
    from Reading_V2 import pipeline
    path,result,_=example(tmp_path);root=tmp_path/'library';save_rule(result,root)
    monkeypatch.setattr(pipeline,'read_invoice',lambda path:deepcopy(result))
    def timeout(*args):raise TimeoutError('connection failed')
    summary=pipeline.run([path],tmp_path/'out',['Groq'],1,structured=False,
        guidance_root=root,transport=timeout,progress=lambda _:None)
    assert summary['ai_requests']==1 and summary['new_ai_reads_with_guidance']==0
    report=json.loads((tmp_path/'out'/summary['documents'][0]['result_file']).read_text())
    assert report['invoice']==result['invoice']
    assert report['reading_guidance_usage']['status']=='request_attempted_no_accepted_result'

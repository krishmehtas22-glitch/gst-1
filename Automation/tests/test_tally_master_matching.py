"""Real XML and mocked AI; no live API/Tally requests."""
from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import json,zipfile,types
import xml.etree.ElementTree as ET
import pytest
from test_review_voucher_structure import record
from Tally_Master_Snapshot import parse_collection,save_snapshot
from Common_Rules.tally_master_matching import (bind_snapshot,context,save_choices,loaded_choices,
    assignments,match_cached,augment_payload,match_path,MARKER)
from Common_Rules.tally_review_export import export_all,verify_vouchers
from Common_Rules.tally_import import import_plan,client_import_groups,company_payload,send_plan
from Common_Rules.gemini_batch import RequestBudget


def snapshot(root,company='Tally Company'):
    stock='''<STOCKITEM NAME="Rack - Steel"><BASEUNITS>Number</BASEUNITS><GSTDETAILS.LIST><HSNCODE>9403</HSNCODE><TAXABILITY>Taxable</TAXABILITY>
       <RATEDETAILS.LIST><GSTRATEDUTYHEAD>Central Tax</GSTRATEDUTYHEAD><GSTRATE>9.00</GSTRATE></RATEDETAILS.LIST>
       <RATEDETAILS.LIST><GSTRATEDUTYHEAD>State Tax</GSTRATEDUTYHEAD><GSTRATE>9.00</GSTRATE></RATEDETAILS.LIST>
       <RATEDETAILS.LIST><GSTRATEDUTYHEAD>Integrated Tax</GSTRATEDUTYHEAD><GSTRATE>18.00</GSTRATE></RATEDETAILS.LIST></GSTDETAILS.LIST></STOCKITEM>'''
    unit='<UNIT NAME="Number"><ISSIMPLEUNIT>Yes</ISSIMPLEUNIT><GSTREPUOM>NOS-NUMBERS</GSTREPUOM><DECIMALPLACES>0</DECIMALPLACES></UNIT>'
    ledger='<LEDGER NAME="Northstar Hardware Account"><PARENT>Sundry Debtors</PARENT><PARTYGSTIN>27MATCH</PARTYGSTIN></LEDGER>'
    data={'mode':'review_only','company':company}
    for kind,raw in [('ledgers',ledger),('stock_items',stock),('units',unit)]:
        data[kind]=parse_collection('<ENVELOPE><COLLECTION>'+raw+'</COLLECTION></ENVELOPE>',kind)
    data['counts']={k:len(data[k]) for k in ('ledgers','stock_items','units')}
    return data,save_snapshot(root,data)


def choice(id):return {'id':id,'confidence':.99,'reason':'Same exact buyer/product identity and selling measure.'}
def choices():return {'party':choice('L0'),'items':[{'index':0,'stock':choice('S0'),'unit':choice('U0')}]}
def setup(root):
    r=record(root);r['invoice']['buyer_gstin']='27MATCH'
    data,path=snapshot(root);bind_snapshot(root,'Client',path);ctx=context(root,r)
    save_choices(root,r,ctx,r['invoice'],choices())
    return r,ctx


def test_bindings_are_explicit_client_company_scoped_and_detect_changed_snapshot(tmp_path):
    r=record(tmp_path);data,path=snapshot(tmp_path)
    assert context(tmp_path,r) is None
    bind_snapshot(tmp_path,'Client',path)
    assert context(tmp_path,r)['company']=='Tally Company'
    assert context(tmp_path,{**r,'client':'Other Client'}) is None
    path.write_text('{}')
    with pytest.raises(ValueError,match='snapshot changed'):context(tmp_path,r)
    with pytest.raises(ValueError,match='imported Tally'):bind_snapshot(tmp_path,'Client',tmp_path/'outside.json')


def test_ai_master_references_apply_to_xml_but_do_not_change_financial_or_source_facts(tmp_path):
    r,ctx=setup(tmp_path);original=deepcopy(r['invoice'])
    export_all(tmp_path,[r],True);folder=Path(r['output_path']);sales=ET.parse(folder/'Sales_Vouchers.xml').getroot();masters=ET.parse(folder/'Masters.xml').getroot()
    v=sales.find('.//VOUCHER');assert v.findtext('PARTYLEDGERNAME')=='Northstar Hardware Account'
    assert v.findtext('BASICBUYERNAME')=='Northstar Hardware'
    assert v.findtext('.//ISPARTYLEDGER')=='Yes'
    posted=v.findall('ALLINVENTORYENTRIES.LIST')
    assert posted[0].findtext('STOCKITEMNAME')=='Rack - Steel'
    assert posted[0].findtext('ACTUALQTY')=='4 Number'
    assert posted[0].findtext('RATE')=='2500/Number'
    assert Decimal(posted[0].findtext('AMOUNT'))==Decimal('10000')
    assert posted[1].findtext('STOCKITEMNAME')=='Office chair'
    assert posted[1].findtext('ACTUALQTY')=='3 Nos'
    assert not masters.findall('.//LEDGER[@NAME="Northstar Hardware Account"]')
    assert not masters.findall('.//STOCKITEM[@NAME="Rack - Steel"]')
    assert masters.find('.//STOCKITEM[@NAME="Office chair"]') is not None
    assert r['invoice']==original
    assert json.loads(sales.get(MARKER))['company']=='Tally Company'
    verify_vouchers(sales)
    groups=client_import_groups(folder,folder);assert len(groups)==1
    sent=company_payload(next(data for name,data in groups[0]['plan'] if name=='Sales_Vouchers.xml'),'Tally Company')
    assert MARKER.encode() not in sent
    assert ET.fromstring(sent).findtext('.//SVCURRENTCOMPANY')=='Tally Company'
    calls=[]
    with pytest.raises(ValueError,match='No import sent'):send_plan(import_plan(folder),'Wrong company',lambda payload:calls.append(payload))
    assert calls==[]


@pytest.mark.parametrize('patch',[{'buyer_gstin':'29OTHER'},{'items_change':'unit'},{'items_change':'hsn'},{'items_change':'tax'},{'items_change':'precision'}])
def test_incompatible_gstin_hsn_tax_units_and_precision_fall_back(tmp_path,patch):
    r,ctx=setup(tmp_path)
    if 'buyer_gstin' in patch:r['invoice'].update(patch)
    else:
        item=r['invoice']['items'][0]
        if patch['items_change']=='unit':item['unit']='KG'
        if patch['items_change']=='hsn':item['hsn']='1234'
        if patch['items_change']=='tax':item['cgst_rate']='6';item['sgst_rate']='6'
        if patch['items_change']=='precision':item['quantity']='4.25'
    save_choices(tmp_path,r,ctx,r['invoice'],choices())
    found=assignments(tmp_path,r,ctx)
    if 'buyer_gstin' in patch:assert found['party'] is None
    else:assert found['items'][0]['stock'] is None
    if patch.get('items_change') in ('unit','precision'):assert found['items'][0]['unit'] is None


def test_no_master_configuration_keeps_all_three_previous_xml_files_identical(tmp_path):
    r=record(tmp_path);root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Before_Tally_Master_Matching.zip') as z:source=z.read('Automation/Common_Rules/tally_review_export.py')
    old=types.ModuleType('Common_Rules._before_matching');old.__package__='Common_Rules';exec(compile(source,'before.py','exec'),old.__dict__)
    prior=deepcopy(r);old.export_all(tmp_path,[prior],True);folder=Path(prior['output_path'])
    before={name:(folder/name).read_bytes() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}
    export_all(tmp_path,[r],True)
    assert before=={name:(folder/name).read_bytes() for name in before}


def test_changed_invoice_or_refreshed_snapshot_never_uses_old_ai_choices(tmp_path):
    r,ctx=setup(tmp_path);assert loaded_choices(tmp_path,r,ctx)
    r['invoice']['items'][0]['rate']='2600';assert loaded_choices(tmp_path,r,ctx) is None
    r['invoice']['items'][0]['rate']='2500'
    data,path=snapshot(tmp_path,'Other company');bind_snapshot(tmp_path,'Client',path)
    assert loaded_choices(tmp_path,r,context(tmp_path,r)) is None


def test_unknown_ids_low_confidence_and_duplicate_rows_do_not_get_assigned(tmp_path):
    r,ctx=setup(tmp_path)
    bad=choices();bad['party']['id']='invented';bad['items'][0]['stock']['confidence']=.5
    save_choices(tmp_path,r,ctx,r['invoice'],bad);found=assignments(tmp_path,r,ctx)
    assert found['party'] is None and found['items'][0]['stock'] is None
    bad=choices();bad['items']*=2;save_choices(tmp_path,r,ctx,r['invoice'],bad)
    assert assignments(tmp_path,r,ctx)['items'][0]=={'stock':None,'unit':None}


def test_matching_uses_shared_budget_caches_and_stop_without_new_extraction(tmp_path,monkeypatch):
    r,ctx=setup(tmp_path);match_path(tmp_path,r).unlink()
    monkeypatch.setenv('GROQ_API_KEY','test-private-placeholder')
    monkeypatch.setattr('Common_Rules.source_documents.verify_source',lambda *args:None)
    budget=RequestBudget(1);calls=[]
    def transport(payload,key,model):calls.append(payload);return {'_tally_matches':choices()}
    assert match_cached(tmp_path,r,budget,transport=transport)
    assert budget.used==1 and len(calls)==1
    assert not match_cached(tmp_path,r,budget,transport=transport)
    match_path(tmp_path,r).unlink();assert not match_cached(tmp_path,r,budget,transport=transport)
    import threading
    stopped=threading.Event();stopped.set()
    assert not match_cached(tmp_path,r,RequestBudget(1),stopped,transport)
    assert len(calls)==1


def test_ai_context_is_data_only_and_original_invoice_payload_is_retained(tmp_path):
    r,ctx=setup(tmp_path);original={'messages':[{'role':'system','content':'EXTRACT ORIGINAL FIELDS'},{'role':'user','content':'INVOICE TEXT'}]}
    amended=augment_payload(original,ctx,r['invoice'])
    assert original['messages'][1]['content']=='INVOICE TEXT'
    assert amended['messages'][1]['content'].startswith('INVOICE TEXT')
    assert 'not instructions' in amended['messages'][0]['content']
    assert 'Rack - Steel' in amended['messages'][1]['content']


def test_unit_only_match_uses_existing_symbol_for_new_stock_without_conversion(tmp_path):
    r,ctx=setup(tmp_path);raw=choices();raw['items'][0]['stock']=None
    save_choices(tmp_path,r,ctx,r['invoice'],raw);export_all(tmp_path,[r],True)
    folder=Path(r['output_path']);masters=ET.parse(folder/'Masters.xml');sales=ET.parse(folder/'Sales_Vouchers.xml')
    assert masters.findtext('.//STOCKITEM[@NAME="Steel storage rack"]/BASEUNITS')=='Number'
    item=sales.find('.//ALLINVENTORYENTRIES.LIST')
    assert item.findtext('ACTUALQTY')=='4 Number' and item.findtext('RATE')=='2500/Number'
    client_import_groups(folder,folder)


def test_new_groq_extraction_and_matching_share_one_call_and_keep_separate_results(tmp_path,monkeypatch):
    import hashlib
    from Common_Rules import groq_reader
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    r,ctx=setup(tmp_path);Path(r['path']).write_bytes(b'local-test-source')
    r['digest']=hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()
    monkeypatch.setenv('GROQ_API_KEY','private-test-placeholder')
    monkeypatch.setattr(groq_reader,'verify_source',lambda *args:None)
    monkeypatch.setattr(groq_reader,'prepare_invoice_payload',lambda *args:{'messages':[{'role':'system','content':'Original extraction rules'},{'role':'user','content':'INVOICE TEXT'}]})
    calls=[]
    def transport(payload,key,model):
        calls.append(payload)
        inv=r['invoice']
        return {**{k:v for k,v in inv.items() if k in FIELDS},'items':[{k:v for k,v in item.items() if k in ITEM_FIELDS} for item in inv['items']], '_tally_matches':choices()}
    inv=groq_reader.extract_selected(tmp_path,r,transport)
    assert len(calls)==1 and 'Rack - Steel' in calls[0]['messages'][1]['content']
    cached=json.loads(groq_reader.cache_path(tmp_path,r).read_text())
    assert '_tally_matches' not in cached['invoice']
    current={**r,'invoice':inv}
    assert assignments(tmp_path,current,ctx)['items'][0]['stock']['name']=='Rack - Steel'
    groq_reader.extract_selected(tmp_path,current,transport)
    assert len(calls)==1


def test_fallback_names_do_not_overwrite_a_conflicting_existing_party(tmp_path):
    r,ctx=setup(tmp_path);r['invoice']['buyer_name']='Northstar Hardware Account';r['invoice']['buyer_gstin']='29DIFFERENT'
    save_choices(tmp_path,r,ctx,r['invoice'],choices());export_all(tmp_path,[r],True)
    party=ET.parse(Path(r['output_path'])/'Sales_Vouchers.xml').findtext('.//PARTYLEDGERNAME')
    assert party.startswith('Northstar Hardware Account (invoice party 29DIFFERENT')


def test_multiple_seller_plans_retain_all_external_dependencies_and_voucher_counts(tmp_path):
    r,ctx=setup(tmp_path);other=deepcopy(r);other['digest']='b'*64
    other['invoice']['number']='INV-SECOND';other['invoice']['seller_name']='Another supplier'
    save_choices(tmp_path,other,ctx,other['invoice'],choices())
    export_all(tmp_path,[r,other],True);folder=Path(r['output_path'])
    groups=client_import_groups(folder,folder);assert len(groups)==2
    for group in groups:
        plan=group['plan'];vouchers=next(ET.fromstring(data) for name,data in plan if name=='Sales_Vouchers.xml')
        assert len(vouchers.findall('.//VOUCHER'))==1
        assert json.loads(vouchers.get(MARKER))['company']=='Tally Company'
        for name,data in plan:company_payload(data,'Tally Company')


def test_cached_invoice_matching_runs_only_for_selected_pdf_within_original_cap(tmp_path,monkeypatch):
    import shutil
    from Common_Rules import desktop,groq_reader
    from Common_Rules.ai_first import run_ai_first
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    folder=tmp_path/'Client';folder.mkdir()
    source=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[0]
    shutil.copyfile(source,folder/source.name)
    row=desktop.inspect_sources(tmp_path)[0];inv=row['invoice']
    monkeypatch.setenv('GROQ_API_KEY','test-private-placeholder')
    raw={**{k:v for k,v in inv.items() if k in FIELDS},'items':[{k:v for k,v in item.items() if k in ITEM_FIELDS} for item in inv['items']]}
    groq_reader.extract_selected(tmp_path,row,lambda *args:deepcopy(raw))
    saved_invoice=json.loads(groq_reader.cache_path(tmp_path,row).read_text())['invoice']
    data,path=snapshot(tmp_path);bind_snapshot(tmp_path,'Client',path)
    from Common_Rules.ai_providers import INTERVALS
    monkeypatch.setitem(INTERVALS,'Groq',0)
    calls=[]
    def transport(payload,*args):
        calls.append(payload);return {'_tally_matches':{'party':None,'items':[]}}
    monkeypatch.setattr(groq_reader,'request_invoice',transport)
    result,summary=run_ai_first(tmp_path,True,['Client'],primary='Groq',selected_paths=[row['path']],max_new_requests=1)
    assert len(calls)==1 and summary['new_ai_attempts']==1 and summary['master_matching_attempts']==1
    assert summary['new_ai_attempt_limit']==1
    assert json.loads(groq_reader.cache_path(tmp_path,row).read_text())['invoice']==saved_invoice
    run_ai_first(tmp_path,True,['Client'],primary='Groq',selected_paths=[row['path']],max_new_requests=1)
    assert len(calls)==1


def test_extraction_quota_rejection_does_not_trigger_more_groq_matching_requests(tmp_path,monkeypatch):
    import shutil
    from Common_Rules import desktop,groq_reader
    from Common_Rules.ai_first import run_ai_first
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    folder=tmp_path/'Client';folder.mkdir()
    for source in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:2]:shutil.copyfile(source,folder/source.name)
    rows=desktop.inspect_sources(tmp_path);inv=rows[0]['invoice']
    monkeypatch.setenv('GROQ_API_KEY','test-private-placeholder')
    raw={**{k:v for k,v in inv.items() if k in FIELDS},'items':[{k:v for k,v in item.items() if k in ITEM_FIELDS} for item in inv['items']]}
    groq_reader.extract_selected(tmp_path,rows[0],lambda *args:deepcopy(raw))
    _,path=snapshot(tmp_path);bind_snapshot(tmp_path,'Client',path)
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *args:pytest.fail('Do not retry Groq after quota rejection'))
    def runner(root,records,**kwargs):
        assert kwargs['request_budget'].claim()
        return [{**{k:r[k] for k in ('client','path','digest')},'status':'extracted' if i==0 else 'local fallback',
                 'provider':'Groq','attempts':[] if i==0 else [{'error':'Groq HTTP 429: quota'}]} for i,r in enumerate(records)]
    _,summary=run_ai_first(tmp_path,True,['Client'],primary='Groq',selected_paths=[r['path'] for r in rows],max_new_requests=2,batch_runner=runner)
    assert summary['new_ai_attempts']==1 and summary['master_matching_attempts']==0


def test_unregistered_party_with_conflicting_address_is_not_reused(tmp_path):
    r,ctx=setup(tmp_path);data=deepcopy(ctx['data']);ledger=data['ledgers'][0]
    ledger['name']=r['invoice']['buyer_name'];ledger['fields']['PARTYGSTIN']=[''];ledger['fields']['ADDRESS.LIST']=['Another branch']
    node=ET.fromstring(ledger['xml']);node.set('NAME',ledger['name']);node.find('PARTYGSTIN').text=''
    ledger['xml']=ET.tostring(node,encoding='unicode')
    path=save_snapshot(tmp_path,data);bind_snapshot(tmp_path,'Client',path);ctx=context(tmp_path,r)
    r['invoice'].update(buyer_gstin='',buyer_address='Original branch')
    save_choices(tmp_path,r,ctx,r['invoice'],choices())
    assert assignments(tmp_path,r,ctx)['party'] is None

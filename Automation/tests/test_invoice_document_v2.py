"""New nested contract -> cached domain -> human review -> real XML, no live calls."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import xml.etree.ElementTree as ET
import pytest
from Common_Rules import invoice_document as domain
from Common_Rules import groq_reader,ollama_reader
from Common_Rules.desktop import inspect_sources,save_review
from Common_Rules.tally_review_export import export_all
from Common_Rules.foreign_currency import for_record
from Common_Rules.workflow_validation import checks
from test_ai_workflow_validation import source_row,server,output,SELLER,BUYER


def response(row):
    doc=domain.from_legacy(row['invoice'],row)
    inv=doc['invoice'];inv.update(document_type='tax_invoice',invoice_date_raw='02/10/2026',invoice_date_iso='2026-10-02')
    inv['other_charges']=[];inv['ship_to']={'name':'Separate delivery recipient'}
    inv['evidence']=[{'field':'invoice_number','quote':'Invoice No: '+inv['invoice_number'],'page':1}]
    return {'schema_version':2,'invoices':[inv]}


def attach(row,answer):
    document=domain.from_model(answer,row,'Invoice No: '+row['invoice']['number'])
    row['invoice']=domain.to_legacy(document,row['invoice']);row['document']=document
    return row


def test_nested_shape_preserves_exact_money_quantity_and_roles(tmp_path):
    row=source_row(tmp_path);answer=response(row);item=answer['invoices'][0]['items'][0]
    item.update(quantity='2.4877',unit='KG',rate='100',taxable_value='248.77')
    normalized=domain.normalize_document_result(answer,row,'Groq','Invoice No: '+row['invoice']['number'])
    document=normalized['_document_v2']
    assert document['schema_version']==2 and document['invoice']['seller']['gstin']==SELLER
    assert document['invoice']['buyer']['gstin']==BUYER
    assert document['invoice']['ship_to']['name']=='Separate delivery recipient'
    assert normalized['items'][0]['quantity']=='2.4877' and normalized['items'][0]['rate']=='100'
    assert document['field_status']['invoice_number']['status']=='source_observed'
    assert document['field_status']['buyer.gstin']['status']=='unverified'


def test_quotes_for_other_values_are_uncertain_not_verified(tmp_path):
    row=source_row(tmp_path);answer=response(row);answer['invoices'][0]['invoice_number']='WRONG'
    doc=domain.from_model(answer,row,'Invoice No: '+row['invoice']['number'])
    assert doc['field_status']['invoice_number']['status']=='uncertain'
    assert any(p['code']=='evidence_unverified' for p in domain.findings(doc))


@pytest.mark.parametrize('change',[
    lambda a:a.update(schema_version=3),
    lambda a:a.update(invoices=[]),
    lambda a:a['invoices'].append(deepcopy(a['invoices'][0])),
    lambda a:a['invoices'][0].update(invented='value'),
    lambda a:a['invoices'][0]['items'][0].update(quantity=2.4877),
    lambda a:a['invoices'][0].update(seller={'gstin':{'wrong':'type'}}),
])
def test_invalid_structure_never_drops_invoice_or_accepts_numeric_floats(tmp_path,change):
    row=source_row(tmp_path);answer=response(row);change(answer)
    with pytest.raises(ValueError):domain.from_model(answer,row)


def test_cache_uses_nested_document_and_detects_mismatch(tmp_path):
    row=source_row(tmp_path);inv=domain.normalize_document_result(response(row),row,'Groq')
    saved=domain.cache_fields(inv)
    assert saved['document']['invoice']['invoice_number']==row['invoice']['number']
    assert domain.cached_invoice(saved,row)['total']==row['invoice']['total']
    corrupt=deepcopy(saved);corrupt['document']['invoice']['totals']['grand_total']='1'
    with pytest.raises(ValueError,match='document changed'):domain.cached_invoice(corrupt,row)
    corrupt=deepcopy(saved);corrupt['invoice']['total']='1'
    with pytest.raises(ValueError,match='projection changed'):domain.cached_invoice(corrupt,row)


@pytest.mark.parametrize('reader',[groq_reader,ollama_reader])
def test_explicit_provider_uses_new_contract_and_retains_cache_without_new_call(tmp_path,monkeypatch,reader):
    row=source_row(tmp_path);monkeypatch.setenv('GROQ_API_KEY','private-test-key');calls=[]
    monkeypatch.setattr('Common_Rules.extraction.text_from_pdf',lambda _: 'Invoice No: '+row['invoice']['number'])
    def transport(payload,*args):
        assert 'schema_version' in payload['messages'][0]['content']
        assert 'invoices' in payload['messages'][0]['content']
        assert 'Ship To' in payload['messages'][0]['content']
        calls.append(payload);return response(row)
    result=reader.extract_selected(tmp_path,row,transport)
    saved=json.loads(reader.cache_path(tmp_path,row).read_text())
    assert saved['document']['schema_version']==2 and result['number']==row['invoice']['number']
    reader.extract_selected(tmp_path,row,lambda *a:pytest.fail('Saved read must not spend a request'))
    assert len(calls)==1


def test_legacy_cache_migrates_locally_without_reanalysis(tmp_path,monkeypatch):
    row=source_row(tmp_path);path=groq_reader.cache_path(tmp_path,row);path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'revision':'groq-text-v1','model':groq_reader.configured_model(),'source_sha256':row['digest'],'invoice':row['invoice']}))
    original=path.read_bytes();result=groq_reader.extract_selected(tmp_path,row,lambda *a:pytest.fail('No paid migration call'))
    assert result['_document_v2']['provenance']['origin']=='legacy_migration'
    assert result['total']==row['invoice']['total'] and path.read_bytes()==original


def test_nested_export_has_source_number_date_and_stock_movements(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv.update(supply='EXPORT',classification='export_lut',place_of_supply='Outside India')
    inv['buyer'].update(country='United Kingdom',gstin='',state='')
    inv['export']={'country':'United Kingdom','mode':'LUT_without_payment'}
    inv['totals'].update(cgst_total='0',sgst_total='0',igst_total='0',grand_total='22000')
    for item in inv['items']:item.update(cgst_rate='0',sgst_rate='0',igst_rate='0')
    attach(row,answer);folder,plan,voucher=output(tmp_path,row)
    assert voucher.findtext('VOUCHERNUMBER')==row['invoice']['number']
    assert voucher.findtext('DATE')=='20261002'
    assert len(voucher.findall('ALLINVENTORYENTRIES.LIST'))==2
    assert voucher.findtext('COUNTRYOFRESIDENCE')=='United Kingdom'


def test_supported_charge_ledger_preserves_stock_and_balances_without_plug(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv['other_charges']=[{'label':'Freight','kind':'freight','amount':'100','included_in_taxable_total':'yes'}]
    inv['totals'].update(taxable_total='22100',cgst_total='1989',sgst_total='1989',grand_total='26078')
    attach(row,answer);_,_,voucher=output(tmp_path,row)
    assert len(voucher.findall('ALLINVENTORYENTRIES.LIST'))==2
    charges=[n for n in voucher.findall('LEDGERENTRIES.LIST') if n.findtext('LEDGERNAME')=='Freight']
    assert len(charges)==1 and charges[0].findtext('AMOUNT')=='100.00'
    assert not voucher.findall(".//LEDGERNAME[.='Invoice differences - review']")


def test_currency_conversion_includes_charges_once_and_keeps_source(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv.update(currency='USD',exchange_rate='80',exchange_rate_basis='INR_per_foreign',exchange_rate_units='1')
    inv['other_charges']=[{'label':'Insurance','kind':'insurance','amount':'10','included_in_taxable_total':'no'}]
    attach(row,answer);before=deepcopy(row['invoice']);converted=for_record(tmp_path,row)
    assert converted['_other_charges'][0]['amount']=='800.00'
    assert converted['currency_conversion']['original_amounts']['other_charges'][0]['amount']=='10'
    assert row['invoice']==before


@pytest.mark.parametrize('kind',['credit_note','quotation'])
def test_wrong_document_type_never_replaces_previous_xml(tmp_path,kind):
    row=source_row(tmp_path);folder,_,_=output(tmp_path,row);old=(folder/'Sales_Vouchers.xml').read_bytes()
    answer=response(row);answer['invoices'][0]['document_type']=kind;attach(row,answer)
    with pytest.raises(ValueError,match='document type'):export_all(tmp_path,[row],True)
    assert (folder/'Sales_Vouchers.xml').read_bytes()==old


def test_human_correction_preserves_delivery_and_charge_metadata(tmp_path):
    row=source_row(tmp_path);attach(row,response(row));edited=deepcopy(row['invoice'])
    edited['_document_v2']['invoice']['ship_to']['name']='Corrected consignee'
    edited['number']='HUMAN-001'
    save_review(tmp_path,row,edited)
    saved=json.loads((tmp_path/'.invoice_app/reviews'/(row['digest']+'.json')).read_text())
    assert saved['document']['invoice']['ship_to']['name']=='Corrected consignee'
    assert saved['document']['invoice']['invoice_number']=='HUMAN-001'
    assert saved['document']['field_status']['invoice_number']['status']=='human_corrected'
    assert domain.findings(saved['document'])==[]


def test_published_schema_matches_runtime():
    path=Path(__file__).parents[1]/'schemas/invoice-v2.schema.json'
    data=json.loads(path.read_text());data.pop('$schema')
    assert data==domain.EXTRACTION_SCHEMA


def test_discount_is_represented_without_rewriting_source_rate(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    first=inv['items'][0];first.update(discount='10',discount_basis='percent')
    original_value=first['taxable_value'];first['taxable_value']=format(__import__('decimal').Decimal(original_value)*__import__('decimal').Decimal('.9'),'f')
    normalized=domain.normalize_document_result(answer,row,'Groq')
    assert normalized['items'][0]['discount_rate']=='10'
    assert normalized['items'][0]['rate']==row['invoice']['items'][0]['rate']
    assert normalized['_document_v2']['raw_extraction']['items'][0]['discount']=='10'


def test_raw_model_facts_survive_derived_unit_and_human_changes(tmp_path):
    row=source_row(tmp_path);answer=response(row);raw=deepcopy(answer['invoices'][0]);result=domain.normalize_document_result(answer,row,'Groq')
    assert result['_document_v2']['raw_extraction']==raw
    row['invoice']=result;domain.sync_record(row)
    edited=deepcopy(result);edited['number']='REVIEWED'
    reviewed=domain.from_legacy(edited,row,row['document'],human=True)
    assert reviewed['invoice']['invoice_number']=='REVIEWED'
    assert reviewed['raw_extraction']['invoice_number']==raw['invoice_number']


def test_charge_excluded_from_taxable_total_is_posted_once(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv['other_charges']=[{'label':'Additional insurance','kind':'insurance','amount':'100','included_in_taxable_total':'no'}]
    inv['totals']['grand_total']='26060';attach(row,answer)
    _,_,voucher=output(tmp_path,row)
    values=[n for n in voucher.findall('LEDGERENTRIES.LIST') if n.findtext('LEDGERNAME')=='Additional insurance']
    assert len(values)==1 and values[0].findtext('AMOUNT')=='100.00'
    assert not voucher.findall(".//LEDGERNAME[.='Invoice differences - review']")


def test_ambiguous_charge_or_rate_basis_keeps_previous_xml(tmp_path):
    row=source_row(tmp_path);folder,_,_=output(tmp_path,row);original=(folder/'Sales_Vouchers.xml').read_bytes()
    answer=response(row);answer['invoices'][0]['other_charges']=[{'label':'Freight','amount':'100','included_in_taxable_total':None}]
    attach(row,answer)
    with pytest.raises(ValueError,match='included in the taxable'):export_all(tmp_path,[row],True)
    assert (folder/'Sales_Vouchers.xml').read_bytes()==original


def exercise_document_editor(root,app,monkeypatch):
    import tempfile
    from tkinter import ttk
    from BillSync_Theme import descendants
    from Invoice_Document_Editor import open_document_editor
    with tempfile.TemporaryDirectory(prefix='document-v2-ui-') as temp:
        storage=Path(temp);row=source_row(storage);attach(row,response(row));saved=[]
        top=open_document_editor(root,storage,row,lambda r,edited:saved.append(edited));root.update()
        notebooks=[w for w in descendants(top) if isinstance(w,ttk.Notebook)]
        assert len(notebooks)==1 and len(notebooks[0].tabs())==4
        button=next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Save changes to XML')
        assert button.winfo_ismapped() and button.winfo_rooty()+button.winfo_height()<=root.winfo_screenheight()
        button.invoke();root.update()
        assert len(saved)==1 and saved[0]['_document_v2']['invoice']['ship_to']['name']=='Separate delivery recipient'
        assert saved[0]['number']==row['invoice']['number']


def test_ambiguous_decimal_comma_cannot_be_silently_stripped(tmp_path):
    row=source_row(tmp_path);answer=response(row);answer['invoices'][0]['totals']['grand_total']='1,20'
    with pytest.raises(ValueError,match='Ambiguous number'):domain.from_model(answer,row)
    answer['invoices'][0]['totals']['grand_total']='1,00,000.50'
    doc=domain.from_model(answer,row)
    assert doc['invoice']['totals']['grand_total']=='100000.50'
    assert doc['raw_extraction']['totals']['grand_total']=='1,00,000.50'


def exercise_pending_editor_changes(root,app,monkeypatch):
    import tempfile
    from tkinter import ttk
    import Invoice_Desktop
    from BillSync_Theme import descendants
    old_root=app.root;old_busy=app.busy
    with tempfile.TemporaryDirectory(prefix='document-v2-draft-') as temp:
        storage=Path(temp);row=source_row(storage);attach(row,response(row));saved=[]
        monkeypatch.setattr(app,'selected',lambda:row)
        monkeypatch.setattr(app,'save_manual_edits',lambda r,edited:saved.append((r,edited)))
        app.root=storage;app.busy=False
        try:
            Invoice_Desktop.InvoiceApp.review(app);root.update()
            old=next(w for w in root.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Review invoice against the original PDF')
            number=next(w for w in descendants(old) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox) and w.get()==row['invoice']['number'])
            number.delete(0,'end');number.insert(0,'PENDING-0042')
            next(w for w in descendants(old) if isinstance(w,ttk.Button) and w.cget('text')=='Details & evidence').invoke();root.update()
            top=next(w for w in root.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Invoice details and source evidence')
            assert not saved and not old.winfo_exists()
            next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Save changes to XML').invoke();root.update()
            assert len(saved)==1 and saved[0][0] is row
            assert saved[0][1]['number']=='PENDING-0042'
            assert saved[0][1]['_document_v2']['invoice']['invoice_number']=='PENDING-0042'
        finally:
            for top in list(root.winfo_children()):
                if top.winfo_class()=='Toplevel' and top.title() in ('Invoice details and source evidence','Review invoice against the original PDF'):top.destroy()
            app.root=old_root;app.busy=old_busy


def test_master_references_and_accounting_projection_reach_nested_report(tmp_path):
    from test_ai_workflow_validation import with_masters
    from test_tally_master_matching import choices
    from Common_Rules.tally_master_matching import save_choices
    row,ctx=with_masters(tmp_path);attach(row,response(row))
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    folder,_,voucher=output(tmp_path,row)
    assert voucher.findtext('PARTYLEDGERNAME')=='Northstar Hardware Account'
    assert row['document']['master_assignments']['party']=='Northstar Hardware Account'
    assert row['document']['accounting']['total']==row['invoice']['total']
    metadata=json.loads(ET.parse(folder/'Sales_Vouchers.xml').getroot().get('BILLSYNCREVIEW'))
    assert metadata['entries'][0]['document']['master_assignments']['party']=='Northstar Hardware Account'
    assert metadata['entries'][0]['document']['provenance']['master_snapshot_sha256']==ctx['sha256']


@pytest.mark.parametrize('special',['tcs','reverse_charge','per_100'])
def test_unsupported_special_treatment_never_drops_into_ordinary_sales(tmp_path,special):
    row=source_row(tmp_path);folder,_,_=output(tmp_path,row);original=(folder/'Sales_Vouchers.xml').read_bytes()
    answer=response(row);inv=answer['invoices'][0]
    if special=='tcs':inv['other_charges']=[{'label':'TCS','kind':'tcs','amount':'100','included_in_taxable_total':'no'}]
    elif special=='reverse_charge':inv['reverse_charge']='Yes'
    else:inv['items'][0]['price_basis']='per_100'
    attach(row,answer)
    with pytest.raises(ValueError):export_all(tmp_path,[row],True)
    assert (folder/'Sales_Vouchers.xml').read_bytes()==original


def test_installer_preserves_unknown_structure_module_before_any_writes(tmp_path):
    import runpy,zipfile
    root=Path(__file__).parents[2];package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(root/'Backups/Before_Invoice_Structure_V2.zip') as archive:
        for name in archive.namelist():
            if name.startswith('Automation/') and (name.endswith('.py') or name.removeprefix('Automation/') in package['ENGINE']):
                target=tmp_path/name.removeprefix('Automation/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(name))
    existing=tmp_path/'Common_Rules/invoice_document.py';existing.write_text('# unrelated custom local file\n')
    before=(tmp_path/'Invoice_Desktop.py').read_bytes()
    with pytest.raises(ValueError,match='No files changed'):package['install'](tmp_path)
    assert (tmp_path/'Invoice_Desktop.py').read_bytes()==before
    existing.unlink();backup=package['install'](tmp_path)
    assert (backup/'Invoice_Desktop.py').read_bytes()==before
    assert (tmp_path/'Common_Rules/invoice_document.py').read_bytes()==(root/'Automation/Common_Rules/invoice_document.py').read_bytes()
    package['install'](tmp_path)


def test_tcs_label_cannot_bypass_tax_treatment_by_changing_kind_case(tmp_path):
    row=source_row(tmp_path);answer=response(row);answer['invoices'][0]['other_charges']=[{'label':'TCS collected','kind':'other','amount':'100','included_in_taxable_total':'no'}]
    attach(row,answer)
    with pytest.raises(ValueError,match='TCS'):domain.require_exportable([row])


def test_missing_new_model_quantity_is_not_defaulted_to_one(tmp_path):
    row=source_row(tmp_path);answer=response(row);answer['invoices'][0]['items'][0]['quantity']=None
    result=domain.normalize_document_result(answer,row,'Groq')
    assert result['items'][0].get('quantity') in (None,'')
    assert result['_document_v2']['invoice']['items'][0].get('quantity') in (None,'')
    row['invoice']=result;_,_,voucher=output(tmp_path,row)
    assert not voucher.findall('ALLINVENTORYENTRIES.LIST')


def test_candidate_retrieval_uses_full_source_when_local_parser_has_no_items():
    from Common_Rules.tally_master_matching import shortlist,augment_payload,offered_ids
    from Common_Rules.invoice_prompt import prepare
    catalog={}
    for index in range(25):
        catalog['S'+str(index)]={'id':'S'+str(index),'name':'Different item '+str(index),'kind':'stock_items','gstin':''}
    catalog['S24']['name']='Unique archival binding clips'
    ctx={'_catalog':catalog}
    payload=prepare({},'mock','Invoice No: SOURCE-001\nUnique archival binding clips 10 PCS')
    offered=augment_payload(payload,ctx,{})
    assert 'S24' in offered_ids(offered)
    assert offered.source_text==payload.source_text
    assert 'source_text' not in json.loads(json.dumps(offered))


def test_local_overlength_input_is_rejected_before_any_request(monkeypatch):
    from Common_Rules import ollama_reader
    monkeypatch.setattr(ollama_reader,'build_opener',lambda *a:pytest.fail('Oversized input must not be sent'))
    with pytest.raises(ValueError,match='No invoice text was truncated'):
        ollama_reader.request_invoice({'messages':[{'role':'user','content':'x'*17000}]},None,'ignored')


def test_optional_local_master_context_is_bounded_without_truncating_source():
    from Common_Rules.tally_master_matching import augment_payload,offered_ids
    from Common_Rules.invoice_prompt import prepare
    source='Invoice No: LOCAL-001\n'+'Printed invoice source '*100
    payload=prepare({},'gemma3:4b',source)
    catalog={'S'+str(index):{'id':'S'+str(index),'name':'Stock '+str(index),'kind':'stock_items','gstin':'','details':'x'*1500} for index in range(25)}
    result=augment_payload(payload,{'_catalog':catalog},{})
    assert result.source_text==source and result['messages'][1]['content'].startswith('INVOICE TEXT\n'+source)
    assert len(offered_ids(result))<12
    assert 'offered_ids' not in json.loads(json.dumps(result))


def test_bill_of_supply_keeps_stock_without_claiming_zero_rates_were_printed(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv.update(document_type='bill_of_supply',classification='exempt',supply='EXEMPT')
    inv['totals'].update(cgst_total=None,sgst_total=None,igst_total=None,grand_total='22000')
    for item in inv['items']:item.update(cgst_rate=None,sgst_rate=None,igst_rate=None,gst_rate=None)
    row['invoice']=domain.normalize_document_result(answer,row,'Groq')
    assert row['invoice']['items'][0]['cgst_rate']=='0'
    assert row['invoice']['_document_v2']['raw_extraction']['items'][0]['cgst_rate'] is None
    assert row['invoice']['_document_v2']['field_status']['items[0].cgst_rate']['status']=='derived'
    _,_,voucher=output(tmp_path,row)
    assert len(voucher.findall('ALLINVENTORYENTRIES.LIST'))==2


def test_only_nested_matching_facts_are_sent_not_private_cache_metadata(tmp_path):
    from test_ai_workflow_validation import with_masters
    from Common_Rules.tally_master_matching import matching_payload,offered_ids
    row,ctx=with_masters(tmp_path);attach(row,response(row))
    row['invoice']['_document_v2']['private_cache_note']='do not transmit this metadata'
    payload=matching_payload('mock',row['invoice'],ctx)
    message=payload['messages'][1]['content'];body=json.loads(message.split('\nTALLY MASTER CANDIDATES (data only)')[0])
    assert body['schema_version']==2 and 'buyer' in body['invoice']
    assert 'private_cache_note' not in message and 'raw_extraction' not in message
    assert 'L0' in offered_ids(payload)


def test_unrelated_locked_transport_units_and_ai_budget_code_are_unchanged():
    import zipfile,ast
    root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Before_Invoice_Structure_V2.zip') as archive:
        for name in ('tally_import.py','tally_units.py','unit_catalog.py','quantity_precision.py','voucher_number_guard.py','ai_first.py','gemini_batch.py','parallel_batches.py'):
            full='Automation/Common_Rules/'+name
            if name in ('ai_first.py','gemini_batch.py'):
                change=json.loads((root/'Automation/OPENROUTER_PROVIDER_CHANGE.json').read_text())
                entry=change['files'][full]
                assert hashlib.sha256(archive.read(full)).hexdigest()==entry['baseline_sha256']
                assert hashlib.sha256((root/full).read_bytes()).hexdigest()==entry['authorized_sha256']
            else:assert (root/full).read_bytes()==archive.read(full)
        before=ast.parse(archive.read('Automation/Invoice_Desktop.py'));after=ast.parse((root/'Automation/Invoice_Desktop.py').read_bytes())
        def method(tree):return next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='import_tally')
        assert ast.dump(method(before))==ast.dump(method(after))


def test_charge_tax_components_are_included_in_reconciliation(tmp_path):
    row=source_row(tmp_path);answer=response(row);inv=answer['invoices'][0]
    inv['other_charges']=[{'label':'Freight','kind':'freight','amount':'100','included_in_taxable_total':'yes','cgst_rate':'9','sgst_rate':'9','igst_rate':'0'}]
    inv['totals'].update(taxable_total='22100',cgst_total='1989',sgst_total='1989',grand_total='26078')
    attach(row,answer)
    assert not any('reconciliation' in p['field'] for p in checks(row['invoice']))
    row['invoice']['_other_charges'][0]['cgst_rate']='8'
    assert any(p['field']=='CGST reconciliation' for p in checks(row['invoice']))


def test_ambiguous_manual_number_is_rejected_before_review_is_saved(tmp_path):
    row=source_row(tmp_path);attach(row,response(row));edited=deepcopy(row['invoice']);edited['total']='1,20'
    with pytest.raises(ValueError,match='Ambiguous number'):save_review(tmp_path,row,edited)
    assert not (tmp_path/'.invoice_app/reviews'/(row['digest']+'.json')).exists()


def test_fresh_legacy_model_reply_does_not_bypass_numeric_or_missing_qty_checks(tmp_path):
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    row=source_row(tmp_path)
    answer={k:v for k,v in row['invoice'].items() if k in FIELDS}
    answer['items']=[{k:v for k,v in item.items() if k in ITEM_FIELDS} for item in row['invoice']['items']]
    answer['total']='1,20'
    with pytest.raises(ValueError,match='Ambiguous number'):domain.normalize_document_result(answer,row,'Groq')
    answer['total']=row['invoice']['total'];answer['items'][0]['quantity']=None
    result=domain.normalize_document_result(answer,row,'Groq')
    assert result['items'][0].get('quantity') in (None,'')
    assert result['_document_v2']['raw_legacy_response']==answer
    assert any(p['code']=='legacy_response_review' for p in domain.findings(result['_document_v2']))

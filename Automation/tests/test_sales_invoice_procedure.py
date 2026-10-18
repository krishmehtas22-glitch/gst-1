"""Offline sales procedure, RCM inventory XML and source-preserving review."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,os,runpy,zipfile
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.gemini_reader import normalize_invoice_result
from Common_Rules.sales_invoice_procedure import normalize_rcm,reverse_charge,validate_rcm
from Common_Rules.tally_review_export import export_all,verify_vouchers
from Common_Rules.workflow_validation import checks
from test_review_voucher_structure import record


def after_sales_procedure(root,name,expected):
    """Continue historical byte locks through this explicitly backed-up change."""
    change=json.loads((root/'Automation/SALES_INVOICE_PROCEDURE_CHANGE.json').read_text())
    if name in change['files']:
        entry=change['files'][name]
        assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(root/change['backup']) as backup:
            assert hashlib.sha256(backup.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    later=json.loads((root/'Automation/AI_FAILURE_DIAGNOSTICS_CHANGE.json').read_text())
    if name in later['files']:
        entry=later['files'][name];assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(root/later['backup']) as backup:assert hashlib.sha256(backup.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected


def rcm_row(root):
    row=record(root)
    row['invoice'].update(reverse_charge='Yes',document_type='sales_invoice',total='22000',cgst='0',sgst='0',igst='0',cess='0')
    return row


@pytest.mark.parametrize('value',['Yes','YES',' true ','1','y'])
def test_explicit_rcm_derives_only_missing_payable_tax(value):
    inv={'reverse_charge':value,'cgst':'0.00','items':[{'cgst_rate':'9'}]}
    normalize_rcm(inv)
    assert reverse_charge(inv) and inv['cgst']=='0.00' and inv['igst']=='0'
    assert inv['items']==[{'cgst_rate':'9'}] and 'not printed' in inv['rcm_tax_basis']


@pytest.mark.parametrize('value',[None,'','No','False','unknown','RCM possibly'])
def test_zero_gst_or_unclear_rcm_is_never_positive_evidence(value):
    inv={'reverse_charge':value,'cgst':'0'};old=deepcopy(inv)
    normalize_rcm(inv)
    assert not reverse_charge(inv) and inv==old


def test_shared_normalizer_preserves_rcm_nominal_rates_and_printed_conflicts(tmp_path):
    row=rcm_row(tmp_path)
    inv=deepcopy(row['invoice']);inv['cgst']='1980'
    inv['items'][0]['printed_total']='10000'
    parsed=normalize_invoice_result(inv,row,'Mock AI')
    assert parsed['cgst']=='1980' and parsed['reverse_charge']=='Yes'
    assert parsed['items'][0]['cgst_rate']=='9' and parsed['items'][0]['printed_total']=='10000'
    with pytest.raises(ValueError,match='will not be erased'):validate_rcm(parsed)


def test_rcm_inventory_xml_has_zero_supplier_gst_but_retains_rates_and_stock(tmp_path):
    row=rcm_row(tmp_path);old=deepcopy(row['invoice'])
    export_all(tmp_path,[row],False);folder=Path(row['output_path'])
    sales=ET.parse(folder/'Sales_Vouchers.xml');v=sales.find('.//VOUCHER')
    assert len(v.findall('ALLINVENTORYENTRIES.LIST'))==2
    entries=v.findall('LEDGERENTRIES.LIST')
    assert len(entries)==1 and entries[0].findtext('AMOUNT')=='-22000.00'
    assert v.findtext('DATE')=='20261002' and v.findtext('VOUCHERNUMBER')==old['number']
    masters=ET.parse(folder/'Masters.xml')
    for stock in masters.findall('.//STOCKITEM'):
        assert stock.findtext('GSTDETAILS.LIST/ISREVERSECHARGEAPPLICABLE')=='Yes'
        assert stock.findtext('GSTDETAILS.LIST/TAXABILITY')=='Taxable'
        assert stock.findtext('.//GSTRATE')=='9'
    assert 'Reverse-charge sales' in v.findtext('NARRATION')
    assert ET.parse(folder/'Units.xml').findtext('.//UNIT/ORIGINALNAME')!='Nos'
    assert row['invoice']==old
    verify_vouchers(sales.getroot())


def test_buyer_address_remains_separate_from_seller_and_place_of_supply(tmp_path):
    row=record(tmp_path)
    row['invoice'].update(buyer_address='Buyer building\nBuyer city & district',seller_address='Different supplier address',place_of_supply='29')
    export_all(tmp_path,[row],False);folder=Path(row['output_path'])
    v=ET.parse(folder/'Sales_Vouchers.xml').find('.//VOUCHER')
    party=v.findtext('PARTYLEDGERNAME')
    master=next(n for n in ET.parse(folder/'Masters.xml').iter('LEDGER') if n.get('NAME')==party)
    assert [n.text for n in master.findall('ADDRESS.LIST/ADDRESS')]==['Buyer building','Buyer city & district']
    assert v.findtext('BASICBUYERADDRESS.LIST/BASICBUYERADDRESS')==row['invoice']['buyer_address']
    assert v.findtext('PLACEOFSUPPLY')=='Karnataka'


def test_combined_printed_rcm_rate_can_supply_nominal_master_components(tmp_path):
    from Common_Rules.demo import test_gstin as gstin
    row=rcm_row(tmp_path);inv=row['invoice'];inv['seller_gstin']=gstin('27ABCDE1234F1Z')
    for item in inv['items']:
        item['gst_rate']='18'
        for tax in ('cgst','sgst','igst'):item.pop(tax+'_rate')
    parsed=normalize_invoice_result(inv,row,'Mock AI')
    assert parsed['cgst']=='0' and parsed['sgst']=='0'
    assert parsed['items'][0]['cgst_rate']=='9' and parsed['items'][0]['igst_rate']=='0'


@pytest.mark.parametrize('patch',[{'cgst':'1980'},{'igst':'3960'},{'cess':'5'},{'total':'25960'},{'classification':'exempt'},{'supply':'EXPORT'},{'cgst':'NaN'}])
def test_conflicting_rcm_keeps_previous_xml_and_original_facts(tmp_path,patch):
    row=record(tmp_path);export_all(tmp_path,[row],False)
    folder=Path(row['output_path']);previous=(folder/'Sales_Vouchers.xml').read_bytes()
    row=rcm_row(tmp_path);row['invoice'].update(patch);original=deepcopy(row['invoice'])
    with pytest.raises(ValueError):export_all(tmp_path,[row],False)
    assert (folder/'Sales_Vouchers.xml').read_bytes()==previous and row['invoice']==original


def test_rcm_and_normal_sale_do_not_share_incompatible_new_stock_master(tmp_path):
    normal=record(tmp_path);rcm=rcm_row(tmp_path);rcm.update(digest='b'*64,path=str(tmp_path/'rcm.pdf'))
    export_all(tmp_path,[normal,rcm],False)
    masters=ET.parse(Path(rcm['output_path'])/'Masters.xml')
    stocks=masters.findall('.//STOCKITEM')
    assert len(stocks)==4 and len({s.get('NAME') for s in stocks})==4
    assert sorted(s.findtext('GSTDETAILS.LIST/ISREVERSECHARGEAPPLICABLE') for s in stocks)==['No','No','Yes','Yes']


@pytest.mark.parametrize('rcm,existing,reuse',[(True,'Yes',True),(True,'No',False),(True,'',False),(False,'Yes',False),(False,'No',True)])
def test_stock_reuse_requires_compatible_reverse_charge(tmp_path,rcm,existing,reuse):
    from test_tally_master_matching import setup,choices
    from Common_Rules.tally_master_matching import assignments,save_choices
    row,ctx=setup(tmp_path)
    row['invoice']['reverse_charge']='Yes' if rcm else 'No'
    # Model a fetched stock with explicit reverse-charge metadata.
    xml=ctx['data']['stock_items'][0]['xml']
    xml=xml.replace('<GSTDETAILS.LIST>','<GSTDETAILS.LIST><ISREVERSECHARGEAPPLICABLE>'+existing+'</ISREVERSECHARGEAPPLICABLE>')
    ctx['data']['stock_items'][0]['xml']=xml;ctx.pop('_catalog',None)
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    assert (assignments(tmp_path,row,ctx)['items'][0]['stock'] is not None)==reuse


@pytest.mark.parametrize('kind',['credit_note','quotation','purchase_order','delivery_note','unknown'])
def test_non_sale_documents_cannot_generate_sales_xml(tmp_path,kind):
    row=record(tmp_path);row['invoice']['document_type']=kind
    with pytest.raises(ValueError,match='not a confirmed sales invoice'):export_all(tmp_path,[row],False)
    assert not list(tmp_path.rglob('Sales_Vouchers.xml'))


def test_structured_read_requires_addresses_hsn_and_separate_component_rates(tmp_path):
    row=rcm_row(tmp_path);inv=row['invoice']
    inv['items'][0].pop('hsn');inv['items'][1]['igst_rate']='bad'
    fields={p['field'] for p in checks(inv)}
    assert {'Seller address','Buyer address','Item 1 HSN/SAC','Item 2 IGST rate'}<=fields
    assert not any('reconciliation' in f for f in fields)  # Nominal RCM rate is not supplier-payable GST.


def test_prompt_has_ordered_party_and_date_procedure_and_all_review_fields(tmp_path,monkeypatch):
    from Common_Rules import extraction,groq_reader
    from Common_Rules.ai_invoice_rules import RULES
    from Invoice_Desktop import FIELDS,REVIEW_CHOICES
    monkeypatch.setattr(extraction,'text_from_pdf',lambda p:'Invoice Date 02/10/2026; Due Date 02/11/2026; Invoiced To: Buyer; Ship To: Warehouse')
    payload=groq_reader.prepare_invoice_payload({'path':'unused'},'mock')
    assert RULES in payload['messages'][0]['content']
    for word in ('Supplied To','Invoiced To','Consignee','Ship To','place_of_supply','invoice date','reverse_charge','printed_total'):
        assert word in payload['messages'][0]['content']
    assert {'document_type','reverse_charge','number','date','buyer_address','buyer_state','place_of_supply'}<=set(FIELDS)
    assert REVIEW_CHOICES['reverse_charge']==('','Yes','No')


def test_new_procedure_backup_manifest_and_installer_are_exact():
    root=Path(__file__).parents[2]
    change=json.loads((root/'Automation/SALES_INVOICE_PROCEDURE_CHANGE.json').read_text())
    package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(root/change['backup']) as backup:
        for name,entry in change['files'].items():
            assert hashlib.sha256(backup.read(name)).hexdigest()==entry['baseline_sha256']
            after_sales_procedure(root,name,entry['baseline_sha256'])
    for name in [*change['files'],*change['new_files']]:
        if name.startswith('Automation/') and name.endswith('.py'):
            assert package['FILES'][name.removeprefix('Automation/')].encode()==(root/name).read_bytes()


@pytest.mark.skipif(not os.environ.get('DISPLAY') and os.name!='nt',reason='Requires a desktop display')
def test_item_table_edits_original_variables_and_removes_rows():
    import tkinter as tk
    from tkinter import ttk
    from Invoice_Desktop import ITEM_FIELDS
    from Invoice_Item_Table import InvoiceItemTable,COLS
    window=tk.Tk();window.withdraw()
    try:
        table=InvoiceItemTable(window);original=ttk.LabelFrame(window);variables={}
        for index,field in enumerate(ITEM_FIELDS):
            row,col=index//3,(index%3)*2
            ttk.Label(original,text=field.replace('_',' ').title()).grid(row=row,column=col)
            variables[field]=tk.StringVar(master=window,value='original')
            ttk.Entry(original,textvariable=variables[field]).grid(row=row,column=col+1)
        table.sync({'one':original})
        for field,value in [('name','Corrected stock'),('unit','KG'),('hsn','9403'),('cgst_rate','9'),('printed_total','118')]:
            cell=table.rows['one'][[c[0] for c in COLS].index(field)]
            cell.delete(0,'end');cell.insert(0,value)
            assert variables[field].get()==value
        variables['quantity'].set('2.4877')
        assert table.rows['one'][2].get()=='2.4877'
        table.sync({});assert not table.rows
    finally:window.destroy()


@pytest.mark.skipif(not os.environ.get('DISPLAY') and os.name!='nt',reason='Requires a desktop display')
def test_actual_billsync_review_exposes_rcm_and_saves_shared_table_values(tmp_path,monkeypatch):
    import tkinter as tk
    import time
    from BillSync_UI import BillSyncApp
    from Common_Rules import groq_reader,ollama_reader
    from Invoice_Item_Table import COLS
    from test_ai_workflow_validation import source_row
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('Review must not call AI'))
    monkeypatch.setattr(ollama_reader,'request_invoice',lambda *a:pytest.fail('Review must not call AI'))
    window=tk.Tk();window.withdraw();app=BillSyncApp(window,data_root=tmp_path)
    try:
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:window.update();time.sleep(.01)
        row=source_row(tmp_path);app.records=[row];app.busy=False
        app.table.insert('','end',iid='0',values=('Client',row['invoice']['number'],'Seller','25960','','Review','',''))
        app.apply_filter()
        app.table.selection_set('0');app.table.focus('0');saved=[]
        monkeypatch.setattr(app,'save_manual_edits',lambda record,invoice:saved.append(invoice))
        app.review();window.update()
        top=next(w for w in window.winfo_children() if isinstance(w,tk.Toplevel))
        assert {'document_type','reverse_charge','buyer_address','seller_address','date','place_of_supply'}<=set(top.review_fields)
        rcm=top.review_fields['reverse_charge'];rcm.set('Yes')
        table=top.invoice_item_table
        assert len(table.rows)==2
        cell=next(iter(table.rows.values()))[[c[0] for c in COLS].index('name')]
        cell.delete(0,'end');cell.insert(0,'Human corrected stock')
        from BillSync_Theme import descendants
        from tkinter import ttk
        next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Save changes to XML').invoke()
        assert len(saved)==1 and saved[0]['reverse_charge']=='Yes'
        assert saved[0]['items'][0]['name']=='Human corrected stock'
    finally:
        app.closing=True;window.destroy()

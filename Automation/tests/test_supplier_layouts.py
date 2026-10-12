from copy import deepcopy
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET

import pytest
from reportlab.pdfgen import canvas

from Common_Rules.desktop import inspect_sources, process_sources, save_review
from Common_Rules.engine import read_json, write_json
from Common_Rules.supplier_layouts import (new_layout, parse_with_layout, preview_layout,
    save_layout, load_layouts, remove_layout)
from helpers import invoice, gstin


def mapped_text(inv):
    item=inv['items'][0]
    return f'''TAX BILL
DOCUMENT
Reference: {inv['number']} Issued: {inv['date']}
VENDOR
Legal Entity: {inv['seller_name']}
Registration ID: {inv['seller_gstin']}
Region: 27
BILLING PARTY
Legal Entity: {inv['buyer_name']}
Registration ID: {inv['buyer_gstin']}
Registration Category: {inv['buyer_registration']}
Region: {inv['buyer_state']}
DELIVERY
Supply Region: {inv['place_of_supply']}
Tax Class: {inv['classification']}
Assessable: {inv['taxable']}
Federal GST: {inv['cgst']}
Provincial GST: {inv['sgst']}
Integrated GST: {inv['igst']}
Invoice Value: {inv['total']}
Article | Tariff | Pieces | Measure | Unit Cost | Base | Local A | Local B | Integrated
{item['name']} | {item['hsn']} | {item['quantity']} | {item['unit']} | {item['rate']} | {item['value']} | {item['cgst_rate']} | {item['sgst_rate']} | {item['igst_rate']}
'''


def make_pdf(path,inv):
    pdf=canvas.Canvas(str(path));pdf.setFont('Courier',7)
    for i,line in enumerate(mapped_text(inv).splitlines()):pdf.drawString(20,810-i*22,line)
    pdf.save()


def setup(root):
    folder=root/'Client';folder.mkdir()
    inv=invoice('MAP-001');make_pdf(folder/'one.pdf',inv)
    record=inspect_sources(root,demo=False)[0]
    assert not record['invoice'].get('seller_gstin')
    # The sample was checked in the review form before teaching its layout.
    record['invoice']=inv
    layout=new_layout(record,False)
    layout['anchors']=['TAX BILL','VENDOR','BILLING PARTY']
    labels={'number':'Reference','date':'Issued','place_of_supply':'Supply Region','classification':'Tax Class',
        'taxable':'Assessable','total':'Invoice Value','cgst':'Federal GST','sgst':'Provincial GST','igst':'Integrated GST',
        'buyer_registration':'Registration Category'}
    layout['fields']={key:{'label':label} for key,label in labels.items()}
    for prefix,start,end in [('seller','VENDOR','BILLING PARTY'),('buyer','BILLING PARTY','DELIVERY')]:
        for suffix,label in [('name','Legal Entity'),('gstin','Registration ID'),('state','Region')]:
            layout['fields'][prefix+'_'+suffix]={'label':label,'start':start,'end':end,'column':'whole'}
    layout['headers']={key:[label] for key,label in zip(('name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate'),
        ('Article','Tariff','Pieces','Measure','Unit Cost','Base','Local A','Local B','Integrated'))}
    return folder,record,layout


def test_saved_mapping_reads_new_dates_buyers_amounts_and_gst_without_copying_sample(tmp_path):
    folder,record,layout=setup(tmp_path)
    assert preview_layout(mapped_text(record['invoice']),layout,False)[1]==[]
    saved=save_layout(tmp_path,record,layout,False)
    assert load_layouts(tmp_path)==[layout]
    assert '2360' not in saved.read_text() and 'MAP-001' not in saved.read_text()
    second=invoice('MAP-002',kind='inter');second.update(date='2026-11-14',taxable='3000',igst='540',total='3540')
    second['items'][0].update(quantity='3',value='3000')
    make_pdf(folder/'two.pdf',second)
    records=process_sources(tmp_path,demo=False)
    assert len(records)==2 and all(not record['errors'] for record in records)
    assert all(record['invoice']['supplier_layout_id']==layout['id'] for record in records)
    new=records[1]['invoice']
    assert new['number']=='MAP-002' and new['date']=='2026-11-14'
    assert new['buyer_gstin']==second['buyer_gstin'] and new['buyer_state']=='29'
    assert new['taxable']=='3000' and new['total']=='3540' and new['igst']=='540'
    assert new['items'][0]['quantity']=='3' and new['items'][0]['igst_rate']=='18'
    company=Path(records[0]['company_path'])
    vouchers=ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==2
    assert sum(len(v.findall('ALLINVENTORYENTRIES.LIST')) for v in vouchers)==2


def test_same_generic_gstin_label_needs_role_sections():
    # Without sections two distinct parties must never resolve to the first GSTIN.
    import uuid
    layout={'version':1,'id':uuid.uuid4().hex,'name':'Roles','seller_gstin':gstin(),'demo':False,
            'fields':{'seller_gstin':{'label':'Registration ID'}},'headers':{}}
    raw=parse_with_layout(mapped_text(invoice()),layout)
    assert any('Ambiguous seller_gstin' in warning for warning in raw['extraction_warnings'])
    assert not raw.get('seller_gstin')


@pytest.mark.parametrize('change', ['total','seller','header','scope','currency'])
def test_bad_preview_cannot_be_saved(tmp_path,change):
    folder,record,layout=setup(tmp_path)
    if change=='total':layout['fields']['total']['label']='Assessable'
    elif change=='seller':layout['fields']['seller_gstin']['start']='BILLING PARTY'
    elif change=='header':layout['headers']['quantity']=['Rate']
    elif change=='scope':layout['fields']['buyer_gstin']['start']='Missing heading'
    else:layout['fields']['currency']={'label':'Tax Class'}
    with pytest.raises(ValueError):save_layout(tmp_path,record,layout,False)
    assert load_layouts(tmp_path)==[]


def test_layout_cache_refresh_edit_remove_and_import_history_retained(tmp_path,monkeypatch):
    folder,record,layout=setup(tmp_path)
    before=inspect_sources(tmp_path,demo=False)[0]
    assert not before['invoice'].get('seller_name')
    save_layout(tmp_path,record,layout,False)
    parsed=process_sources(tmp_path,demo=False)[0]
    assert not parsed['errors']
    company=Path(parsed['company_path'])
    with sqlite3.connect(company/'.automation/history.sqlite3') as db:
        db.execute("UPDATE invoices SET status='imported'")
    def unexpected(*args):raise AssertionError('Mapping changes should reuse cached PDF text')
    monkeypatch.setattr('Common_Rules.desktop.text_from_pdf',unexpected)
    layout['name']='Updated label layout';save_layout(tmp_path,record,layout,False)
    updated=process_sources(tmp_path,demo=False)[0]
    assert updated['invoice']['supplier_layout_name']=='Updated label layout'
    assert updated['display_status']=='Already confirmed imported'
    assert list((tmp_path/'.invoice_app/supplier_layouts/backups').glob('*.json'))
    history=(company/'.automation/history.sqlite3').read_bytes()
    remove_layout(tmp_path,layout)
    assert (company/'.automation/history.sqlite3').read_bytes()==history
    assert load_layouts(tmp_path)==[] and (folder/'one.pdf').exists()
    assert not inspect_sources(tmp_path,demo=False)[0]['invoice'].get('supplier_layout_id')


def test_supplier_mode_and_anchor_isolation(tmp_path):
    folder,record,layout=setup(tmp_path);save_layout(tmp_path,record,layout,False)
    other=invoice('OTHER');other['seller_gstin']=gstin('27','OTHER1234A');make_pdf(folder/'other.pdf',other)
    assert not inspect_sources(tmp_path,demo=False)[1]['invoice'].get('supplier_layout_id')
    assert all(not r['invoice'].get('supplier_layout_id') for r in inspect_sources(tmp_path,demo=True))
    text=mapped_text(invoice()).replace('TAX BILL','DIFFERENT LAYOUT')
    from Common_Rules.supplier_layouts import extract_with_layouts
    assert not extract_with_layouts(text,[layout],False).get('supplier_layout_id')


def test_overlapping_profiles_are_blocked_instead_of_first_match(tmp_path):
    _,record,layout=setup(tmp_path);save_layout(tmp_path,record,layout,False)
    another=deepcopy(layout);another['id']='a'*32
    with pytest.raises(ValueError,match='already matches'):save_layout(tmp_path,record,another,False)
    write_json(tmp_path/'.invoice_app/supplier_layouts'/(another['id']+'.json'),another)
    inspected=inspect_sources(tmp_path,demo=False)[0]
    assert any('Multiple supplier layouts' in error for error in inspected['errors'])
    assert not process_sources(tmp_path,demo=False)[0].get('company_path')


def test_broken_catalog_cannot_be_hidden_by_approved_invoice(tmp_path):
    _,record,layout=setup(tmp_path)
    save_review(tmp_path,record,record['invoice'])
    write_json(tmp_path/'.invoice_app/supplier_layouts/bad.json',{'version':99})
    inspected=inspect_sources(tmp_path,demo=False)[0]
    assert any('Cannot read supplier layout' in error for error in inspected['errors'])


def test_supported_client11_layout_can_be_saved_and_reused_without_tax_approval(tmp_path):
    folder=tmp_path/'CLIENT 11';folder.mkdir()
    fixtures=Path(__file__).parent/'fixtures/client11'
    for path in fixtures.glob('*.pdf'):shutil.copy2(path,folder/path.name)
    record=process_sources(tmp_path)[0]
    layout=new_layout(record,True);save_layout(tmp_path,record,layout,True)
    records=process_sources(tmp_path)
    assert all(r['invoice']['supplier_layout_name']==layout['name'] for r in records)
    assert sum(bool(r['errors']) for r in records)==2
    assert all('exempt / nil-rated' in r['errors'][0] for r in records if r['errors'])


def test_sample_changed_or_mapping_constants_rejected(tmp_path):
    folder,record,layout=setup(tmp_path)
    bad=deepcopy(layout);bad['fields']['total']['value']='2360'
    with pytest.raises(ValueError,match='source labels'):save_layout(tmp_path,record,bad,False)
    (folder/'one.pdf').write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):save_layout(tmp_path,record,layout,False)


def test_next_line_values_and_first_line_after_heading(tmp_path):
    _,record,layout=setup(tmp_path)
    text=mapped_text(record['invoice']).replace('Reference: MAP-001','Reference:\nMAP-001')
    text=text.replace('Legal Entity: Dummy Seller','Dummy Seller')
    layout['fields']['seller_name']={'start':'VENDOR','end':'BILLING PARTY','position':'first_line'}
    parsed,errors=preview_layout(text,layout,False)
    assert errors==[] and parsed['number']=='MAP-001' and parsed['seller_name']=='Dummy Seller'


def test_two_party_columns_read_distinct_names_gstins_and_regions(tmp_path):
    _,record,layout=setup(tmp_path)
    inv=record['invoice'];text=mapped_text(inv)
    start=text.index('VENDOR');end=text.index('DELIVERY')
    text=text[:start]+f'''PARTIES
{inv['seller_name']}                {inv['buyer_name']}
GSTIN: {inv['seller_gstin']}        GSTIN: {inv['buyer_gstin']}
Region: 27                        Region: 27
'''+text[end:]
    layout['anchors']=['PARTIES']
    for prefix,column in [('seller','left'),('buyer','right')]:
        for suffix,label in [('name',''),('gstin','GSTIN'),('state','Region')]:
            layout['fields'][prefix+'_'+suffix]={'label':label,'start':'PARTIES','end':'DELIVERY',
                'column':column,'position':'first_line' if suffix=='name' else 'label'}
    layout['fields']['buyer_registration']={'label':'Registration Category'}
    text=text.replace('DELIVERY','DELIVERY\nRegistration Category: Regular')
    parsed,errors=preview_layout(text,layout,False)
    assert errors==[]
    assert parsed['seller_name']=='Dummy Seller' and parsed['buyer_name']=='Dummy Customer 27'
    assert parsed['seller_gstin']==inv['seller_gstin'] and parsed['buyer_gstin']==inv['buyer_gstin']


def test_mapping_cannot_reclassify_explicit_export_as_domestic(tmp_path):
    folder=tmp_path/'Client';folder.mkdir()
    source=Path(__file__).parent/'fixtures/client11/Sales_Invoice_07_EXPORT_LUT.pdf'
    shutil.copy2(source,folder/source.name)
    record=inspect_sources(tmp_path)[0]
    from Common_Rules.extraction import text_from_pdf
    text=text_from_pdf(source)+'\nOther Treatment: taxable\n'
    layout=new_layout(record,True)
    layout['fields']={'classification':{'label':'Other Treatment'}}
    _,errors=preview_layout(text,layout,True)
    assert any('printed export treatment' in error for error in errors)


def test_custom_header_aliases_also_apply_to_paired_native_adapter():
    from Common_Rules.extraction import parse_text, text_from_pdf
    text=text_from_pdf(Path(__file__).parent/'fixtures/client7/TEST-26-27-001_INTRA.pdf')
    invoice=parse_text(text)
    layout=new_layout({'invoice':invoice},True)
    layout['headers']={'name':['Commodity']}
    parsed,errors=preview_layout(text.replace('Goods / description','Commodity'),layout,True)
    assert errors==[] and len(parsed['items'])==2
    assert parsed['items'][0]['hsn']=='940320'

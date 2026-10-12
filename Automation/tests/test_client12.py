from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import shutil
import json
import sqlite3
import xml.etree.ElementTree as ET

import pytest

from Common_Rules.accounting import validate, money
from Common_Rules.desktop import process_sources, inspect_sources
from Common_Rules.engine import read_json
from Common_Rules.extraction import parse_text, text_from_pdf
from Common_Rules.supplier_layouts import new_layout, save_layout, preview_layout

FIXTURES=Path(__file__).parent/'fixtures/client12'


def setup(root):
    folder=root/'CLIENT 12';folder.mkdir()
    for path in FIXTURES.glob('*.pdf'):shutil.copy2(path,folder/path.name)
    return folder


def test_nine_uploaded_styles_all_accounting_without_manual_review(tmp_path):
    folder=setup(tmp_path)
    originals={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.glob('*.pdf')}
    records=process_sources(tmp_path)
    assert len(records)==9 and all(not record['errors'] for record in records)
    assert len({record['company_path'] for record in records})==1
    assert {record['batch_voucher_count'] for record in records}=={9}
    assert {record['invoice']['classification'] for record in records}=={'taxable','export_igst','export_lut','exempt','nil_rated'}
    company=Path(records[0]['company_path'])
    vouchers=ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==9
    assert sum(len(v.findall('ALLINVENTORYENTRIES.LIST')) for v in vouchers)==19
    totals={}
    for voucher in vouchers:
        rows=voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST')
        rows+=voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST')
        assert sum(money(row.findtext('AMOUNT')) for row in rows)==0
        for row in rows:
            name=row.findtext('LEDGERNAME');totals[name]=totals.get(name,Decimal(0))+money(row.findtext('AMOUNT'))
    assert totals['Sales']==Decimal('1662326')
    assert totals['Output CGST']==totals['Output SGST']==Decimal('3558.55')
    assert totals['Output IGST']==Decimal('139915.70')
    assert totals['Round Off']==Decimal('.20')
    assert -sum(value for name,value in totals.items() if name not in ('Sales','Output CGST','Output SGST','Output IGST','Round Off'))==Decimal('1809359')
    exports=[v for v in vouchers if v.get('OBJVIEW')=='Accounting Voucher View']
    assert len(exports)==2 and all(not v.findall('ALLINVENTORYENTRIES.LIST') for v in exports)
    assert any('original invoice USD 7900.00' in v.findtext('NARRATION') and 'INR 86.2' in v.findtext('NARRATION') for v in exports)
    assert any('original invoice AED 17680.00' in v.findtext('NARRATION') and 'INR 23.45' in v.findtext('NARRATION') for v in exports)
    discounted=next(v for v in vouchers if v.findtext('VOUCHERNUMBER')=='OTC/26-27/0003')
    assert [i.findtext('RATE') for i in discounted.findall('ALLINVENTORYENTRIES.LIST')]==['90.25/PKT','389.5/Nos','690/Nos','576/Nos']
    assert 'printed list rate INR 410, discount 5%' in discounted.findtext('NARRATION')
    manifest=read_json(company/'imports/manifest.json')
    assert manifest['valid_for_import'] is True and manifest['gst_return_mapping_verified'] is False
    config=read_json(company/'client.json')
    for unit,uqc in [('BOX','BOX'),('PRS','PRS'),('REAM','RIM'),('PKT','PAC'),('KGS','KGS'),('DOZ','DOZ')]:
        assert config['units'][unit]['uqc']==uqc
    assert all(not record['errors'] for record in process_sources(tmp_path))
    assert originals=={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.glob('*.pdf')}


def test_wrapped_names_leading_zero_hsn_receipt_and_explicit_zero_tax_classes():
    raw={path.name:parse_text(text_from_pdf(path)) for path in FIXTURES.glob('*.pdf')}
    assert raw['INV01_B2B_intra.pdf']['items'][0]['name']=='Steel Hex Bolts M10 (Box of 100)'
    assert raw['INV03_B2B_inter.pdf']['items'][1]['name']=='Mobile Phone Charger 20W'
    assert raw['INV03_B2B_inter.pdf']['items'][0]['hsn']=='0902'
    assert raw['INV05_B2C_inter.pdf']['items'][0]['name']=='Laptop 15 inch, Core i7, 16 GB'
    receipt=raw['INV04_B2C_intra.pdf']
    assert receipt['seller_name']=='ORION TRADING CO.' and len(receipt['items'])==3
    assert receipt['buyer_registration']=='Unregistered' and receipt['round_off']=='-0.10'
    assert receipt['total']=='2347.00'
    assert raw['INV08_B2B_exempt.pdf']['classification']=='exempt'
    assert raw['INV09_B2C_exempt.pdf']['classification']=='nil_rated'
    for name in ('INV08_B2B_exempt.pdf','INV09_B2C_exempt.pdf'):
        assert all(raw[name][tax]=='0.00' for tax in ('cgst','sgst','igst'))
    assert raw['INV06_EXP_export_pay.pdf']['shipping_bill_date']=='08-Oct-2026'
    assert raw['INV06_EXP_export_pay.pdf']['buyer_foreign_tax_id']=='EIN 98-7654321'


@pytest.mark.parametrize('name,before,after,reason',[
    ('INV01_B2B_intra.pdf','1,890.00','1,891.00','reconcile'),
    ('INV03_B2B_inter.pdf','10,830.00','10,831.00','reconcile'),
    ('INV06_EXP_export_pay.pdf','USD 1 = INR 86.20','USD 1 = INR 87.20','reconcile'),
    ('INV07_EXP_export_lut.pdf','0% (LUT)','18% (LUT)','reconcile'),
    ('INV06_EXP_export_pay.pdf','96-Other Countries','27-Maharashtra','place of supply'),
    ('INV08_B2B_exempt.pdf','NIL','100.00','NIL GST'),
    ('INV01_B2B_intra.pdf','For Orion Trading Co.','For Another Seller','identity'),
])
def test_conflicting_source_evidence_not_silently_exported(name,before,after,reason):
    text=text_from_pdf(FIXTURES/name)
    assert before in text
    invoice=parse_text(text.replace(before,after))
    assert any(reason in warning for warning in invoice['extraction_warnings'])


@pytest.mark.parametrize('field,value',[
    ('exchange_rate','90'),('foreign_currency','EUR'),('foreign_invoice_value','7901'),
    ('foreign_value','1000'),('foreign_rate','7'),('igst','0'),
])
def test_review_cannot_bypass_exchange_rate_or_foreign_value_reconciliation(tmp_path,field,value):
    setup(tmp_path);records=process_sources(tmp_path)
    company=Path(records[0]['company_path']);config=read_json(company/'client.json')
    invoices=read_json(company/'reports/validated_invoices.json')
    invoice=deepcopy(next(entry['invoice'] for entry in invoices if entry['invoice']['number']=='OTC/26-27/0006'))
    if field in ('foreign_value','foreign_rate'):invoice['items'][0][field]=value
    else:invoice[field]=value
    assert validate(invoice,config)[1]


@pytest.mark.parametrize('field,value', [('discount_rate','10'),('list_rate','96'),('printed_igst','540'),('printed_total','11000')])
def test_review_still_checks_list_price_discount_and_printed_item_tax(tmp_path,field,value):
    setup(tmp_path);records=process_sources(tmp_path)
    company=Path(records[0]['company_path']);config=read_json(company/'client.json')
    invoice=deepcopy(next(entry['invoice'] for entry in read_json(company/'reports/validated_invoices.json') if entry['invoice']['number']=='OTC/26-27/0003'))
    invoice['items'][0][field]=value
    assert validate(invoice,config)[1]


def test_both_new_fictional_notices_are_required_for_demo_and_block_real_mode(tmp_path):
    setup(tmp_path)
    assert all(record['errors'] for record in process_sources(tmp_path,demo=False))
    for name,marker in [('INV01_B2B_intra.pdf','Sample invoice generated for software testing. All names, GSTINs and figures are fictional.'),
                        ('INV04_B2C_intra.pdf','Fictional')]:
        text=text_from_pdf(FIXTURES/name)
        assert marker in text
        assert not parse_text(text.replace(marker,'TAX DOCUMENT')).get('dummy_document')


def test_supplier_profile_reuses_native_styles_and_spacing_only_metadata(tmp_path):
    setup(tmp_path);record=process_sources(tmp_path)[0]
    layout=new_layout(record,True)
    layout['fields']={'number':{'label':'Invoice No.'},'date':{'label':'Invoice Date'}}
    assert preview_layout(text_from_pdf(FIXTURES/'INV01_B2B_intra.pdf'),layout,True)[1]==[]
    save_layout(tmp_path,record,layout,True)
    records=process_sources(tmp_path)
    assert all(not record['errors'] for record in records)
    assert sum(bool(record['invoice'].get('supplier_layout_name')) for record in records)==8
    assert records[3]['invoice']['source_layout']=='receipt_items_v1'


@pytest.mark.parametrize('number', ['OTC/26-27/0003','OTC/26-27/0006'])
def test_prior_financial_hashes_preserve_import_status_and_pricing_data(tmp_path,number):
    from Common_Rules.accounting import previous_financial_fingerprint
    setup(tmp_path);records=process_sources(tmp_path)
    company=Path(records[0]['company_path']);database=company/'.automation/history.sqlite3'
    with sqlite3.connect(database) as db:
        key,data=next((key,json.loads(data)) for key,data in db.execute('SELECT invoice_key,data FROM invoices') if json.loads(data)['number']==number)
        prior=previous_financial_fingerprint(data)
        db.execute("UPDATE invoices SET fingerprint=?,status='imported' WHERE invoice_key=?",(prior,key))
    records=process_sources(tmp_path)
    assert all(not record['errors'] for record in records)
    assert next(record for record in records if record['invoice']['number']==number)['display_status']=='Already confirmed imported'
    with sqlite3.connect(database) as db:
        row=db.execute('SELECT fingerprint,data,status FROM invoices WHERE invoice_key=?',(key,)).fetchone()
        assert row[0]==prior and json.loads(row[1])==data and row[2]=='imported'

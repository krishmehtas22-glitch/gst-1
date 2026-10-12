from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

from Common_Rules.accounting import validate, money
from Common_Rules.desktop import process_sources, save_review, refresh_review
from Common_Rules.engine import read_json
from Common_Rules.extraction import parse_text, text_from_pdf

FIXTURES=Path(__file__).parent/'fixtures/client11'


def source(name='Sales_Invoice_01_INTRA.pdf'):
    return text_from_pdf(FIXTURES/name)


def install(root):
    folder=root/'CLIENT 11';folder.mkdir()
    for path in FIXTURES.glob('*.pdf'):
        shutil.copy2(path,folder/path.name)


def test_all_ten_source_panels_keep_party_roles_and_identifiers_separate():
    buyers=['Sahyadri Retail LLP','Godavari Supplies','Orange City Traders',
        'Sabarmati Distribution','Southern Office Mart','Capital Trade House',
        'Desert Horizon Trading LLC','Marina Global Pte Ltd','Fresh Harvest Foods','Pink City Agro Stores']
    for index,path in enumerate(sorted(FIXTURES.glob('*.pdf')),1):
        inv=parse_text(text_from_pdf(path))
        assert inv['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED'
        assert inv['seller_gstin']=='27ABCDE1234F1Z5'
        assert inv['seller_state']=='27'
        assert inv['seller_address']=='Unit 12, Industrial Estate, Andheri East, Mumbai, Maharashtra - 400093'
        assert inv['buyer_name']==buyers[index-1]
        assert inv['number']==f'DM/26-27/{index:04d}'
        assert inv['date']==f'2026-10-{index+12:02d}'
        assert inv['dummy_document'] is True
        assert len(inv['items'])==1
        assert len(inv['extraction_warnings'])==(1 if index>=9 else 0)
    assert parse_text(source('Sales_Invoice_10_EXEMPT.pdf'))['buyer_gstin']=='08EFGHI9876J1Z9'


def test_uploaded_accounting_all_ten_after_exempt_classification_review(tmp_path):
    install(tmp_path)
    records=process_sources(tmp_path)
    assert len(records)==10
    assert sum(not record['errors'] for record in records)==8
    for record in records:
        if record['errors']:
            assert record['invoice']['classification']=='exempt'
            assert record['errors']==['Remarks say exempt / nil-rated; confirm classification in Review']
            save_review(tmp_path,record,record['invoice'])
    records=process_sources(tmp_path)
    assert all(not record['errors'] for record in records)
    assert {record['batch_voucher_count'] for record in records}=={10}
    assert len({record['company_path'] for record in records})==1
    company=Path(records[0]['company_path'])
    vouchers=ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==10
    totals={}
    for voucher in vouchers:
        entries=voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST')
        entries+=voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST')
        assert sum(money(entry.findtext('AMOUNT')) for entry in entries)==0
        for entry in entries:
            name=entry.findtext('LEDGERNAME')
            totals[name]=totals.get(name,Decimal(0))+money(entry.findtext('AMOUNT'))
    assert totals['Sales']==Decimal('121200')
    assert totals['Output CGST']==totals['Output SGST']==Decimal('2316')
    assert totals['Output IGST']==Decimal('10074')
    assert -sum(value for value in totals.values() if value<0)==Decimal('135906')
    export=next(v for v in vouchers if v.findtext('VOUCHERNUMBER')=='DM/26-27/0008')
    assert export.get('OBJVIEW')=='Accounting Voucher View'
    assert export.findtext('COUNTRYOFRESIDENCE')=='Singapore'
    assert not export.findall('ALLINVENTORYENTRIES.LIST')
    assert [(e.findtext('LEDGERNAME'),e.findtext('AMOUNT')) for e in export.findall('ALLLEDGERENTRIES.LIST')]==[
        ('Marina Global Pte Ltd','-42480.00'),('Sales','36000.00'),('Output IGST','6480.00')]
    assert 'EXPORT WITH PAYMENT OF IGST' in export.findtext('NARRATION')
    assert 'TEST-SB-008' in export.findtext('NARRATION')
    manifest=read_json(company/'imports/manifest.json')
    assert manifest['valid_for_import'] is True
    assert manifest['gst_return_mapping_verified'] is False
    assert len(manifest['accounting_only_exports'])==2
    assert len(ET.parse(company/'imports/Masters.xml').findall('.//STOCKITEM'))==8
    assert all(not record['errors'] for record in process_sources(tmp_path))


@pytest.mark.parametrize('before,after,message',[
    ('Reverse Charge: No','Reverse Charge: Yes','reverse charge'),
    ('For DEMO MERCANTILE PRIVATE LIMITED','For ANOTHER SELLER','Seller name/address'),
    ('Sahyadri Retail LLP Sahyadri Retail LLP','Sahyadri Retail LLP Other Company','Buyer name/address'),
    ('Maharashtra (27)','Gujarat (24)','Seller state labels conflict'),
    ('INR 1,152.00','INR 1,151.99','exact item'),
])
def test_conflicting_or_ambiguous_source_not_silently_repaired(before,after,message):
    inv=parse_text(source().replace(before,after))
    assert any(message in warning for warning in inv['extraction_warnings'])


def test_multi_item_totals_cannot_establish_unprinted_item_rates():
    text=source()
    item_line=next(line for line in text.splitlines() if 'Office chairs' in line)
    inv=parse_text(text.replace(item_line,item_line+'\n'+item_line))
    assert len(inv['items'])==2
    assert any('Item-wise GST rates missing' in warning for warning in inv['extraction_warnings'])
    assert all('cgst_rate' not in item for item in inv['items'])


def test_new_synthetic_notice_required_in_demo_and_forbidden_in_real(tmp_path):
    install(tmp_path)
    assert all(record['errors'] for record in process_sources(tmp_path,demo=False))
    text=source().replace('SYNTHETIC TEST DOCUMENT - NOT FOR REAL GST FILING OR COMMERCIAL USE.','TAX INVOICE')
    assert not parse_text(text).get('dummy_document')


@pytest.mark.parametrize('field,value',[
    ('export_mode','LUT_without_payment'),('classification','export_lut'),
    ('igst','0'),('cgst','1'),('buyer_country','India'),('buyer_state','27'),
])
def test_export_with_igst_financial_constraints(tmp_path,field,value):
    folder=tmp_path/'CLIENT 11';folder.mkdir()
    path=FIXTURES/'Sales_Invoice_08_EXPORT_IGST.pdf';shutil.copy2(path,folder/path.name)
    record=process_sources(tmp_path)[0]
    assert record['errors']==[]
    company=Path(record['company_path'])
    inv=read_json(company/'reports/validated_invoices.json')[0]['invoice']
    inv[field]=value
    assert validate(inv,read_json(company/'client.json'))[1]


def test_export_review_cannot_change_payment_mode(tmp_path):
    install(tmp_path)
    record=process_sources(tmp_path)[7]
    inv=deepcopy(record['invoice']);inv['classification']='export_lut';inv['export_mode']='LUT_without_payment'
    save_review(tmp_path,record,inv)
    assert any('Reviewed export treatment' in error for error in process_sources(tmp_path)[7]['errors'])


def test_same_warning_approval_does_not_approve_new_parser_uncertainty():
    original={'extraction_warnings':['Old warning'],'items':[]}
    saved={'original_extraction':original,'invoice':{'extraction_warnings':[],'items':[]}}
    assert refresh_review(original,saved)['extraction_warnings']==[]
    assert refresh_review({**original,'extraction_warnings':['New warning']},saved)['extraction_warnings']==['New warning']

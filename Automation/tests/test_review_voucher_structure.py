from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.tally_review_export import export_all,verify_vouchers


def record(root):
    inv={'number':'TEST-26-27-001','date':'2026-10-02','seller_name':'Western Trade Supplies','seller_gstin':'INVALID','buyer_name':'Northstar Hardware',
         'classification':'taxable','supply':'INTRA','place_of_supply':'27','taxable':'22000','total':'25960','cgst':'1980','sgst':'1980','igst':'0','round_off':'0','cess':'0',
         'items':[{'name':'Steel storage rack','quantity':'4','unit':'Nos','rate':'2500','value':'10000','hsn':'9403','cgst_rate':'9','sgst_rate':'9','igst_rate':'0'},
                  {'name':'Office chair','quantity':'3','unit':'Nos','rate':'4000','value':'12000','hsn':'9403','cgst_rate':'9','sgst_rate':'9','igst_rate':'0'}]}
    return {'client':'Client','path':str(root/'source.pdf'),'digest':'a'*64,'invoice':inv,'errors':[]}


def output(root):
    r=record(root);export_all(root,[r],True)
    folder=Path(r['output_path']);return r,ET.parse(folder/'Sales_Vouchers.xml'),ET.parse(folder/'Masters.xml')


def test_inventory_gross_buyer_debit_matches_item_and_gst_credits(tmp_path):
    r,sales,masters=output(tmp_path);voucher=sales.find('.//VOUCHER')
    assert voucher.attrib['OBJVIEW']=='Invoice Voucher View'
    assert not voucher.findall('ALLLEDGERENTRIES.LIST')
    entries=voucher.findall('LEDGERENTRIES.LIST')
    party=next(e for e in entries if e.findtext('ISPARTYLEDGER')=='Yes')
    assert party.findtext('LEDGERNAME')==voucher.findtext('PARTYLEDGERNAME')
    assert party.findtext('LEDGERNAME').startswith('Northstar Hardware')
    assert voucher.findtext('BASICBUYERNAME')=='Northstar Hardware'
    assert Decimal(party.findtext('AMOUNT'))==-25960
    assert {e.findtext('LEDGERNAME'):Decimal(e.findtext('AMOUNT')) for e in entries if e is not party}=={'CGST':Decimal('1980'),'SGST':Decimal('1980')}
    assert 'Sales' not in {e.findtext('LEDGERNAME') for e in entries}
    items=voucher.findall('ALLINVENTORYENTRIES.LIST')
    assert sum(Decimal(i.findtext('ACCOUNTINGALLOCATIONS.LIST/AMOUNT')) for i in items)==22000
    for item in items:
        batch=item.find('BATCHALLOCATIONS.LIST')
        assert batch.findtext('GODOWNNAME')=='Main Location'
        assert batch.findtext('AMOUNT')==item.findtext('AMOUNT')
        assert batch.findtext('ACTUALQTY')==item.findtext('ACTUALQTY')
    assert party.findtext('LEDGERNAME') in {m.attrib['NAME'] for m in masters.findall('.//LEDGER')}
    verify_vouchers(sales.getroot())


def test_verifier_rejects_wrong_inventory_list_even_if_arithmetic_balances(tmp_path):
    _,sales,_=output(tmp_path)
    for entry in sales.findall('.//VOUCHER/LEDGERENTRIES.LIST'):entry.tag='ALLLEDGERENTRIES.LIST'
    with pytest.raises(ValueError,match='ledger list'):verify_vouchers(sales.getroot())


def test_verifier_rejects_wrong_party_and_double_sales_credit(tmp_path):
    _,sales,_=output(tmp_path);voucher=sales.find('.//VOUCHER')
    party=next(e for e in voucher.findall('LEDGERENTRIES.LIST') if e.findtext('ISPARTYLEDGER')=='Yes')
    party.find('LEDGERNAME').text='Sales'
    with pytest.raises(ValueError,match='buyer ledger'):verify_vouchers(sales.getroot())
    party.find('LEDGERNAME').text=voucher.findtext('PARTYLEDGERNAME')
    duplicate=ET.SubElement(voucher,'LEDGERENTRIES.LIST')
    ET.SubElement(duplicate,'LEDGERNAME').text='Sales';ET.SubElement(duplicate,'AMOUNT').text='22000'
    with pytest.raises(ValueError,match='debit/credit'):verify_vouchers(sales.getroot())


def test_accounting_fallback_keeps_allledgerentries_and_balances(tmp_path):
    r=record(tmp_path);r['invoice']['items'][0].pop('cgst_rate')
    export_all(tmp_path,[r],True)
    sales=ET.parse(Path(r['output_path'])/'Sales_Vouchers.xml');voucher=sales.find('.//VOUCHER')
    assert voucher.attrib['OBJVIEW']=='Accounting Voucher View'
    assert not voucher.findall('LEDGERENTRIES.LIST') and not voucher.findall('ALLINVENTORYENTRIES.LIST')
    assert sum(Decimal(e.findtext('AMOUNT')) for e in voucher.findall('ALLLEDGERENTRIES.LIST'))==0
    verify_vouchers(sales.getroot())

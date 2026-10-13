from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.extraction import parse_text
from Common_Rules.desktop import process_sources
from Common_Rules.unit_choices import save_unit_choices
from Common_Rules.accounting import validate
from helpers import gstin,client
from test_generic_treatments import pdf


def source(header='Item | HSN | Rate | Value',row='Service item | 998300 | 100 | 100',taxes='CGST: 0\nSGST: 0\nIGST: 0'):
    return f'''Invoice No: ZERO-001
Invoice Date: 2026-10-13
Seller: Example Seller
Seller GSTIN: {gstin()}
Buyer: Example Buyer
Buyer GSTIN: {gstin('27','PQRSX5678L')}
Buyer Registration: Regular
Buyer State: Maharashtra
Place of supply: Maharashtra
Supply type: INTRA
Tax Treatment: taxable
Currency: INR
Taxable Value: 100
{taxes}
Grand Total: 100
{header}
{row}
'''


def test_missing_quantity_and_unit_default_to_one_unit_without_gst_ledgers(tmp_path):
    folder=tmp_path/'Client';folder.mkdir();pdf(folder/'invoice.pdf',source())
    record=process_sources(tmp_path,demo=False)[0];assert not record['errors']
    item=record['invoice']['items'][0]
    assert item['quantity']=='1' and item['unit']=='Units'
    assert item['quantity_assumed'] and item['unit_auto']
    assert not item['quantity_confirmed']
    assert not record['invoice'].get('tax_accounting_basis')
    voucher=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
    assert voucher.findtext('ALLINVENTORYENTRIES.LIST/ACTUALQTY')=='1 Units'
    assert not any('Output ' in (e.findtext('LEDGERNAME') or '') for e in voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST'))
    save_unit_choices(tmp_path,[(record,0,'Units')]);confirmed=process_sources(tmp_path,demo=False)[0]
    assert not confirmed['errors']
    assert confirmed['invoice']['items'][0]['quantity_confirmed']
    assert not confirmed['invoice']['items'][0]['unit_auto']


@pytest.mark.parametrize('column,value,quantity,unit',[
    ('Unit','LTR','1','LTR'),('Units','LTR','1','LTR'),
    ('Units','1','1','Units'),('Qty | Unit','1 | KG','1','KG')])
def test_printed_units_and_numeric_unit_columns_are_not_overwritten(column,value,quantity,unit):
    inv=parse_text(source('Item | HSN | '+column+' | Rate | Value','Service item | 998300 | '+value+' | 100 | 100'))
    item=inv['items'][0];assert item['quantity']==quantity
    # A numeric Units column supplies quantity but has no actual unit.
    if column=='Units' and value=='1':assert not item.get('unit') and not item.get('quantity_assumed')
    else:assert item['unit']==unit


@pytest.mark.parametrize('taxes',['GST: 0','Total GST: 0.00','No GST charged'])
def test_explicit_zero_declaration_supports_omitted_components(taxes):
    inv=parse_text(source(taxes=taxes))
    assert all(inv[tax]=='0' for tax in ('cgst','sgst','igst'))
    assert not inv.get('tax_accounting_basis') and not inv['extraction_warnings']


def test_missing_quantity_assumption_does_not_hide_extension_or_gst_conflicts(tmp_path):
    folder=client(tmp_path);from Common_Rules.engine import read_json
    config=read_json(folder/'client.json')
    inv=parse_text(source(row='Service item | 998300 | 50 | 100'))
    _,errors=validate(inv,config)
    assert any('quantity × rate' in error for error in errors)
    inv=parse_text(source(taxes='CGST: 9\nSGST: 9\nIGST: 0\nNo GST charged'))
    assert any('no-GST declaration conflicts' in error for error in inv['extraction_warnings'])
    inv=parse_text(source('Item | HSN | Qty | Unit | Rate | Value','Service item | 998300 | 0 | Units | 100 | 100'))
    assert inv['items'][0]['quantity']=='0' and not inv['items'][0].get('quantity_assumed')


def test_missing_gst_is_not_an_explicit_zero_declaration():
    inv=parse_text(source(taxes=''))
    assert all(inv.get(tax) is None for tax in ('cgst','sgst','igst'))

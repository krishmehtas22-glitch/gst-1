from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest

from Common_Rules.accounting import accounting_entries, validate, invoice_key
from Common_Rules.desktop import process_sources
from Common_Rules.engine import read_json
from Common_Rules.tally_xml import sales_document, verify_sales

FIXTURES=Path(__file__).parent/'fixtures/client7'


def process_export(tmp_path,name='TEST-26-27-005_EXPORT.pdf'):
    folder=tmp_path/'CLIENT 7';folder.mkdir()
    shutil.copy2(FIXTURES/name,folder/name)
    record=process_sources(tmp_path)[0]
    assert record['errors']==[]
    company=Path(record['company_path'])
    config=read_json(company/'client.json')
    inv=read_json(company/'reports/validated_invoices.json')[0]['invoice']
    return company,config,inv


@pytest.mark.parametrize('name,total,country',[
    ('TEST-26-27-005_EXPORT.pdf','30000.00','United Arab Emirates'),
    ('TEST-26-27-006_EXPORT.pdf','45000.00','United States of America')])
def test_lut_exports_debit_foreign_debtor_credit_export_sales(tmp_path,name,total,country):
    company,config,inv=process_export(tmp_path,name)
    assert inv['classification']=='export_lut'
    assert inv['buyer_country']==country
    assert inv['buyer_state']=='Outside India' and inv['buyer_gstin']==''
    assert inv['export_mode']=='LUT_without_payment'
    assert accounting_entries(inv,config)==[
        {'ledger':inv['buyer_name'],'debit':total,'credit':'0.00'},
        {'ledger':'Sales','debit':'0.00','credit':total}]
    root=ET.parse(company/'imports/Sales_Vouchers.xml')
    voucher=root.find('.//VOUCHER')
    assert voucher.get('OBJVIEW')=='Accounting Voucher View'
    assert voucher.findtext('ISINVOICE')=='No'
    assert voucher.findtext('VOUCHERTYPENAME')=='Sales'
    assert voucher.findtext('COUNTRYOFRESIDENCE')==country
    assert voucher.findtext('PLACEOFSUPPLY')=='Outside India'
    assert not voucher.findall('ALLINVENTORYENTRIES.LIST')
    amounts=[node.findtext('AMOUNT') for node in voucher.findall('ALLLEDGERENTRIES.LIST')]
    assert amounts==['-'+total,total]
    assert 'no inventory movement' in voucher.findtext('NARRATION')
    assert inv['shipping_bill_port'] in voucher.findtext('NARRATION')
    masters=ET.parse(company/'imports/Masters.xml')
    assert masters.find('.//STOCKITEM') is None
    debtor=next(node for node in masters.findall('.//LEDGER') if node.get('NAME')==inv['buyer_name'])
    assert debtor.findtext('COUNTRYNAME')==country
    assert debtor.findtext('LEDSTATENAME')=='Not Applicable'
    manifest=read_json(company/'imports/manifest.json')
    assert manifest['valid_for_import'] is True
    assert manifest['gst_return_mapping_verified'] is False
    assert len(manifest['accounting_only_exports'])==1
    assert manifest['accounting_only_exports'][0]['number']==inv['number']


@pytest.mark.parametrize('field,value',[
    ('export_mode','with_payment'),('buyer_country','India'),('buyer_country',''),
    ('place_of_supply','Maharashtra'),('buyer_state','27'),
    ('buyer_gstin','27TESTA1000A1Z5'),('cgst','1'),('igst','10')])
def test_conflicting_export_details_never_validate(tmp_path,field,value):
    _,config,inv=process_export(tmp_path)
    raw=deepcopy(inv);raw[field]=value
    _,errors=validate(raw,config)
    assert errors


def test_serialized_export_allocations_cannot_be_changed(tmp_path):
    _,config,inv=process_export(tmp_path)
    invoices={invoice_key(inv):inv}
    root=sales_document(config,invoices)
    root.find('.//VOUCHER/ALLLEDGERENTRIES.LIST/LEDGERNAME').text='Wrong customer'
    with pytest.raises(ValueError,match='Export XML ledger allocations'):
        verify_sales(root,invoices,config)

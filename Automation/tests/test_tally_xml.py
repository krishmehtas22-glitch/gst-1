from copy import deepcopy
from decimal import Decimal
import hashlib
import xml.etree.ElementTree as ET
import pytest

from Common_Rules.accounting import money, validate
from Common_Rules.engine import INBOX, confirm_import, read_json, run, write_json
from Common_Rules.masters import plan_masters, required_masters
from Common_Rules.tally_xml import masters_document, sales_document, verify_sales, verify_references
from helpers import client, invoice, pdf, write_snapshot


def generated(tmp_path, inv=None):
    c = client(tmp_path)
    pdf(c / 'one.pdf',inv or invoice())
    report = run(tmp_path)['clients'][0]
    assert not report['issues']
    assert report['history'][0]['status'] == 'generated'
    return c,report


@pytest.mark.parametrize('kind,ledgers',[('intra',{'Output CGST','Output SGST'}),('inter',{'Output IGST'}),('exempt',set())])
def test_xml_voucher_amounts_and_separate_taxes(tmp_path,kind,ledgers):
    c,_ = generated(tmp_path,invoice(kind=kind))
    root = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').getroot()
    assert root.findtext('HEADER/TALLYREQUEST') == 'Import Data'
    assert root.findtext('BODY/IMPORTDATA/REQUESTDESC/REPORTNAME') == 'Vouchers'
    assert root.findtext('BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES/SVCURRENTCOMPANY') == 'Client 1 Company'
    vouchers = root.findall('.//VOUCHER')
    assert len(vouchers) == 1
    v = vouchers[0]
    assert v.findtext('VOUCHERTYPENAME') == 'Sales'
    assert v.get('ACTION') == 'Create'
    assert v.findtext('DATE') == '20260401'
    assert v.findtext('VOUCHERNUMBER') == 'INV-001'
    assert v.findtext('PLACEOFSUPPLY') == ('Karnataka' if kind == 'inter' else 'Maharashtra')
    entries = v.findall('LEDGERENTRIES.LIST')
    assert {e.findtext('LEDGERNAME') for e in entries[1:]} == ledgers
    assert entries[0].findtext('ISDEEMEDPOSITIVE') == 'Yes'
    assert money(entries[0].findtext('AMOUNT')) < 0
    assert all(e.findtext('ISDEEMEDPOSITIVE') == 'No' for e in entries[1:])
    assert money(entries[0].findtext('BILLALLOCATIONS.LIST/AMOUNT')) == money(entries[0].findtext('AMOUNT'))
    inventory = v.findall('ALLINVENTORYENTRIES.LIST')
    assert len(inventory) == 1
    assert inventory[0].findtext('ACTUALQTY') == '2 Nos'
    assert inventory[0].findtext('RATE') == '1000/Nos'
    assert sum(money(e.findtext('AMOUNT')) for e in entries) + sum(money(a.findtext('AMOUNT')) for a in v.findall('.//ACCOUNTINGALLOCATIONS.LIST')) == Decimal('0')
    assert v.get('REMOTEID') == v.findtext('GUID')


def test_xml_dependency_order_gstin_hsn_and_rates(tmp_path):
    c,_ = generated(tmp_path)
    root = ET.parse(c / 'imports' / 'Masters.xml').getroot()
    assert root.findtext('BODY/IMPORTDATA/REQUESTDESC/REPORTNAME') == 'All Masters'
    objects = [list(msg)[0] for msg in root.findall('.//TALLYMESSAGE')]
    tags = [m.tag for m in objects]
    assert tags[0] == 'UNIT'
    assert tags[-1] == 'STOCKITEM'
    assert all((m.get('Action') if m.tag=='UNIT' else m.get('ACTION')) == 'Create' for m in objects)
    assert len({(m.tag,m.get('NAME')) for m in objects}) == len(objects)
    unit = root.find('.//UNIT')
    assert unit.findtext('GSTREPUOM') == 'NOS-NUMBERS'
    assert unit.findtext('DECIMALPLACES') == '0'
    customer = next(m for m in root.findall('.//LEDGER') if m.findtext('PARENT') == 'Sundry Debtors')
    assert customer.findtext('PARTYGSTIN') == invoice()['buyer_gstin']
    tax_ledgers = [m for m in root.findall('.//LEDGER') if m.findtext('PARENT') == 'Duties & Taxes']
    assert {m.findtext('GSTDUTYHEAD') for m in tax_ledgers} == {'Central Tax','State Tax'}
    stock = root.find('.//STOCKITEM')
    assert stock.findtext('BASEUNITS') == 'Nos'
    assert stock.findtext('GSTDETAILS.LIST/HSNCODE') == '8418'
    rates = {m.findtext('GSTRATEDUTYHEAD'):m.findtext('GSTRATE') for m in stock.findall('.//RATEDETAILS.LIST')}
    assert rates == {'Central Tax':'9','State Tax':'9','Integrated Tax':'18'}


def test_multi_item_one_voucher_with_no_double_sales_posting(tmp_path):
    inv = invoice()
    inv['items'][0].update(quantity='1',value='1000')
    item = dict(inv['items'][0],name='Product B')
    inv['items'].append(item)
    c,_ = generated(tmp_path,inv)
    root = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').getroot()
    assert len(root.findall('.//VOUCHER')) == 1
    assert len(root.findall('.//ALLINVENTORYENTRIES.LIST')) == 2
    assert len(root.findall('.//ACCOUNTINGALLOCATIONS.LIST')) == 2
    assert all(n.findtext('LEDGERNAME') != 'Sales' for n in root.findall('.//LEDGERENTRIES.LIST'))


def test_stable_remote_ids_reruns_and_client_isolation(tmp_path):
    c,_ = generated(tmp_path)
    first = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').find('.//VOUCHER').get('REMOTEID')
    run(tmp_path)
    again = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').find('.//VOUCHER').get('REMOTEID')
    assert first == again
    other = client(tmp_path,'Client 2')
    pdf(other / 'same.pdf',invoice())
    report = run(tmp_path)
    different = ET.parse(other / 'imports' / 'Sales_Vouchers.xml').find('.//VOUCHER').get('REMOTEID')
    assert first != different
    assert len(report['clients'][0]['history']) == 1


def test_xml_escaping_and_invalid_control_chars(tmp_path):
    inv = invoice()
    inv.update(buyer_name='Customer & Sons <East>',number='INV & <01>')
    inv['items'][0]['name'] = 'Fridge & Freezer <Large>'
    c,_ = generated(tmp_path,inv)
    root = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').getroot()
    assert root.findtext('.//PARTYLEDGERNAME') == inv['buyer_name']
    assert root.findtext('.//VOUCHERNUMBER') == inv['number']
    assert b'&amp;' in (c / 'imports' / 'Sales_Vouchers.xml').read_bytes()
    config = read_json(c / 'client.json')
    canonical,_ = validate(inv,config)
    canonical['source'] = 'one.pdf'
    canonical['buyer_name'] = 'Invalid\x01Name'
    with pytest.raises(ValueError,match='control character'):
        sales_document(config,{'one':canonical})


def test_xml_structural_validation_catches_balance_error(tmp_path):
    c,_ = generated(tmp_path)
    root = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').getroot()
    config = read_json(c / 'client.json')
    root.find('.//ACCOUNTINGALLOCATIONS.LIST/AMOUNT').text = '1000'
    with pytest.raises(ValueError,match='balance exactly'):
        verify_sales(root,{'one':invoice()},config)


def test_xml_confirmed_imports_not_regenerated(tmp_path):
    c,_ = generated(tmp_path)
    manifest = read_json(c / 'imports' / 'manifest.json')
    assert manifest['import_order'] == ['Masters.xml','Sales_Vouchers.xml']
    result = {'company_id':manifest['company_id'],'generated_at':manifest['generated_at'],
              'tally_result_reference':'SYNTHETIC TEST ONLY - no live import',
              'masters':[{'master':m,'status':'imported'} for m in manifest['masters']],
              'vouchers':[{'invoice_key':k,'status':'imported'} for k in manifest['invoice_keys']]}
    path = c / 'import_results.json'
    write_json(path,result)
    confirm_import(c,path)
    report = run(tmp_path)['clients'][0]
    assert report['history'][0]['status'] == 'imported'
    assert report['pending_validated'] == 0
    assert not (c / 'imports' / 'Sales_Vouchers.xml').exists()
    pdf(c / 'two.pdf',invoice('NEW-002'))
    report = run(tmp_path)['clients'][0]
    assert report['counts']['new'] == 1
    assert not (c / 'imports' / 'Masters.xml').exists()
    assert ET.parse(c / 'imports' / 'Sales_Vouchers.xml').findtext('.//VOUCHERNUMBER') == 'NEW-002'


def test_round_off_entry_sign(tmp_path):
    inv = invoice()
    inv.update(round_off='-0.50',total='2359.50')
    c,_ = generated(tmp_path,inv)
    entries = ET.parse(c / 'imports' / 'Sales_Vouchers.xml').findall('.//LEDGERENTRIES.LIST')
    rounding = next(e for e in entries if e.findtext('LEDGERNAME') == 'Round Off')
    assert rounding.findtext('ISDEEMEDPOSITIVE') == 'Yes'
    assert rounding.findtext('AMOUNT') == '-0.50'


def test_shared_unit_is_kept_for_valid_invoice_when_other_conflicts(tmp_path):
    c = client(tmp_path)
    config = read_json(c / 'client.json')
    a,_ = validate(invoice('A'),config)
    b,_ = validate(invoice('B'),config)
    b['buyer_name'] = 'Conflicting Customer'
    existing = [{'kind':'ledger','name':'Conflicting Customer','group':'Sundry Debtors','gstin':'wrong'}]
    masters,errors = plan_masters({'a':a,'b':b},config,existing)
    assert set(errors) == {'b'}
    assert any(m['kind'] == 'unit' for m in masters)


def test_old_configuration_defaults_to_xml(tmp_path):
    c = client(tmp_path)
    config = read_json(c / 'client.json')
    del config['output_format']
    write_json(c / 'client.json',config)
    pdf(c / 'one.pdf',invoice())
    assert run(tmp_path)['clients'][0]['output_format'] == 'xml'
    assert (c / 'imports' / 'Masters.xml').is_file()


def test_same_product_intra_and_inter_uses_one_stock_master(tmp_path):
    c = client(tmp_path)
    pdf(c / 'local.pdf',invoice('LOCAL','intra','Fridge'))
    pdf(c / 'interstate.pdf',invoice('INTERSTATE','inter','Fridge'))
    report = run(tmp_path)['clients'][0]
    assert report['pending_validated'] == 2
    assert not report['issues']
    stock = ET.parse(c / 'imports' / 'Masters.xml').findall('.//STOCKITEM')
    assert len(stock) == 1
    assert stock[0].get('NAME') == 'Fridge'
    assert len(ET.parse(c / 'imports' / 'Sales_Vouchers.xml').findall('.//VOUCHER')) == 2


def test_missing_master_reference_blocks_export(tmp_path):
    c = client(tmp_path)
    config = read_json(c / 'client.json')
    inv,_ = validate(invoice(),config)
    masters = required_masters(inv,config)
    masters = [m for m in masters if m['kind'] != 'unit']
    with pytest.raises(ValueError,match='master reference: unit'):
        verify_references(config,{'one':inv},masters)


def test_xml_custom_stock_group_before_stock_item(tmp_path):
    c = client(tmp_path)
    config = read_json(c / 'client.json')
    config['stock_group'] = 'Appliances'
    write_json(c / 'client.json',config)
    pdf(c / 'one.pdf',invoice())
    assert not run(tmp_path)['clients'][0]['issues']
    root = ET.parse(c / 'imports' / 'Masters.xml').getroot()
    objects = [list(msg)[0] for msg in root.findall('.//TALLYMESSAGE')]
    assert [m.tag for m in objects].index('STOCKGROUP') < [m.tag for m in objects].index('STOCKITEM')
    assert root.findtext('.//STOCKITEM/PARENT') == 'Appliances'

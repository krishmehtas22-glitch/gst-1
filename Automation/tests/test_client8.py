from decimal import Decimal
from pathlib import Path
import shutil
import sqlite3
import json
import xml.etree.ElementTree as ET

from Common_Rules.accounting import legacy_fingerprint
from Common_Rules.desktop import process_sources, save_review
from Common_Rules.engine import read_json

FIXTURES=Path(__file__).parent/'fixtures/client8'


def test_new_uploaded_set_generates_ten_vouchers_in_one_xml(tmp_path):
    folder=tmp_path/'CLIENT 8';folder.mkdir()
    for path in FIXTURES.glob('*.pdf'):shutil.copy2(path,folder/path.name)
    records=process_sources(tmp_path)
    assert len(records)==10 and all(not record['errors'] for record in records)
    companies={Path(record['company_path']) for record in records}
    assert len(companies)==1
    company=companies.pop()
    assert all(record['batch_voucher_count']==10 for record in records)
    vouchers=ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==10
    assert {v.findtext('VOUCHERNUMBER') for v in vouchers}=={f'TEST-26-27-{n:03}' for n in range(1,11)}
    assert sum(Decimal(record['invoice']['total']) for record in records)==Decimal('200934.00')
    normalized=read_json(company/'reports/validated_invoices.json')
    assert len(normalized)==10
    assert all(row['accounting'][1]['ledger']=='Sales' for row in normalized)
    assert sum(Decimal(row['accounting'][1]['credit']) for row in normalized)==Decimal('187800.00')
    assert sum(len(v.findall('ALLINVENTORYENTRIES.LIST')) for v in vouchers)==14
    assert len([v for v in vouchers if v.get('OBJVIEW')=='Accounting Voucher View'])==2
    again=process_sources(tmp_path)
    assert all(not record['errors'] for record in again)
    assert len(read_json(company/'reports/validation.json')['history'])==10
    assert {v.get('REMOTEID') for v in vouchers}=={v.get('REMOTEID') for v in ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')}


def old_history(tmp_path):
    folder=tmp_path/'CLIENT 8';folder.mkdir()
    name='TEST-26-27-001_INTRA.pdf'
    shutil.copy2(Path(__file__).parent/'fixtures/client7'/name,folder/'old.pdf')
    record=process_sources(tmp_path)[0]
    company=Path(record['company_path'])
    with sqlite3.connect(company/'.automation/history.sqlite3') as db:
        key,data=db.execute('SELECT invoice_key,data FROM invoices').fetchone()
        db.execute('UPDATE invoices SET fingerprint=? WHERE invoice_key=?',(legacy_fingerprint(json.loads(data)),key))
    shutil.copy2(FIXTURES/name,folder/'new.pdf')
    return company,folder


def test_revised_pdf_layout_matches_legacy_history_without_duplicate_or_reset(tmp_path):
    company,_=old_history(tmp_path)
    original_config=(company/'client.json').read_bytes()
    records=process_sources(tmp_path)
    assert len(records)==2 and all(not record['errors'] for record in records)
    assert (company/'client.json').read_bytes()==original_config
    assert len(read_json(company/'reports/validation.json')['history'])==1
    assert len(ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER'))==1


def test_changed_accounting_amounts_still_conflict_with_legacy_history(tmp_path):
    _,_=old_history(tmp_path)
    record=next(record for record in process_sources(tmp_path) if Path(record['path']).name=='new.pdf')
    edited=json.loads(json.dumps(record['invoice']))
    item=edited['items'][0]
    item.update(quantity='5',value='12500.00',printed_cgst='1125.00',printed_sgst='1125.00')
    edited.update(taxable='24500.00',cgst='2205.00',sgst='2205.00',total='28910.00')
    save_review(tmp_path,record,edited)
    result=next(record for record in process_sources(tmp_path) if Path(record['path']).name=='new.pdf')
    assert any('transaction details differ' in error for error in result['errors'])


def test_bad_legacy_hash_is_reported_not_trusted(tmp_path):
    company,_=old_history(tmp_path)
    with sqlite3.connect(company/'.automation/history.sqlite3') as db:
        db.execute("UPDATE invoices SET fingerprint='corrupt'")
    records=process_sources(tmp_path)
    assert any('fingerprint does not match' in error for record in records for error in record['errors'])

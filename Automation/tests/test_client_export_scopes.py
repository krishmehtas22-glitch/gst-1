"""Client-folder XML batches share company history without combining invoices."""
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.desktop import process_sources, save_review
from Common_Rules.engine import read_json, write_json, process_client, confirm_import

FIXTURES=Path(__file__).parent/'fixtures'


def install(root):
    for name,source in [('CLIENT 14',FIXTURES/'client11'),('CLIENT 15',FIXTURES/'client15')]:
        folder=root/name;folder.mkdir()
        for path in source.glob('Sales_Invoice*.pdf'):shutil.copy2(path,folder/path.name)
    for record in process_sources(root):
        inv=deepcopy(record['invoice'])
        if record['client']=='CLIENT 15':inv['items'][0]['unit']='KG' if inv['classification']=='exempt' else 'Nos'
        if record['errors']:save_review(root,record,inv)
    return process_sources(root)


def output(records,name):
    return Path(next(r['output_path'] for r in records if r['client']==name))


def numbers(folder):
    return {v.findtext('VOUCHERNUMBER') for v in ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER')}


def test_all_clients_and_single_folder_scans_never_mix_ten_and_fifteen(tmp_path):
    records=install(tmp_path)
    assert len(records)==25 and all(not r['errors'] for r in records)
    assert len({r['company_path'] for r in records})==1
    company=Path(records[0]['company_path']);config=(company/'client.json').read_bytes()
    a=output(records,'CLIENT 14');b=output(records,'CLIENT 15')
    assert a!=b
    assert numbers(a)=={f'DM/26-27/{i:04d}' for i in range(1,11)}
    assert numbers(b)=={f'DM/26-27/{i:04d}' for i in range(11,26)}
    assert {r['batch_voucher_count'] for r in records if r['client']=='CLIENT 14'}=={10}
    assert {r['batch_voucher_count'] for r in records if r['client']=='CLIENT 15'}=={15}
    assert read_json(a/'manifest.json')['source_client']=='CLIENT 14'
    assert read_json(b/'manifest.json')['source_client']=='CLIENT 15'
    assert not (company/'imports/Sales_Vouchers.xml').exists()
    retained_a={p.name:p.read_bytes() for p in a.iterdir()}
    again=process_sources(tmp_path,client_names=['CLIENT 15'])
    assert len(again)==15 and all(not r['errors'] for r in again)
    assert {r['batch_voucher_count'] for r in again}=={15}
    assert numbers(output(again,'CLIENT 15'))==numbers(b)
    assert retained_a=={p.name:p.read_bytes() for p in a.iterdir()}
    assert (company/'client.json').read_bytes()==config
    assert len(read_json(company/'reports/validation.json')['history'])==25
    assert not (company/'imports/Sales_Vouchers.xml').exists()


def test_upgrade_with_existing_mixed_company_xml_preserves_history_and_guids(tmp_path):
    records=install(tmp_path);company=Path(records[0]['company_path'])
    process_client(company.parent,company) # Simulate the older company-wide batch.
    old=ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER');assert len(old)==25
    guids={v.findtext('VOUCHERNUMBER'):v.get('REMOTEID') for v in old}
    config=(company/'client.json').read_bytes()
    updated=process_sources(tmp_path)
    assert not (company/'imports/Sales_Vouchers.xml').exists()
    for name in ('CLIENT 14','CLIENT 15'):
        manifest=read_json(output(updated,name)/'manifest.json')
        assert manifest['valid_for_import'] and manifest['source_client']==name
        for v in ET.parse(output(updated,name)/'Sales_Vouchers.xml').findall('.//VOUCHER'):
            assert v.get('REMOTEID')==guids[v.findtext('VOUCHERNUMBER')]
    assert (company/'client.json').read_bytes()==config
    assert len(read_json(company/'reports/validation.json')['history'])==25


def test_scoped_import_confirmation_preserves_other_client_pending_batch(tmp_path):
    records=install(tmp_path);company=Path(records[0]['company_path']);folder=output(records,'CLIENT 14')
    manifest=read_json(folder/'manifest.json');result=tmp_path/'result.json'
    write_json(result,{'company_id':manifest['company_id'],'generated_at':manifest['generated_at'],
        'export_scope':manifest['export_scope'],'tally_result_reference':'fixture import confirmation',
        'masters':[{'master':m,'status':'imported'} for m in manifest['masters']],
        'vouchers':[{'invoice_key':key,'status':'imported'} for key in manifest['invoice_keys']]})
    history=confirm_import(company,result)
    assert sum(row['status']=='imported' for row in history)==10
    assert sum(row['status']=='generated' for row in history)==15
    updated=process_sources(tmp_path)
    assert all(not r['errors'] for r in updated)
    assert {r['batch_voucher_count'] for r in updated if r['client']=='CLIENT 14'}=={0}
    assert {r['display_status'] for r in updated if r['client']=='CLIENT 14'}=={'Already confirmed imported'}
    assert not (output(updated,'CLIENT 14')/'Sales_Vouchers.xml').exists()
    assert len(numbers(output(updated,'CLIENT 15')))==15


@pytest.mark.parametrize('scope',['../outside','by_client/../../outside','/tmp/outside','by_client\\outside'])
def test_import_scope_cannot_escape_company_directory(tmp_path,scope):
    # Validation precedes reading an attacker-selected manifest.
    records=install(tmp_path);company=Path(records[0]['company_path']);result=tmp_path/'result.json'
    write_json(result,{'export_scope':scope})
    with pytest.raises(ValueError,match='scope'):confirm_import(company,result)

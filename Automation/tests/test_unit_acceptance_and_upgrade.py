from copy import deepcopy
from pathlib import Path
import shutil,json
import pytest
import xml.etree.ElementTree as ET
from Common_Rules.desktop import process_sources
from Common_Rules.unit_choices import save_unit_choices
from Common_Rules.history import History
from Common_Rules.accounting import fingerprint,invoice_key
from helpers import invoice


def test_accept_one_item_then_all_does_not_change_quantity_or_clear_gst_review(tmp_path):
    fixtures=Path(__file__).parent/'fixtures/client22'
    shutil.copytree(fixtures,tmp_path/'Client')
    rows=process_sources(tmp_path)
    before={r['digest']:deepcopy(r['invoice']['items']) for r in rows}
    first=rows[0];unit=first['invoice']['items'][0]['unit']
    save_unit_choices(tmp_path,[(first,0,unit)])
    rows=process_sources(tmp_path)
    assert not rows[0]['invoice']['items'][0]['unit_auto']
    assert all(item['unit_auto'] for r in rows for i,item in enumerate(r['invoice']['items']) if r['digest']!=first['digest'] or i!=0)
    assert sum(not r['errors'] for r in rows)==5  # Missing item GST rates remain unresolved.
    choices=[(r,i,item['unit']) for r in rows for i,item in enumerate(r['invoice']['items'])]
    save_unit_choices(tmp_path,choices)
    confirmed=process_sources(tmp_path)
    assert all(not item['unit_auto'] for r in confirmed for item in r['invoice']['items'])
    assert sum(not r['errors'] for r in confirmed)==5
    for r in confirmed:
        for old,new in zip(before[r['digest']],r['invoice']['items']):
            for field in ('quantity','rate','value'):assert old[field]==new[field]


def test_upgrade_recovers_blank_addresses_without_changing_saved_transactions(tmp_path):
    shutil.copytree(Path(__file__).parent/'fixtures/client17',tmp_path/'Client')
    rows=process_sources(tmp_path);assert all(not r['errors'] for r in rows)
    company=Path(rows[0]['company_path']);history=History(company/'.automation/history.sqlite3')
    # Reader 5.5 left these buyer addresses blank; emulate its retained format.
    for entry in history.statuses():
        data=history.lookup(entry['invoice_key'])['data'];data.pop('buyer_address',None)
        history.db.execute('UPDATE invoices SET data=?,fingerprint=? WHERE invoice_key=?',(json.dumps(data),fingerprint(data),entry['invoice_key']))
    history.db.commit()
    imported=history.statuses()[0]['invoice_key'];history.set_status(imported,'imported')
    before=history.db.execute('SELECT * FROM invoices ORDER BY invoice_key').fetchall()
    output=Path(rows[0]['output_path'])/'Sales_Vouchers.xml'
    guids={v.findtext('VOUCHERNUMBER'):v.findtext('GUID') for v in ET.parse(output).findall('.//VOUCHER')}
    history.close()
    upgraded=process_sources(tmp_path);assert all(not r['errors'] for r in upgraded)
    assert all(any('address metadata' in notice for notice in r.get('notices',[])) for r in upgraded)
    history=History(company/'.automation/history.sqlite3')
    assert history.db.execute('SELECT * FROM invoices ORDER BY invoice_key').fetchall()==before
    assert history.lookup(imported)['status']=='imported'
    assert history.db.execute("SELECT count(*) FROM events WHERE status='metadata_compatible'").fetchone()[0]==8
    history.close()
    for v in ET.parse(output).findall('.//VOUCHER'):assert v.findtext('GUID')==guids[v.findtext('VOUCHERNUMBER')]


@pytest.mark.parametrize('change',['quantity','unit','gst','source','existing_address'])
def test_address_compatibility_never_waives_other_transaction_changes(tmp_path,change):
    history=History(tmp_path/'history.sqlite3')
    saved={**invoice(),'sha256':'same-pdf','source':'invoice.pdf'}
    if change=='existing_address':saved['buyer_address']='Original address'
    key=invoice_key(saved);history.save(key,fingerprint(saved),saved,'generated')
    current=deepcopy(saved);current['buyer_address']='Newly extracted address'
    if change=='quantity':current['items'][0]['quantity']='3'
    if change=='unit':current['items'][0]['unit']='BOX'
    if change=='gst':current['cgst']='999'
    if change=='source':current['sha256']='changed-pdf'
    aligned,_=history.retain_saved_addresses(history.lookup(key),current)
    assert fingerprint(aligned)!=fingerprint(saved)
    assert history.lookup(key)['data']==saved
    history.close()

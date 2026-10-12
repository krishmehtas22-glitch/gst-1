from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3

from Common_Rules.desktop import inspect_sources, process_sources, reset_source_reviews
from Common_Rules.engine import read_json, write_json

FIXTURES=Path(__file__).parent/'fixtures/client8'


def setup(root, names=('CLIENT 9',)):
    for name in names:
        folder=root/name;folder.mkdir()
        for path in FIXTURES.glob('*.pdf'):shutil.copy2(path,folder/path.name)


def stale_review(root,record,baseline=True):
    old=deepcopy(record['source_invoice'])
    for field in ('taxable','total','cgst','sgst','igst','seller_state','buyer_country','export_mode'):
        old.pop(field,None)
    old['items']=[]
    old['extraction_warnings']=['No recognized item rows']
    if old.get('supply')=='EXPORT':old['classification']='export'
    edited=deepcopy(old)
    edited['extraction_warnings']=[]
    for field in ('taxable','total','cgst','sgst','igst','seller_state','buyer_country','export_mode'):
        edited[field]=''
    saved={'source_sha256':record['digest'],'approved':True,'invoice':edited}
    if baseline:saved['original_extraction']=old
    path=root/'.invoice_app/reviews'/(record['digest']+'.json')
    write_json(path,saved)
    return path


def test_reproduced_stale_reviews_refresh_all_detailed_invoices(tmp_path):
    setup(tmp_path,('CLIENT 8','CLIENT 9'))
    records=inspect_sources(tmp_path)
    for record in records[:10]:
        if record['invoice']['number'] not in ('TEST-26-27-005','TEST-26-27-007'):
            stale_review(tmp_path,record)
    refreshed=process_sources(tmp_path)
    assert len(refreshed)==20
    assert all(not record['errors'] for record in refreshed)
    assert all(record['invoice']['total'] for record in refreshed)
    assert all(record['batch_voucher_count']==10 for record in refreshed)
    assert len({record['company_path'] for record in refreshed})==1


def test_refresh_preserves_human_edits_and_accounting_validation(tmp_path):
    setup(tmp_path)
    record=inspect_sources(tmp_path)[0]
    path=stale_review(tmp_path,record)
    saved=read_json(path);saved['invoice']['total']='1.00';write_json(path,saved)
    refreshed=process_sources(tmp_path)[0]
    assert refreshed['invoice']['total']=='1.00'
    assert any('balance' in error for error in refreshed['errors'])


def test_selected_reset_archives_old_reviews_without_touching_history(tmp_path):
    setup(tmp_path)
    records=process_sources(tmp_path)
    record=records[0]
    company=Path(record['company_path'])
    path=stale_review(tmp_path,record,baseline=False)
    review_bytes=path.read_bytes()
    # Simulate a retained confirmed import; reset must leave it confirmed.
    with sqlite3.connect(company/'.automation/history.sqlite3') as db:
        key=db.execute('SELECT invoice_key FROM invoices ORDER BY invoice_key LIMIT 1').fetchone()[0]
        db.execute("UPDATE invoices SET status='imported' WHERE invoice_key=?",(key,))
    history_bytes=(company/'.automation/history.sqlite3').read_bytes()
    config_bytes=(company/'client.json').read_bytes()
    selected=inspect_sources(tmp_path)[0]
    backups=reset_source_reviews(tmp_path,[selected])
    assert not path.exists()
    assert any(Path(backup).read_bytes()==review_bytes for backup in backups)
    assert (company/'.automation/history.sqlite3').read_bytes()==history_bytes
    assert (company/'client.json').read_bytes()==config_bytes
    updated=process_sources(tmp_path)
    assert all(not record['errors'] for record in updated)
    assert updated[0]['display_status']=='Already confirmed imported'


def test_client_selection_leaves_other_source_folders_out(tmp_path):
    setup(tmp_path,('CLIENT 8','CLIENT 9'))
    records=process_sources(tmp_path,client_names=['CLIENT 9'])
    assert len(records)==10 and {record['client'] for record in records}=={'CLIENT 9'}


def test_old_export_review_without_baseline_can_be_reread_safely(tmp_path):
    setup(tmp_path)
    record=inspect_sources(tmp_path)[5]
    stale_review(tmp_path,record,baseline=False)
    before=process_sources(tmp_path)[5]
    assert any('Reviewed export treatment' in error for error in before['errors'])
    reset_source_reviews(tmp_path,[before])
    after=process_sources(tmp_path)[5]
    assert after['errors']==[] and after['invoice']['export_mode']=='LUT_without_payment'

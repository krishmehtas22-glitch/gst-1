"""Optional business-duplicate warning; both uploads/vouchers remain allowed."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import pytest
from test_buyer_ledger_guard import assert_after_guard
from test_review_voucher_structure import record
from Common_Rules.duplicate_invoice_warning import warnings,annotate,PREFIX
from Common_Rules.tally_review_export import export_all


def pair(root):
    first=record(root);second=deepcopy(first)
    second.update(path=str(root/'rescanned.pdf'),digest='f'*64)
    return [first,second]


@pytest.mark.parametrize('field,value',[('seller_gstin','29OTHER'),('seller_name','Another seller'),('buyer_name','Another buyer'),('total','999999')])
def test_only_number_and_date_decide_duplicates(tmp_path,field,value):
    rows=pair(tmp_path);rows[1]['invoice'][field]=value
    assert len(warnings(rows))==2


@pytest.mark.parametrize('field,value',[('number','OTHER-2'),('date','2026-10-18')])
def test_either_number_or_date_difference_is_not_duplicate(tmp_path,field,value):
    rows=pair(tmp_path);rows[1]['invoice'][field]=value
    assert warnings(rows)=={}


@pytest.mark.parametrize('field,value',[('number',''),('date',''),('date','not a date')])
def test_missing_or_invalid_identity_never_matches(tmp_path,field,value):
    rows=pair(tmp_path)
    for row in rows:row['invoice'][field]=value
    assert not warnings(rows)


def test_dates_normalize_and_numbers_keep_punctuation(tmp_path):
    rows=pair(tmp_path);rows[0]['invoice'].update(number='INV/001',date='17/10/2026')
    rows[1]['invoice'].update(number=' inv/001 ',date='2026-10-17')
    assert len(warnings(rows))==2
    rows[1]['invoice']['number']='INV-001'
    assert not warnings(rows)


def test_client_isolation_and_list_only_do_not_read_or_guess(tmp_path):
    rows=pair(tmp_path);rows[1]['client']='Other client'
    assert not warnings(rows)
    rows[1]['client']=rows[0]['client'];rows[1]['listing_only']=True
    assert not warnings(rows)


def test_advisory_clears_after_correction_or_removal_without_mutating_facts(tmp_path):
    rows=pair(tmp_path);facts=deepcopy([r['invoice'] for r in rows]);errors=deepcopy([r['errors'] for r in rows])
    for row in rows:row['notices']=['Retained notice']
    annotate(rows);annotate(rows)
    assert all(len(r['notices'])==2 for r in rows)
    assert [r['invoice'] for r in rows]==facts and [r['errors'] for r in rows]==errors
    annotate(rows[:1]);assert 'duplicate_warning' not in rows[0]
    rows[1]['invoice']['number']='OTHER'
    annotate(rows)
    assert all('duplicate_warning' not in r and r['notices']==['Retained notice'] for r in rows)


def test_both_vouchers_survive_with_warning_and_original_guids(tmp_path):
    rows=pair(tmp_path);facts=deepcopy([r['invoice'] for r in rows])
    export_all(tmp_path,rows,False);folder=Path(rows[0]['output_path'])
    vouchers=ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==2
    guids=[v.findtext('GUID') for v in vouchers];assert len(set(guids))==2
    assert all(PREFIX in v.findtext('NARRATION') for v in vouchers)
    report=json.loads((folder/'Batch_Report.json').read_text())
    assert report['input_count']==report['xml_voucher_count']==2
    assert all(any(n.startswith(PREFIX) for n in r['warnings']) for r in report['invoices'])
    assert [r['invoice'] for r in rows]==facts
    export_all(tmp_path,rows,False)
    assert [v.findtext('GUID') for v in ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER')]==guids


def test_current_upload_keeps_rescanned_pdf_bytes(tmp_path):
    from pypdf import PdfReader,PdfWriter
    from Document_Upload import upload_documents
    source=next((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))
    first=tmp_path/'original.pdf';first.write_bytes(source.read_bytes())
    second=tmp_path/'rescan.pdf';writer=PdfWriter()
    for page in PdfReader(first).pages:writer.add_page(page)
    writer.add_metadata({'/Title':'Same invoice, different PDF metadata'})
    with second.open('wb') as file:writer.write(file)
    assert first.read_bytes()!=second.read_bytes()
    report=upload_documents(tmp_path/'app','Client',[first,second])
    assert len(report['uploaded'])==2 and not report['errors']
    assert first.is_file() and second.is_file()


def test_warning_change_has_backup_and_preserves_frozen_currency_quantity_code():
    repo=Path(__file__).parents[2];change=json.loads((repo/'Automation/DUPLICATE_WARNING_CHANGE.json').read_text())
    with zipfile.ZipFile(repo/change['backup']) as z:
        for name,values in change['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==values['baseline_sha256']
            assert_after_guard(repo,name,values['authorized_sha256'])
    locked=json.loads((repo/'Automation/QUANTITY_PRECISION_CHANGE.json').read_text())
    for name,digest in locked['currency_lock'].items():
        if name not in change['files']:assert_after_guard(repo,name,digest)


def exercise_duplicate_warning_ui(root,app,tmp_path):
    rows=pair(tmp_path);app.records=rows
    app.filter_status.set('All statuses');app.search.set('');app.apply_filter();app.update_summary();root.update()
    assert all(app.table.set(str(i),'status')=='Duplicate invoice — review' for i in range(2))
    assert all('duplicate' in app.table.item(str(i),'tags') for i in range(2))
    app.filter_status.set('Needs review');root.update()
    assert len(app.table.get_children())==2
    app.table.selection_set('0');app.details();root.update()
    assert PREFIX in app.detail.get('1.0','end')
    assert app.count_labels[2].cget('text')=='2'
    rows[1]['invoice']['number']='OTHER-1'
    app.apply_filter();root.update()
    assert all('duplicate_warning' not in row for row in rows)
    assert not app.table.get_children()
    app.filter_status.set('All statuses');root.update()
    assert len(app.table.get_children())==2

import hashlib
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from pypdf import PdfWriter
from helpers import invoice

from Common_Rules.desktop import inspect_sources, process_sources, save_review
from Common_Rules.engine import init_demo_client, read_json, run
from Common_Rules.extraction import parse_text, text_from_pdf

FIXTURES = Path(__file__).parent/'fixtures/client7'


def setup_files(root):
    folder = root/'CLIENT 7'
    folder.mkdir()
    for path in FIXTURES.glob('*.pdf'):
        shutil.copy2(path,folder/path.name)
    return folder


def test_ten_uploaded_pdfs_eight_domestic_vouchers_three_sellers(tmp_path):
    folder = setup_files(tmp_path)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.pdf')}
    records = process_sources(tmp_path)
    assert len(records) == 10
    accepted = [r for r in records if not r['errors']]
    assert len(accepted) == 8
    rejected = [r for r in records if r['errors']]
    assert all('EXPORT' in Path(r['path']).name for r in rejected)
    companies = {Path(r['company_path']) for r in accepted}
    assert len(companies) == 3
    vouchers = []
    for company in companies:
        config = read_json(company/'client.json')
        assert config['demo_profile']['version'] == 2
        assert config['source_seller_gstin'].startswith(('24','27'))
        doc = ET.parse(company/'imports/Sales_Vouchers.xml')
        vouchers.extend(doc.findall('.//VOUCHER'))
        assert read_json(company/'imports/manifest.json')['valid_for_import'] is True
    assert len(vouchers) == 8
    assert sum(len(v.findall('ALLINVENTORYENTRIES.LIST')) for v in vouchers) == 14
    assert {v.findtext('VOUCHERNUMBER') for v in vouchers} == {r['invoice']['number'] for r in accepted}
    assert all(v.findtext('PLACEOFSUPPLY') != 'Outside India' for v in vouchers)
    original_configs = {str(p): (p/'client.json').read_bytes() for p in companies}
    again = process_sources(tmp_path)
    assert sum(not r['errors'] for r in again) == 8
    assert original_configs == {str(p): (p/'client.json').read_bytes() for p in companies}
    assert hashes == {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.pdf')}
    assert not (folder/'client.json').exists()


def test_exports_keep_details_for_inspection_without_xml(tmp_path):
    folder = setup_files(tmp_path)
    records = inspect_sources(tmp_path)
    exports = [r for r in records if 'EXPORT' in r['path']]
    assert len(exports) == 2
    assert {r['invoice']['buyer_country'] for r in exports} == {'UAE','USA'}
    assert {r['invoice']['total'] for r in exports} == {'30000.00','45000.00'}
    assert all(r['invoice']['items'] and r['errors'] for r in exports)


def test_digest_bound_review_corrects_and_revalidates(tmp_path):
    setup_files(tmp_path)
    record = inspect_sources(tmp_path)[0]
    edited = dict(record['invoice'])
    edited['total'] = '25961.00'
    save_review(tmp_path,record,edited)
    report = process_sources(tmp_path)[0]
    assert any('balance' in error for error in report['errors'])
    save_review(tmp_path,record,record['invoice'])
    assert process_sources(tmp_path)[0]['errors'] == []
    Path(record['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed'):
        save_review(tmp_path,record,edited)


def test_real_mode_never_silently_processes_fictional_pdfs(tmp_path):
    setup_files(tmp_path)
    records = process_sources(tmp_path,demo=False)
    assert all(r['errors'] for r in records)
    assert not list((tmp_path/'.invoice_app/companies').glob('*/imports/*.xml'))


def test_review_cannot_move_previously_processed_invoice_to_other_seller(tmp_path):
    setup_files(tmp_path)
    record = process_sources(tmp_path)[0]
    edited = dict(record['invoice'])
    edited['seller_gstin'] = '27DEMOB2000B1Z5'
    edited['seller_name'] = 'Deccan Industrial Traders'
    save_review(tmp_path,record,edited)
    report = process_sources(tmp_path)[0]
    assert any('already belongs' in error for error in report['errors'])


def test_wrapped_igst_digits_extracted_exactly():
    for name,amount in [('TEST-26-27-004_INTER.pdf','1224.00'),('TEST-26-27-009_INTER.pdf','3300.00')]:
        raw = parse_text(text_from_pdf(FIXTURES/name))
        assert raw['items'][0]['printed_igst'] == amount
        assert raw['extraction_warnings'] == []


def test_export_cannot_be_approved_as_domestic_by_editing_treatment(tmp_path):
    setup_files(tmp_path)
    record = next(r for r in inspect_sources(tmp_path) if '005_EXPORT' in r['path'])
    edited = dict(record['invoice'])
    edited.update(supply='INTRA',classification='taxable',extraction_warnings=[])
    save_review(tmp_path,record,edited)
    report = next(r for r in process_sources(tmp_path) if '005_EXPORT' in r['path'])
    assert any('export-specific' in error for error in report['errors'])
    assert not report.get('company_path')


def test_legacy_watcher_does_not_merge_multiple_sellers(tmp_path):
    client = init_demo_client(tmp_path,'CLIENT 7','CLIENT 7','Maharashtra','Nos')
    for name in ('TEST-26-27-001_INTRA.pdf','TEST-26-27-002_INTRA.pdf'):
        shutil.copy2(FIXTURES/name,client/name)
    report = run(tmp_path)['clients'][0]
    assert 'Multiple sellers' in report['error']
    assert not (client/'imports/Sales_Vouchers.xml').exists()


def test_unreadable_text_can_be_manually_reviewed_without_bypassing_validation(tmp_path):
    folder = tmp_path/'Scanned client'
    folder.mkdir()
    path = folder/'scan.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=600,height=800)
    with path.open('wb') as stream:
        writer.write(stream)
    record = inspect_sources(tmp_path)[0]
    assert record['errors'] and record['digest']
    save_review(tmp_path,record,invoice())
    result = process_sources(tmp_path,demo=False)[0]
    assert result['errors'] == []
    assert result['export'].startswith('Generated 1')

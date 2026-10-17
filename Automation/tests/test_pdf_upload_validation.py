"""Actual damaged PDFs and existing readers; no OCR/AI in the upload check."""
from io import BytesIO
from pathlib import Path
import ast,hashlib,json,runpy,zipfile
import pytest
from pypdf import PdfWriter,PdfReader
from pypdf.generic import NameObject,IndirectObject,NullObject
from Document_Upload import upload_documents
from PDF_Upload_Validation import validate_pdf


def valid_pdf():
    return next((Path(__file__).parent/'fixtures/client23').glob('*.pdf')).read_bytes()


def write_pdf(writer):
    output=BytesIO();writer.write(output);return output.getvalue()


def damaged(kind):
    if kind=='header_only':return b'%PDF-1.7\nnot a PDF object tree or trailer'
    if kind=='truncated':return valid_pdf()[:len(valid_pdf())//2]
    if kind=='fake_type':return b'%PDF-1.4\n<html>not a PDF</html>'
    writer=PdfWriter()
    if kind=='zero_pages':return write_pdf(writer)
    writer.add_blank_page(width=595,height=842)
    if kind=='encrypted':writer.encrypt('private-test-password');return write_pdf(writer)
    if kind=='broken_second_page':
        page=writer.add_blank_page(width=595,height=842)
        page[NameObject('/Contents')]=IndirectObject(9999,0,writer)
        return write_pdf(writer)
    raise AssertionError(kind)


@pytest.mark.parametrize('kind',['header_only','truncated','fake_type','zero_pages','encrypted','broken_second_page'])
def test_invalid_pdf_is_rejected_before_storage_without_mutating_source(tmp_path,kind):
    source=tmp_path/'bad.pdf';raw=damaged(kind);source.write_bytes(raw)
    report=upload_documents(tmp_path/'app','Client',[source])
    assert len(report['errors'])==1 and not report['uploaded'] and not report['reused']
    error=report['errors'][0]['error'].casefold()
    assert any(word in error for word in ('damaged','unreadable','password','no pages'))
    assert source.read_bytes()==raw
    assert not list((tmp_path/'app').rglob('*.pdf'))
    assert not list((tmp_path/'app').rglob('*.xml'))


@pytest.mark.parametrize('order',['bad_first','good_first'])
def test_mixed_upload_keeps_good_pdf_and_reports_only_bad_file(tmp_path,order):
    good=tmp_path/'good.pdf';good.write_bytes(valid_pdf())
    bad=tmp_path/'bad.pdf';bad.write_bytes(damaged('header_only'))
    report=upload_documents(tmp_path/'app','Client',[bad,good] if order=='bad_first' else [good,bad])
    assert len(report['uploaded'])==len(report['errors'])==1
    assert report['errors'][0]['name']=='bad.pdf'
    assert Path(report['uploaded'][0]['path']).read_bytes()==good.read_bytes()


def test_upload_validation_does_not_extract_text_or_call_ocr_or_ai(tmp_path,monkeypatch):
    from Common_Rules import groq_reader,ai_first,desktop,ocr
    def blocked(*args,**kwargs):pytest.fail('Upload validation cannot analyse invoices')
    monkeypatch.setattr(PdfReader,'decrypt',blocked)
    from pypdf._page import PageObject
    monkeypatch.setattr(PageObject,'extract_text',blocked)
    monkeypatch.setattr(groq_reader,'request_invoice',blocked)
    monkeypatch.setattr(ai_first,'run_ai_first',blocked)
    monkeypatch.setattr(desktop,'process_sources',blocked)
    monkeypatch.setattr(ocr,'read_page',blocked)
    # OCR entrypoint name is verified from the module, without initializing models.
    for name in ('ocr_pdf','text_from_pdf','read_pdf'):
        if hasattr(ocr,name):monkeypatch.setattr(ocr,name,blocked)
    source=tmp_path/'valid.pdf';source.write_bytes(valid_pdf())
    report=upload_documents(tmp_path/'app','Client',[source])
    assert len(report['uploaded'])==1 and not report['errors']


def test_valid_multipage_document_and_blank_pages_are_readable(tmp_path):
    writer=PdfWriter();writer.append(PdfReader(BytesIO(valid_pdf())))
    blank=writer.add_blank_page(width=595,height=842);blank[NameObject('/Contents')]=NullObject()
    raw=write_pdf(writer);source=tmp_path/'multipage.pdf';source.write_bytes(raw)
    report=upload_documents(tmp_path/'app','Client',[source])
    assert not report['errors'];target=Path(report['uploaded'][0]['path'])
    assert target.read_bytes()==raw and len(PdfReader(target).pages)==2


def test_all_existing_pdf_fixture_layouts_remain_readable():
    fixtures=list((Path(__file__).parent/'fixtures').glob('**/*.pdf'))
    assert len(fixtures)>100
    for path in fixtures:validate_pdf(path.read_bytes())


def test_later_page_render_failure_closes_resources_and_keeps_other_files(tmp_path,monkeypatch):
    import pypdfium2 as pdfium
    original=pdfium.PdfPage.render;calls=[]
    def fail_second(page,*args,**kwargs):
        calls.append(page)
        if len(calls)==2:raise RuntimeError('Controlled unreadable second page')
        return original(page,*args,**kwargs)
    monkeypatch.setattr(pdfium.PdfPage,'render',fail_second)
    writer=PdfWriter();writer.add_blank_page(width=595,height=842);writer.add_blank_page(width=595,height=842)
    bad=tmp_path/'two_pages.pdf';bad.write_bytes(write_pdf(writer))
    good=tmp_path/'good.pdf';good.write_bytes(valid_pdf())
    report=upload_documents(tmp_path/'app','Client',[bad,good])
    assert len(report['uploaded'])==len(report['errors'])==1 and len(calls)==3
    assert all(not page.raw for page in calls)


def test_original_image_conversion_function_is_identical_to_backup():
    repo=Path(__file__).parents[2]
    with zipfile.ZipFile(repo/'Backups/Before_PDF_Upload_Validation.zip') as z:old=z.read('Automation/Document_Upload.py').decode()
    new=(repo/'Automation/Document_Upload.py').read_text()
    def image_tree(code):return ast.dump(next(n for n in ast.parse(code).body if isinstance(n,ast.FunctionDef) and n.name=='image_pdf'))
    assert image_tree(old)==image_tree(new)


def test_installer_supports_original_and_updated_adapters_and_rejects_unknown(tmp_path):
    repo=Path(__file__).parents[2];installer=runpy.run_path(str(repo/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(repo/'Backups/Reader_Before_BillSync_UI.zip') as z:
        for name in z.namelist():
            if name.startswith('Automation/') and not name.endswith('/'):
                target=tmp_path/name.removeprefix('Automation/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
    with zipfile.ZipFile(repo/'Backups/Before_PDF_Upload_Validation.zip') as z:
        (tmp_path/'Document_Upload.py').write_bytes(z.read('Automation/Document_Upload.py').replace(b'\n',b'\r\n'))
    backup=installer['install'](tmp_path)
    assert (backup/'Document_Upload.py').is_file()
    assert (tmp_path/'PDF_Upload_Validation.py').read_text()==installer['FILES']['PDF_Upload_Validation.py']
    installer['install'](tmp_path)
    target=tmp_path/'Document_Upload.py';target.write_bytes(target.read_bytes()+b'\n# unknown local edits\n')
    before=target.read_bytes()
    with pytest.raises(ValueError,match='No files changed'):installer['install'](tmp_path)
    assert target.read_bytes()==before


def test_backup_and_new_adapter_hash_are_recorded_without_replacing_original():
    repo=Path(__file__).parents[2];change=json.loads((repo/'Automation/PDF_UPLOAD_VALIDATION_CHANGE.json').read_text())
    with zipfile.ZipFile(repo/change['backup']) as z:
        for name,entry in change['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==entry['baseline_sha256']
            ocr=json.loads((repo/'Automation/OCR_REVIEW_GUARD_CHANGE.json').read_text())
            expected=entry['authorized_sha256']
            if name in ocr['files']:
                replacement=ocr['files'][name];assert replacement['baseline_sha256']==expected
                with zipfile.ZipFile(repo/ocr['backup']) as later:assert hashlib.sha256(later.read(name)).hexdigest()==expected
                expected=replacement['authorized_sha256']
            premium=json.loads((repo/'Automation/PREMIUM_UI_CHANGE.json').read_text())
            if name in premium['files']:
                replacement=premium['files'][name];assert replacement['baseline_sha256']==expected
                with zipfile.ZipFile(repo/premium['backup']) as later:assert hashlib.sha256(later.read(name)).hexdigest()==expected
                expected=replacement['authorized_sha256']
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==expected
    original=json.loads((repo/'Automation/APPROVED_UI_DESIGN_LOCK.json').read_text())
    # The old design manifest remains historical; the PDF-only exception is separate.
    assert change['files']['Automation/Document_Upload.py']['baseline_sha256']=='160d68558971760e74e169caf29de33dbe3b62aef85e5e1a6320efb47665835b'
    assert original['format_audit_baseline']['Automation/Document_Upload.py']==change['files']['Automation/Document_Upload.py']['baseline_sha256']

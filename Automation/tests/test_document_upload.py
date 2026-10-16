from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil

import pytest
from PIL import Image
from pypdf import PdfReader

from Document_Upload import upload_documents,client_folder
from Common_Rules.invoice_queue import list_sources


@pytest.mark.parametrize('suffix',['png','jpg','jpeg'])
def test_image_upload_makes_one_deterministic_pdf_and_retains_original(tmp_path,suffix):
    source=tmp_path/f'invoice.{suffix}';Image.new('RGB',(120,240),'white').save(source)
    original=source.read_bytes();root=tmp_path/'app';root.mkdir()
    report=upload_documents(root,'Client',[source])
    assert not report['errors'] and len(report['uploaded'])==1
    target=Path(report['uploaded'][0]['path']);pdf=PdfReader(target)
    assert len(pdf.pages)==1
    assert float(pdf.pages[0].mediabox.width)==120 and float(pdf.pages[0].mediabox.height)==240
    stored=next((root/'.invoice_app/original_uploads').iterdir());assert stored.read_bytes()==original
    assert source.read_bytes()==original
    assert upload_documents(root,'Client',[source])['reused'][0]['path']==str(target)
    assert len(list_sources(root))==1
    assert not list(root.rglob('*Vouchers.xml'))


def test_pdf_upload_is_byte_identical_and_same_named_different_files_are_preserved(tmp_path):
    fixture=next((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))
    source=tmp_path/'source/invoice.pdf';source.parent.mkdir();shutil.copyfile(fixture,source)
    root=tmp_path/'app';root.mkdir()
    first=upload_documents(root,'Client',[source])
    path=Path(first['uploaded'][0]['path']);assert path.read_bytes()==source.read_bytes()
    original=path.read_bytes();source.write_bytes(original+b'\n%new source version\n')
    second=upload_documents(root,'Client',[source])
    assert second['uploaded'][0]['path']!=str(path) and path.read_bytes()==original
    assert len(list_sources(root))==2


@pytest.mark.parametrize('name',['../escape','.invoice_app','All clients','CON','Client/2','bad:name'])
def test_client_names_cannot_escape_or_use_reserved_folders(tmp_path,name):
    with pytest.raises(ValueError):client_folder(tmp_path,name,create=True)


def test_intake_never_calls_ai_or_creates_xml(tmp_path,monkeypatch):
    from Common_Rules import ai_first,desktop,groq_reader
    for module,name in [(ai_first,'run_ai_first'),(desktop,'process_sources'),(groq_reader,'request_invoice')]:
        monkeypatch.setattr(module,name,lambda *a,**kw:pytest.fail('Upload must not process invoices'))
    source=tmp_path/'a.pdf';source.write_bytes(b'%PDF-1.4\nfixture bytes only')
    result=upload_documents(tmp_path/'app','Client',[source])
    assert len(result['uploaded'])==1
    assert not list((tmp_path/'app').rglob('*.xml'))


def test_bad_files_are_reported_without_losing_valid_upload(tmp_path):
    bad=tmp_path/'bad.png';bad.write_bytes(b'not a PNG')
    good=tmp_path/'good.pdf';good.write_bytes(b'%PDF-1.4\n')
    result=upload_documents(tmp_path/'app','Client',[bad,good])
    assert len(result['errors'])==1 and len(result['uploaded'])==1


def test_upload_reuses_existing_client_pdf_without_changing_its_path_or_hash(tmp_path):
    root=tmp_path/'app';client_folder(root,'Client',create=True)
    original=root/'Client/existing.pdf';original.write_bytes(b'%PDF-1.4\noriginal invoice')
    source=tmp_path/'new-name.pdf';source.write_bytes(original.read_bytes())
    result=upload_documents(root,'Client',[source])
    assert not result['uploaded'] and result['reused'][0]['path']==str(original)
    assert len(list_sources(root))==1

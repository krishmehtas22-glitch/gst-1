from pathlib import Path
import shutil
import pytest
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import pypdfium2 as pdfium

from Common_Rules.desktop import inspect_sources, process_sources, save_review
from Common_Rules.extraction import parse_text, text_from_pdf
from helpers import gstin


def alternate_text():
    return f'''SUPPLIER
Example Seller
GSTIN: {gstin()}
State: Maharashtra

BILL TO
Example Buyer
GSTIN: Unregistered
State: Maharashtra
Registration type: Unregistered

Inv No.: NEW-001    Dated: 12 October 2026
Place of Supply: Maharashtra
Net taxable value: 2000
CGST: 180
SGST: 180
IGST: 0
Grand Total: 2360
HSN | Description of Goods | Qty. | UOM | Unit Rate | Taxable Amount | GST % | CGST Amount | SGST Amount | IGST Amount
8418 | Widget | 2 | Nos | 1000 | 2000 | 18% | 180 | 180 | 0
'''


def test_alternative_labels_party_blocks_and_reordered_columns_end_to_end(tmp_path):
    folder=tmp_path/'Client';folder.mkdir()
    pdf=canvas.Canvas(str(folder/'invoice.pdf'))
    pdf.setFont('Courier',6)
    for index,line in enumerate(alternate_text().splitlines()):
        pdf.drawString(20,800-index*20,line)
    pdf.save()
    record=process_sources(tmp_path,demo=False)[0]
    assert record['errors']==[]
    assert record['export'].startswith('Generated 1')
    assert record['invoice']['number']=='NEW-001'
    assert record['invoice']['date']=='2026-10-12'
    assert record['invoice']['buyer_gstin']==''
    assert record['invoice']['items'][0]['cgst_rate']=='9'


@pytest.mark.parametrize('before,after',[
    ('18% | 180','17% | 180'),
    ('CGST Amount | SGST Amount','SGST Amount | CGST Amount'),
])
def test_printed_component_amounts_checked(before,after):
    modified=alternate_text().replace(before,after)
    if before.startswith('CGST Amount'):
        modified=modified.replace('| 180 | 180 | 0','| 170 | 190 | 0')
    assert parse_text(modified)['extraction_warnings']


def test_inline_pairs_and_standalone_labels():
    raw=parse_text(alternate_text().replace('Inv No.: NEW-001    Dated: 12 October 2026',
        'Invoice number:\nNEW-001\nInvoice Date:\n12/10/2026'))
    assert raw['number']=='NEW-001' and raw['date']=='2026-10-12'
    assert raw['seller_gstin']==gstin()


def test_image_only_pdf_ocr_requires_review_then_can_generate(tmp_path):
    folder=tmp_path/'Scanned client';folder.mkdir()
    source=Path(__file__).parent/'fixtures/client7/TEST-26-27-001_INTRA.pdf'
    path=folder/'scanned.pdf'
    with pdfium.PdfDocument(str(source)) as doc:
        page=doc[0];bitmap=page.render(scale=3)
        try:
            image=bitmap.to_pil().copy()
            pdf=canvas.Canvas(str(path),pagesize=(page.get_width(),page.get_height()))
            pdf.drawImage(ImageReader(image),0,0,width=page.get_width(),height=page.get_height())
            pdf.save()
        finally:
            bitmap.close();page.close()
    record=process_sources(tmp_path)[0]
    assert record['invoice']['source_ocr'] is True
    assert record['invoice']['number']=='TEST-26-27-001'
    assert record['invoice']['total']=='25960.00'
    assert len(record['invoice']['items'])==2
    assert record['errors'] and not record.get('company_path')
    # Confirm source values against the text original, correcting OCR names.
    checked=parse_text(text_from_pdf(source));checked['source_ocr']=True
    save_review(tmp_path,record,checked)
    reviewed=process_sources(tmp_path)[0]
    assert reviewed['errors']==[]
    assert reviewed['export'].startswith('Generated 1')


def test_cached_extraction_is_not_repeated_for_unchanged_pdf(tmp_path,monkeypatch):
    folder=tmp_path/'Client';folder.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/client7/TEST-26-27-001_INTRA.pdf',folder/'one.pdf')
    first=inspect_sources(tmp_path)
    def unexpected(*args):
        raise AssertionError('Unchanged source should use cached extraction')
    monkeypatch.setattr('Common_Rules.desktop.text_from_pdf',unexpected)
    second=inspect_sources(tmp_path)
    assert first==second

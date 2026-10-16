"""Actual local OCR and Groq-input preparation across supported upload formats.

No provider requests or Tally operations are performed. These verify document
reading, not AI response accuracy on arbitrary invoices.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas
import pytest

from Document_Upload import upload_documents, image_pdf
from Common_Rules.groq_reader import prepare_invoice_payload
from Common_Rules.invoice_queue import list_sources
from Common_Rules.ocr import MARKER


def invoice_pdf():
    output=BytesIO();canvas=Canvas(output,pagesize=(420,594),invariant=1)
    canvas.setFont('Helvetica',14)
    lines=['SALES INVOICE', 'Invoice Number: INV-2026-123', 'Date: 16 October 2026',
           'Seller: Acme Trade Supplies', 'Buyer: North Office Stores',
           'Description     Quantity    Unit     Rate       Amount',
           'Cable                10       PCS    100.00    1000.00',
           'Taxable Amount: 1000.00', 'CGST: 90.00', 'SGST: 90.00',
           'Invoice Total: 1180.00']
    for index,line in enumerate(lines):canvas.drawString(20,560-index*32,line)
    canvas.showPage();canvas.save();return output.getvalue()


def raster(data):
    with pdfium.PdfDocument(data) as doc:
        page=doc[0];bitmap=page.render(scale=2)
        try:return bitmap.to_pil().convert('RGB').copy()
        finally:bitmap.close();page.close()


@pytest.mark.parametrize('kind',['pdf','scanned_pdf','png','jpg','jpeg','rotated_jpeg','cmyk_jpeg','gray_jpeg'])
def test_supported_formats_reach_the_real_groq_input_with_readable_facts(tmp_path,monkeypatch,kind):
    from Common_Rules import groq_reader
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *args,**kw:pytest.fail('No AI requests are permitted in format verification'))
    source=tmp_path/'source';source.mkdir()
    raw=invoice_pdf();upright=raster(raw)
    if kind=='pdf':
        path=source/'invoice.PDF';path.write_bytes(raw)
    elif kind=='scanned_pdf':
        png=BytesIO();upright.save(png,format='PNG')
        path=source/'scan.pdf';path.write_bytes(image_pdf(png.getvalue()))
    else:
        suffix='png' if kind=='png' else 'JPG' if kind=='jpg' else 'JPEG'
        path=source/('invoice.'+suffix)
        image=upright
        options={}
        if kind=='rotated_jpeg':
            image=upright.transpose(Image.Transpose.ROTATE_90)
            exif=Image.Exif();exif[274]=6;options['exif']=exif
        elif kind=='cmyk_jpeg':image=upright.convert('CMYK')
        elif kind=='gray_jpeg':image=upright.convert('L')
        image.save(path,format='PNG' if kind=='png' else 'JPEG',quality=95,**options)
    original=path.read_bytes();root=tmp_path/'app'
    report=upload_documents(root,'Format test',[path])
    assert not report['errors'] and len(report['uploaded'])==1
    target=Path(report['uploaded'][0]['path'])
    assert path.read_bytes()==original
    reader=PdfReader(target);assert len(reader.pages)==1
    if kind in ('pdf','scanned_pdf'):assert target.read_bytes()==original
    else:
        assert float(reader.pages[0].mediabox.width)==upright.width
        assert float(reader.pages[0].mediabox.height)==upright.height
        retained=list((root/'.invoice_app/original_uploads').iterdir())
        assert len(retained)==1 and retained[0].read_bytes()==original
    records=list_sources(root)
    assert len(records)==1 and records[0]['listing_only']
    # The exact existing input-preparation function performs real OCR when needed.
    payload=prepare_invoice_payload({'path':str(target),'digest':sha256(target.read_bytes()).hexdigest()},'local-format-check')
    text=payload['messages'][1]['content']
    normalized=re.sub(r'[\s,]+','',text).casefold()
    for fact in ('INV-2026-123','Acme Trade Supplies','North Office Stores','Cable','PCS','1000.00','1180.00'):
        assert re.sub(r'\s+','',fact).casefold() in normalized,(kind,fact,text)
    assert (MARKER in text)==(kind!='pdf')
    assert upload_documents(root,'Format test',[path])['reused'][0]['path']==str(target)
    assert not list(root.rglob('*.xml'))


def test_multipage_pdf_keeps_both_pages_and_printed_text(tmp_path):
    from pypdf import PdfWriter
    from Common_Rules.extraction import text_from_pdf
    writer=PdfWriter();writer.append(PdfReader(BytesIO(invoice_pdf())))
    continuation=BytesIO();canvas=Canvas(continuation,pagesize=(420,594),invariant=1)
    canvas.drawString(20,550,'Invoice INV-2026-123 continued: delivery to North Office Stores.')
    canvas.showPage();canvas.save();writer.append(PdfReader(BytesIO(continuation.getvalue())))
    source=tmp_path/'two_pages.pdf'
    with source.open('wb') as stream:writer.write(stream)
    before=source.read_bytes();root=tmp_path/'app'
    report=upload_documents(root,'Client',[source])
    target=Path(report['uploaded'][0]['path'])
    assert target.read_bytes()==before and len(PdfReader(target).pages)==2
    assert 'delivery to North Office Stores' in text_from_pdf(target)

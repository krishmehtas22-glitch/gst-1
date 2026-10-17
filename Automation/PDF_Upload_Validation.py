"""Local PDF readability check only; no OCR, invoice reading or rewriting."""
from io import BytesIO
from contextlib import closing
import math


class PDFUploadError(ValueError):
    pass


def validate_pdf(data):
    if b'%PDF-' not in data[:1024]:raise PDFUploadError('This file is not a valid PDF document.')
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject,StreamObject,NullObject
    import pypdfium2 as pdfium
    try:
        reader=PdfReader(BytesIO(data),strict=False)
        if reader.is_encrypted:
            raise PDFUploadError('Password-protected PDF. Save an unlocked copy and upload it again.')
        count=len(reader.pages)
        if count==0:raise PDFUploadError('This PDF has no pages. Upload a readable invoice PDF.')
        for page in reader.pages:
            if page.get('/Type')!='/Page':raise PDFUploadError('Damaged PDF page structure. Export or scan a fresh copy.')
            if '/Contents' in page:
                content=page.raw_get('/Contents').get_object()
                streams=[] if isinstance(content,NullObject) else content if isinstance(content,ArrayObject) else [content]
                if any(not isinstance(stream.get_object() if stream is not None else None,StreamObject) for stream in streams):
                    raise PDFUploadError('Damaged PDF page content. Export or scan a fresh copy.')
        # A page tree can parse even when a page cannot load/render. Check every
        # page using a small bounded preview, without extracting text or doing OCR.
        with pdfium.PdfDocument(data) as document:
            if len(document)!=count:raise PDFUploadError('Damaged PDF page list. Export or scan a fresh copy.')
            for index in range(count):
                with closing(document[index]) as page:
                    width,height=page.get_size()
                    if not all(math.isfinite(value) and value>0 for value in (width,height)):
                        raise PDFUploadError('This PDF has an unreadable page size. Export a fresh copy.')
                    with closing(page.render(scale=min(1,256/max(width,height)))) as bitmap:
                        if bitmap.width<=0 or bitmap.height<=0:raise PDFUploadError('This PDF contains an unreadable page. Export a fresh copy.')
    except PDFUploadError:raise
    except Exception as exc:
        raise PDFUploadError('Damaged or unreadable PDF. It was not uploaded. Export or scan a fresh copy and try again.') from exc

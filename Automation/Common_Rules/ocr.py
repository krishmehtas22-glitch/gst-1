"""Local OCR for image-only PDF pages; every OCR result requires review."""
from statistics import median
import threading

MARKER = 'OCR EXTRACTED TEXT - MANUAL VERIFICATION REQUIRED'
_engine = None
_lock = threading.Lock()


def rows_from_boxes(results):
    rows = []
    ordered = sorted(results,key=lambda item:sum(p[1] for p in item[0])/4)
    for box,text,confidence in ordered:
        left,right = min(p[0] for p in box),max(p[0] for p in box)
        top,bottom = min(p[1] for p in box),max(p[1] for p in box)
        middle = (top+bottom)/2
        row = next((row for row in reversed(rows) if abs(row['y']-middle)<max(row['height'],bottom-top)*.45),None)
        if row is None:
            row = {'y':middle,'height':bottom-top,'parts':[]}
            rows.append(row)
        row['parts'].append((left,right,text,float(confidence)))
    lines = []
    for row in rows:
        parts = sorted(row['parts'])
        char_width = max(3,median((right-left)/max(len(text),1) for left,right,text,_ in parts))
        line,end = '',0
        for left,right,text,_ in parts:
            spaces = max(2,round((left-end)/char_width)) if line else 0
            line += ' '*spaces+text
            end = right
        lines.append(line)
    return '\n'.join(lines)


def read_page(path,index):
    try:
        import pypdfium2 as pdfium
        import onnxruntime
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise ValueError('Scanned PDF needs the OCR dependencies. Start Open_Invoice_App.bat to install them, or enter the invoice through Review.') from exc
    global _engine
    with _lock:
        if _engine is None:
            onnxruntime.disable_telemetry_events()
            _engine = RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
        with pdfium.PdfDocument(str(path)) as document:
            page = document[index]
            bitmap = page.render(scale=3)
            try:
                image = bitmap.to_numpy().copy()
                results,_ = _engine(image)
            finally:
                bitmap.close()
                page.close()
        return rows_from_boxes(results or [])

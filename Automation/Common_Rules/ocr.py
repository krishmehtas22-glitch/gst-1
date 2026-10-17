"""Local OCR for image-only PDF pages; every OCR result requires review."""
from statistics import median
import threading
import math,re,json

MARKER = 'OCR EXTRACTED TEXT - MANUAL VERIFICATION REQUIRED'
_engine = None
_lock = threading.Lock()


class OCRText(str):
    def __new__(cls,text,evidence=()):
        value=super().__new__(cls,text);value.ocr_evidence=list(evidence);return value


class OCRPayload(dict):
    """Evidence is a local attribute, not an extra provider API JSON field."""
    pass


def suspect(text,confidence):
    reasons=[]
    if not math.isfinite(float(confidence)) or float(confidence)<.92:reasons.append('low OCR confidence')
    words=re.findall(r'\b[A-Za-z01]+\b',str(text))
    if any(sum(c.isalpha() for c in word)>=3 and any(c.islower() for c in word) and any(c in '01' for c in word) for word in words):
        reasons.append('possible letter/digit confusion')
    return ', '.join(reasons)


def second_read(image,results,engine,index):
    """Threshold a bounded set of suspect regions; keep primary text intact."""
    from PIL import ImageOps
    import numpy as np
    evidence=[];attempts=0
    for box,text,confidence in results:
        reason=suspect(text,confidence)
        if not reason:continue
        entry={'page':index+1,'primary':str(text),'confidence':round(float(confidence),4) if math.isfinite(float(confidence)) else None,'reason':reason,'alternatives':[]}
        if attempts<4:
            attempts+=1
            try:
                xs=[p[0] for p in box];ys=[p[1] for p in box]
                crop=image.crop((max(0,int(min(xs))-12),max(0,int(min(ys))-12),min(image.width,int(max(xs))+12),min(image.height,int(max(ys))+12)))
                if crop.width<=0 or crop.height<=0:raise ValueError('Empty OCR crop')
                gray=ImageOps.autocontrast(crop.convert('L'))
                variant=gray.point(lambda pixel:255 if pixel>160 else 0).convert('RGB')
                scale=min(2,4096/variant.width,512/variant.height)
                variant=variant.resize((max(1,round(variant.width*scale)),max(1,round(variant.height*scale))))
                output=engine(np.asarray(variant))
                alternate=list(zip(output.boxes,output.txts,output.scores)) if output.boxes is not None and output.txts is not None else []
                reading=rows_from_boxes(alternate)
                if reading.strip():
                    entry['alternatives'].append({'method':'local threshold crop','text':reading})
                    numbers=lambda value:re.findall(r'(?<![A-Za-z0-9])[-+]?\d+(?:[,.]\d+)*(?![A-Za-z0-9])',value)
                    if numbers(str(text))!=numbers(reading):entry['numeric_conflict']=True
            except Exception:entry['retry_status']='Local second read unavailable; review source'
        else:entry['retry_status']='Local retry limit reached; review source'
        evidence.append(entry)
        if len(evidence)==20:
            evidence.append({'page':index+1,'reason':'Page has additional uncertain text; review the original page'});break
    return evidence


def evidence_for_payload(evidence):
    selected=[]
    for entry in evidence:
        hint=dict(entry)
        if hint.get('numeric_conflict'):
            hint['alternatives']=[];hint['reason']+='; second reading disagrees on numbers, manual review required'
        if len(json.dumps(selected+[hint],ensure_ascii=False))>5000:
            selected.append({'reason':'Further OCR ambiguities omitted from AI hints; review source'});break
        selected.append(hint)
    return selected


def review_warning(evidence):
    samples=[str(e['primary'])[:100] for e in evidence if e.get('primary')][:3]
    return 'OCR ambiguity requires source review'+(': '+'; '.join(samples) if samples else '')+'. Second readings are suggestions, not verified corrections.'


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
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise ValueError('Scanned PDF needs the OCR dependencies. Start Open_Invoice_App.bat to install them, or enter the invoice through Review.') from exc
    global _engine
    with _lock:
        if _engine is None:
            onnxruntime.disable_telemetry_events()
            _engine = RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':2,
                'EngineConfig.onnxruntime.inter_op_num_threads':1,'Global.log_level':'error'})
        with pdfium.PdfDocument(str(path)) as document:
            page = document[index]
            bitmap = page.render(scale=3)
            try:
                image = bitmap.to_numpy().copy()
                output = _engine(image)
                results = list(zip(output.boxes,output.txts,output.scores)) if output.boxes is not None and output.txts is not None else []
                evidence=second_read(bitmap.to_pil(),results,_engine,index) if any(suspect(text,score) for _,text,score in results) else []
            finally:
                bitmap.close()
                page.close()
        return OCRText(rows_from_boxes(results or []),evidence)

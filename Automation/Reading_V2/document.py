"""PDF/OCR words with normalized top-left page coordinates and stable IDs."""
from pathlib import Path
from statistics import median
import hashlib
import math
import threading

VERSION='positioned-document-v1'
_ocr=None
_ocr_lock=threading.Lock()


def union(boxes):
    return [min(b[0] for b in boxes),min(b[1] for b in boxes),
            max(b[2] for b in boxes),max(b[3] for b in boxes)]


def cluster_lines(tokens):
    rows=[]
    for token in sorted(tokens,key=lambda t:((t['box'][1]+t['box'][3])/2,t['box'][0])):
        box=token['box'];middle=(box[1]+box[3])/2;height=box[3]-box[1]
        row=next((r for r in reversed(rows[-4:]) if abs(r['middle']-middle)<=max(r['height'],height,.004)*.55),None)
        if row is None:
            row={'middle':middle,'height':height,'tokens':[]};rows.append(row)
        row['tokens'].append(token)
        row['middle']=median((t['box'][1]+t['box'][3])/2 for t in row['tokens'])
        row['height']=max(row['height'],height)
    return [{'tokens':sorted(row['tokens'],key=lambda t:t['box'][0]),
             'box':union([t['box'] for t in row['tokens']])} for row in rows]


def pdf_words(page,index):
    width,height=page.get_size();textpage=page.get_textpage();glyphs=[];word_id=0
    try:
        for i in range(textpage.count_chars()):
            text=textpage.get_text_range(i,1)
            if not text or text.isspace() or not text.isprintable():
                word_id+=1;continue
            left,bottom,right,top=textpage.get_charbox(i)
            if not all(math.isfinite(v) for v in (left,bottom,right,top)):continue
            if right<left or top<bottom:continue
            box=[max(0,left/width),max(0,1-top/height),min(1,right/width),min(1,1-bottom/height)]
            if box[0]>box[2] or box[1]>box[3]:continue
            glyphs.append({'text':text,'box':box,'word_id':word_id,'char_index':i})
    finally:textpage.close()
    words=[]
    groups={}
    for glyph in glyphs:groups.setdefault(glyph['word_id'],[]).append(glyph)
    for group in groups.values():
        group.sort(key=lambda t:t['char_index'])
        words.append({'id':f'p{index+1}w{len(words)+1}','text':''.join(t['text'] for t in group),
                      'box':union([t['box'] for t in group]),'origin':'pdf','ocr_confidence':None})
    return words


def ocr_words(page,index,engine=None):
    bitmap=page.render(scale=3)
    try:
        pixels=bitmap.to_numpy().copy();height,width=pixels.shape[:2]
        global _ocr
        with _ocr_lock:
            if engine is None:
                if _ocr is None:
                    import onnxruntime
                    from rapidocr import RapidOCR
                    onnxruntime.disable_telemetry_events()
                    _ocr=RapidOCR(params={'Global.log_level':'error',
                        'EngineConfig.onnxruntime.intra_op_num_threads':2,
                        'EngineConfig.onnxruntime.inter_op_num_threads':1})
                engine=_ocr
            output=engine(pixels)
        rows=list(zip(output.boxes,output.txts,output.scores)) if output.boxes is not None and output.txts is not None else []
        words=[]
        for box,text,confidence in rows:
            if not str(text).strip():continue
            words.append({'id':f'p{index+1}w{len(words)+1}','text':str(text),
                'box':[float(min(p[0] for p in box))/width,float(min(p[1] for p in box))/height,
                       float(max(p[0] for p in box))/width,float(max(p[1] for p in box))/height],
                'origin':'ocr','ocr_confidence':float(confidence)})
        return words
    finally:bitmap.close()


def read_document(path,ocr_engine=None,max_pages=100):
    import pypdfium2 as pdfium
    path=Path(path);raw=path.read_bytes()
    document={'version':VERSION,'source_sha256':hashlib.sha256(raw).hexdigest(),
              'pages':[],'warnings':[]}
    with pdfium.PdfDocument(str(path)) as pdf:
        if len(pdf)>max_pages:raise ValueError('Document exceeds the evaluation page limit; no pages were silently dropped.')
        for index in range(len(pdf)):
            page=pdf[index]
            try:
                width,height=page.get_size();rotation=page.get_rotation()
                words=pdf_words(page,index) if rotation==0 else []
                if sum(len(t['text']) for t in words)<30:
                    words=ocr_words(page,index,ocr_engine)
                lines=cluster_lines(words)
                for line_index,line in enumerate(lines):
                    line['id']=f'p{index+1}l{line_index+1}'
                    line['text']=' '.join(t['text'] for t in line['tokens'])
                document['pages'].append({'number':index+1,'width':width,'height':height,
                    'rotation':rotation,'tokens':words,'lines':lines})
                if not words:document['warnings'].append(f'Page {index+1} has no readable text.')
            finally:page.close()
    if path.read_bytes()!=raw:raise ValueError('PDF changed during reading; no result may be used.')
    return document


def positioned_text(document):
    """Readable columns for fallback parsing; retain exact tokens separately."""
    pages=[]
    for page in document['pages']:
        lines=[]
        for line in page['lines']:
            words=line['tokens'];parts=[];end=0
            scale=median((t['box'][2]-t['box'][0])/max(1,len(t['text'])) for t in words) if words else .005
            scale=max(.002,scale)
            for word in words:
                gap=max(1,round((word['box'][0]-end)/scale)) if parts else 0
                parts.append(' '*gap+word['text']);end=word['box'][2]
            lines.append(''.join(parts))
        pages.append('\n'.join(lines))
    return '\n\f\n'.join(pages)

"""Date-only normalization/recovery; never substitutes today's date or changes parties/items."""
from datetime import datetime
from pathlib import Path
import re
from .engine import read_json


def normalize_date(value):
    if value in (None,''):return None
    value=' '.join(str(value).strip().split())
    value=re.sub(r'^(?:invoice\s+date|inv\.?\s*date|issued\s+on|date\s+of\s+invoice|dated|date)\s*[:=-]?\s*','',value,flags=re.I)
    value=re.sub(r'^(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?),?\s+','',value,flags=re.I)
    value=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',value,flags=re.I)
    value=re.sub(r'\bSept\b','Sep',value,flags=re.I)
    value=value.replace(',',' ').replace('–','-').replace('—','-')
    value=' '.join(value.split())
    # ISO timestamps retain their printed calendar date, without timezone shifts.
    if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:',value):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).date().isoformat()
        except ValueError:pass
    formats=('%Y-%m-%d','%Y/%m/%d','%Y.%m.%d','%Y%m%d',
             '%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%d %m %Y','%d%m%Y',
             '%d/%m/%y','%d-%m-%y','%d.%m.%y',
             '%d %b %Y','%d-%b-%Y','%d/%b/%Y','%d %B %Y','%d-%B-%Y','%d/%B/%Y',
             '%d %b %y','%d-%b-%y','%d %B %y','%d-%B-%y',
             '%b %d %Y','%B %d %Y','%b %d %y','%B %d %y',
             '%m/%d/%Y','%m-%d-%Y','%m/%d/%y','%m-%d-%y')
    for fmt in formats:
        try:
            date=datetime.strptime(value,fmt).date()
            if 1900<=date.year<=2199:return date.isoformat()
        except ValueError:pass
    return None


# Match labelled invoice dates only. Never pick Due/Delivery/Shipping dates.
TOKEN=(r'(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?'
       r'|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}'
       r'|\d{1,2}(?:st|nd|rd|th)?[\s/-]+[A-Za-z]{3,9}[\s,/-]+\d{2,4}'
       r'|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{2,4}'
       r'|\d{8})')


def labelled_date(text):
    explicit=[];generic=[]
    lines=str(text).splitlines()
    for index,line in enumerate(lines):
        if re.fullmatch(r'\s*(?:invoice\s+date|inv\.?\s*date|date\s+of\s+invoice|issued\s+on|date|dated)\s*[:=-]?\s*',line,re.I) and index+1<len(lines):line+=' '+lines[index+1]
        if re.search(r'\b(?:due|delivery|shipping|dispatch|payment|order|purchase order)\s+date\b',line,re.I) and not re.search(r'\b(?:invoice\s+date|date\s+of\s+invoice|issued\s+on)\b',line,re.I):continue
        strong=re.search(r'\b(?:invoice\s+date|inv\.?\s*date|date\s+of\s+invoice|issued\s+on)\b\s*[:=-]?\s*('+TOKEN+r')',line,re.I)
        weak=re.search(r'(?<![A-Za-z])(?:date|dated)\s*[:=-]?\s*('+TOKEN+r')',line,re.I)
        if weak and re.search(r'\b(?:due|delivery|shipping|dispatch|payment|order)\s*$',line[:weak.start()],re.I):weak=None
        match=strong or weak
        if match:
            parsed=normalize_date(match[1])
            if parsed:(explicit if strong else generic).append(parsed)
    candidates=set(explicit or generic)
    return next(iter(candidates)) if len(candidates)==1 else None


def recover_date(root,record):
    """Update only date/audit fields, using a digest-verified local source if needed."""
    invoice=record.get('invoice') or {}
    raw=invoice.get('date');date=normalize_date(raw)
    evidence='Normalized printed/AI date; numeric Indian dates use day/month/year'
    if date is None and record.get('digest'):
        try:
            from .source_documents import verify_source
            verify_source(Path(root),record)
            cache=Path(root)/'.invoice_app'/'extraction'/(record['digest']+'.json')
            saved=read_json(cache) if cache.exists() else {}
            if saved.get('source_sha256')==record['digest']:
                date=labelled_date(saved.get('text',''))
                if date is None:
                    parsed=normalize_date(saved.get('invoice',{}).get('date'))
                    other_dates={normalize_date(match[1]) for match in re.finditer(r'\b(?:due|delivery|shipping|dispatch|payment|order)\s+date\s*[:=-]?\s*('+TOKEN+r')',saved.get('text',''),re.I)}
                    if parsed not in other_dates:date=parsed
            if date is None:
                from .extraction import text_from_pdf
                date=labelled_date(text_from_pdf(record['path']))
            evidence='Invoice date recovered from verified source PDF/local extraction, not a due date'
        except Exception:
            date=None  # No guessing, API call, or change to other fields.
    if date is not None:
        if raw!=date:
            invoice['date_raw']=raw
            invoice['date']=date
            invoice['date_evidence']=evidence
            record['invoice']=invoice
        return date
    return None

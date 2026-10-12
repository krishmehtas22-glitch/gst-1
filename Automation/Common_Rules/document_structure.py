"""Typed fields and position-preserving table headers for unfamiliar text layouts."""
import re


def gst_identifier(value):
    token=str(value or '').strip()
    match=re.match(r'(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9])(?=$|[\s|;])',token,re.I)
    return match[1].upper() if match else token


def header_key(value,headers):
    direct=next((key for key,aliases in headers.items() if value.casefold() in aliases),None)
    if direct:return direct
    cleaned=re.sub(r'\s*(?:\(\s*)?(?:INR|Rs\.?|₹)(?:\s*\))?\s*$','',value,flags=re.I).strip()
    return next((key for key,aliases in headers.items() if cleaned.casefold() in aliases),None)


def unlabelled_invoice_number(text,warnings):
    found=[]
    for line in text.splitlines():
        for cell in re.split(r'\s{2,}|\s*\|\s*',line.strip()):
            match=re.fullmatch(r'Invoice\s+(?:No\.?\s*)?([A-Z0-9][A-Z0-9/_.-]*)',cell,re.I)
            if match and re.search(r'\d',match[1]):found.append(match[1])
    found=list(dict.fromkeys(found))
    if len(found)>1:warnings.append('Multiple printed invoice numbers need review')
    return found[0] if len(found)==1 else None


def positional_cells(line,header_line):
    """Fallback when extra spaces inside a description split the usual row."""
    spans=list(re.finditer(r'\S.*?(?=\s{2,}|$)',header_line))
    if len(spans)<4:return None
    starts=[0]+[max(0,match.start()-1) for match in spans[1:]]+[len(line)]
    return [line[starts[i]:starts[i+1]].strip() for i in range(len(spans))]

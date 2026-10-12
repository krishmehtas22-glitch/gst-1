"""Party names from explicit printed roles, with no supplier-name dictionary."""
import re

SELLER_ROLES={'seller','supplier','vendor','exporter','issued by','sold by','bill from','billed from','invoice from','from',
    'seller details','supplier details','vendor details','seller information','supplier information','vendor information',
    'seller supplier','supplier seller','seller exporter','exporter seller'}
BUYER_ROLES={'buyer','recipient','customer','bill to','billed to','sold to','buyer details','recipient details','customer details',
    'buyer information','customer information','buyer recipient','recipient buyer','buyer bill to','bill to buyer',
    'billed to buyer','billed to recipient','consignee buyer','billing party'}
STOPS=r'^(?:invoice|inv\b|bill no|date\b|dated\b|item\b|description\b|particulars\b|place of supply\b|ship to\b|delivery\b|supply details|supply information|tax summary|bank details|payment|terms|authori[sz]ed)'


def role_heading(value):
    value=re.sub(r'[^\w\s]',' ',value.casefold()).replace('_',' ')
    value=' '.join(value.split())
    return 'seller' if value in SELLER_ROLES else 'buyer' if value in BUYER_ROLES else None


def read_party_roles(text,warnings):
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    found={};evidence={}
    def put(key,value,line):
        value=value.strip()
        if not value:return
        if key in found and found[key]!=value:
            warnings.append('Ambiguous '+key+' in printed party roles');found[key]=None
        elif key not in found:
            found[key]=value;evidence[key]=line
    def block(rows,initial=None):
        role=initial;expect_name=bool(initial)
        for line in rows:
            heading=role_heading(line.rstrip(':'))
            if heading:
                role=heading;expect_name=True;continue
            prefix,separator,value=line.partition(':')
            inline=role_heading(prefix) if separator else None
            if inline:
                role=inline;expect_name=False
                if value.strip():put(role+'_name',value,line)
                else:expect_name=True
                continue
            if re.match(STOPS,line,re.I):role=None;expect_name=False
            if role is None:continue
            named=re.fullmatch(r'(?:legal name|registered name|trade name|business name|company name|name)\s*:\s*(.+)',line,re.I)
            if named:put(role+'_name',named[1],line);expect_name=False;continue
            gst=re.search(r'(?:^|\s)(?:GSTIN(?:/UIN)?|GST\s*(?:No\.?|Number|Registration\s*(?:No\.?|Number)))(?:\s*\(fictional\))?\s*[:=]\s*(NOT ASSIGNED|Not applicable(?:\s*-\s*overseas buyer)?|N/A(?:\s*-\s*overseas buyer)?|Unregistered|\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9])\b',line,re.I)
            if gst:put(role+'_gstin',gst[1],line);expect_name=False
            state=re.search(r'(?:^|[|;]\s*|\s{2,})(?:State(?:\s*Code)?)\s*[:=]\s*([^|;]+)',line,re.I)
            if state:put(role+'_state',state[1],line)
            reg=re.fullmatch(r'(?:GST registration|registration type)\s*:\s*(.+)',line,re.I)
            if reg:put(role+'_registration',reg[1],line)
            if expect_name and ':' in line:
                expect_name=False
            if expect_name and not gst and not state and ':' not in line:
                if not re.match(r'^(?:tax invoice|original for|duplicate for|address\b|GST\b)',line,re.I):
                    if not re.search(r'\b(?:Unit|Plot|Flat|Floor|Road|Street|Industrial Estate|PIN)\b.*\d|\b\d{6}\b',line,re.I):
                        put(role+'_name',line,line)
                    expect_name=False
    block(lines)
    # Side-by-side party columns need independent role contexts. Their names
    # are the first printed line in each column, never the opposing party.
    for index,line in enumerate(lines):
        cells=re.split(r'\s{2,}|\s*\|\s*|\t+',line)
        roles=[role_heading(cell) for cell in cells]
        if len(roles)!=2 or not any(roles):continue
        columns=[[],[]]
        for following in lines[index+1:]:
            if re.match(STOPS,following,re.I):break
            values=re.split(r'\s{2,}|\s*\|\s*|\t+',following)
            if len(values)!=2:break
            for col,value in zip(columns,values):col.append(value)
        for role,rows in zip(roles,columns):
            if role:block(rows,role)
    return found,evidence


def legal_name_key(name):
    name=re.sub(r'\bpvt\.?\b','private',str(name).casefold())
    name=re.sub(r'\bltd\.?\b','limited',name)
    return ' '.join(re.sub(r'[^\w\s]',' ',name).split())


def read_seller_masthead(text,warnings):
    """Read the printed business before the buyer, corroborated by GST/signature."""
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    boundary=next((i for i,line in enumerate(lines) if role_heading(line.rstrip(':'))=='buyer'
        or role_heading(line.split(':',1)[0])=='buyer'),None)
    if boundary is None:return {}
    header=lines[:boundary];printed=' '.join(header);candidates=[]
    for line in header:
        for cell in re.split(r'\s{2,}|\s*\|\s*',line):
            if ':' in cell or re.match(r'^(?:tax|sales|commercial) invoice\b',cell,re.I):continue
            if re.search(r'\b\d{6}\b|\b(?:Road|Street|Floor|Plot|Address|Industrial Estate)\b',cell,re.I):continue
            if re.search(r'\b(?:Limited|Ltd\.?|LLP|Enterprises|Traders|Trading|Supplies|Distributors|Industries|Corporation|Manufacturers)\b',cell,re.I):candidates.append(cell.strip())
    candidates=list(dict.fromkeys(candidates))
    ids=list(dict.fromkeys(re.findall(r'\bGSTIN(?:/UIN)?\s*[:=]\s*(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[A-Z0-9])\b',printed,re.I)))
    signatories=[]
    for name in re.findall(r'^\s*For\s+([^\n]+)',text,re.I|re.M):
        name=re.split(r'\s*(?:\||[-–,:])?\s*authori[sz]ed signat(?:ory|ure)\b',name,flags=re.I)[0].strip(' |:-–')
        if re.match(r'^(?:testing|software testing|reference|information|illustration|demonstration|office use|sample use)\b',name,re.I):continue
        if name:signatories.append(name)
    signatories=list({legal_name_key(name):name for name in signatories}.values())
    matches=[name for name in signatories if legal_name_key(name) in legal_name_key(printed)]
    candidate={'seller_name_candidate':candidates[0]} if len(candidates)==1 else {}
    if len(signatories)>1 or (signatories and not matches):
        warnings.append('Seller masthead and signatory conflict');return candidate
    if len(ids)>1:
        warnings.append('Ambiguous seller GSTIN in masthead');return candidate
    if len(candidates)==1 and (not signatories or legal_name_key(candidates[0])==legal_name_key(signatories[0])):
        result={'seller_name':candidates[0],'seller_name_source':'Printed seller masthead'}
        if ids:result['seller_gstin']=ids[0]
        return result
    if len(matches)==1 and not candidates and len(ids)==1:return {'seller_name':matches[0],'seller_gstin':ids[0],'seller_name_source':'Printed matching signatory'}
    return candidate

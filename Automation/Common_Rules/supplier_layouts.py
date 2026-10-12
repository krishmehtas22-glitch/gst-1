"""Supplier-scoped extraction instructions, never stored invoice values."""
import hashlib
import json
import re
import uuid

from .accounting import money


def validate_layout(layout):
    from .extraction import FIELDS, HEADERS
    if not isinstance(layout,dict) or layout.get('version')!=1:
        raise ValueError('Unsupported supplier layout version')
    if not re.fullmatch(r'[a-f0-9]{32}',str(layout.get('id',''))):
        raise ValueError('Invalid supplier layout identifier')
    if not isinstance(layout.get('name'),str) or not layout['name'].strip():
        raise ValueError('Give the supplier layout a name')
    if not re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]',str(layout.get('seller_gstin',''))):
        raise ValueError('Supplier layouts require a printed seller GSTIN')
    if not isinstance(layout.get('demo'),bool):
        raise ValueError('Supplier layout must have a real/dummy mode')
    if not isinstance(layout.get('anchors',[]),list) or any(not isinstance(anchor,str) or not anchor.strip() or '\n' in anchor for anchor in layout.get('anchors',[])):
        raise ValueError('Layout identifiers must be printed headings')
    rules=layout.get('fields',{})
    headers=layout.get('headers',{})
    if not isinstance(rules,dict) or not isinstance(headers,dict):
        raise ValueError('Invalid supplier mappings')
    for key,rule in rules.items():
        if key not in FIELDS or not isinstance(rule,dict):
            raise ValueError('Unknown invoice field in supplier layout: '+str(key))
        if set(rule)-{'label','start','end','column','position'}:
            raise ValueError('Supplier mappings accept source labels and sections only')
        for name in ('label','start','end'):
            if not isinstance(rule.get(name,''),str) or '\n' in rule.get(name,''):
                raise ValueError('Mapping labels/headings must be single lines')
        if rule.get('position','label') not in ('label','first_line') or rule.get('column','whole') not in ('whole','left','right'):
            raise ValueError('Invalid supplier mapping position/column')
        if rule.get('position','label')=='label' and not rule.get('label','').strip():
            raise ValueError('A mapped field needs its printed PDF label')
        if rule.get('position')=='first_line' and not rule.get('start','').strip():
            raise ValueError('First-line mapping needs a section heading')
    for key,aliases in headers.items():
        if key not in HEADERS or not isinstance(aliases,list) or not aliases or any(not isinstance(a,str) or not a.strip() or '\n' in a for a in aliases):
            raise ValueError('Invalid item header aliases: '+str(key))
    alias_owners={alias.casefold():key for key,aliases in HEADERS.items() for alias in aliases}
    for key,aliases in headers.items():
        for alias in aliases:
            owner=alias_owners.setdefault(alias.strip().casefold(),key)
            if owner!=key:
                raise ValueError('One item header cannot map to two columns: '+alias)
    return layout


def layout_text(text,rule,warnings):
    """Restrict a field to explicit headings and one party column if requested."""
    lines=text.splitlines()
    start=rule.get('start','').strip()
    end=rule.get('end','').strip()
    if start:
        matches=[i for i,line in enumerate(lines) if start.casefold() in line.casefold()]
        if len(matches)!=1:
            warnings.append('Mapping section heading missing or repeated: '+start)
            return ''
        lines=lines[matches[0]+1:]
    if end:
        matches=[i for i,line in enumerate(lines) if end.casefold() in line.casefold()]
        if not matches:
            warnings.append('Mapping end heading missing: '+end)
            return ''
        lines=lines[:matches[0]]
    column=rule.get('column','whole')
    if column!='whole':
        gaps=[re.search(r'(?<=\S)\s{2,}(?=\S)',line) for line in lines]
        boundary=min((gap.end() for gap in gaps if gap),default=None)
        if boundary is None:
            warnings.append('Mapping column boundary missing; review the changed layout')
            return ''
        selected=[]
        for line,gap in zip(lines,gaps):
            if gap:
                selected.append(line[:gap.start()] if column=='left' else line[gap.end():])
            elif line.strip():
                is_right=len(line)-len(line.lstrip())>=boundary
                if is_right==(column=='right'):
                    selected.append(line.strip())
        lines=selected
    return '\n'.join(lines)


def load_layouts(root):
    folder=root/'.invoice_app'/'supplier_layouts'
    result=[]
    for path in sorted(folder.glob('*.json')):
        if path.is_symlink():
            raise ValueError('Supplier layout must not be a symbolic link')
        try:
            result.append(validate_layout(json.loads(path.read_text(encoding='utf-8'))))
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError('Cannot read supplier layout '+path.name+': '+str(exc)) from exc
    return result


def layouts_revision(layouts):
    return hashlib.sha256(json.dumps(layouts,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def matches_layout(layout,text,base,demo):
    if layout['demo']!=demo:
        return False
    if any(anchor.casefold() not in text.casefold() for anchor in layout.get('anchors',[])):
        return False
    seller=str(base.get('seller_gstin') or '').strip().upper()
    if re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]',seller) and seller!=layout['seller_gstin']:
        return False
    if not re.search(r'(?<![A-Z0-9])'+re.escape(layout['seller_gstin'])+r'(?![A-Z0-9])',text,re.I):
        return False
    for rule in layout['fields'].values():
        for name in ('label','start','end'):
            if rule.get(name) and rule[name].casefold() not in text.casefold():
                return False
    for aliases in layout['headers'].values():
        if not any(alias.casefold() in text.casefold() for alias in aliases):
            return False
    return True


def parse_with_layout(text,layout):
    from .extraction import parse_text
    validate_layout(layout)
    base=parse_text(text)
    mapped=parse_text(text,layout.get('fields',{}),layout.get('headers',{}))
    warnings=mapped.setdefault('extraction_warnings',[])
    if mapped.get('seller_gstin','').upper()!=layout['seller_gstin']:
        warnings.append('Mapped seller GSTIN differs from the saved supplier')
    if base.get('supply')=='EXPORT' and any(mapped.get(key)!=base.get(key) for key in ('supply','classification','export_mode')):
        warnings.append('Supplier mapping conflicts with the printed export treatment')
    mapped['supplier_layout_name']=layout['name']
    mapped['supplier_layout_id']=layout['id']
    if not mapped.get('source_layout'):
        mapped['source_layout']='supplier_mapping_v1'
    return mapped


def extract_with_layouts(text,layouts,demo):
    from .extraction import parse_text
    base=parse_text(text)
    matches=[layout for layout in layouts if matches_layout(layout,text,base,demo)]
    if len(matches)>1:
        base.setdefault('extraction_warnings',[]).append('Multiple supplier layouts match; remove or narrow the overlapping mappings')
        return base
    return parse_with_layout(text,matches[0]) if matches else base


def new_layout(record,demo):
    invoice=record['invoice']
    anchors={'section_panels_v1':['SELLER DETAILS','INVOICE DETAILS','BILL TO / BUYER'],
             'paired_columns_v1':['SELLER / SUPPLIER','BUYER / RECIPIENT'],
             'tabular_roles_v1':['Billed To (Recipient)'],
             'receipt_items_v1':['Customer:','HSN']}.get(invoice.get('source_layout'),[])
    return {'version':1,'id':uuid.uuid4().hex,'name':invoice.get('seller_name','Supplier layout'),
            'seller_gstin':str(invoice.get('seller_gstin','')).upper(),'demo':demo,
            'anchors':anchors,'fields':{},'headers':{}}


def preview_layout(text,layout,demo):
    """Validate the sample without creating a company or changing history."""
    from .accounting import gstin_valid, validate
    from .demo import prepare_demo_invoice, test_gstin
    from .engine import DEFAULT_LEDGERS
    from .desktop import UNITS
    parsed=parse_with_layout(text,layout)
    config={'seller_gstin':layout['seller_gstin'],'ledgers':dict(DEFAULT_LEDGERS),'units':dict(UNITS)}
    if demo:
        try:
            config.update(demo_only=True,source_seller_gstin=layout['seller_gstin'],
                          seller_gstin=test_gstin(layout['seller_gstin'][:14]),
                          demo_profile={'version':2,'seller_state':layout['seller_gstin'][:2],'unit':'Nos'})
            prepared=prepare_demo_invoice(parsed,config)
        except (ValueError,KeyError,TypeError) as exc:
            return parsed,[str(exc)]
    else:
        prepared=parsed
        if not gstin_valid(layout['seller_gstin']):
            return parsed,['Seller GSTIN fails validation']
        if parsed.get('dummy_document'):
            return parsed,['This document is explicitly fictional; use dummy mode']
    _,errors=validate(prepared,config)
    # Validating without preparing masters can miss unknown units.
    errors.extend('Unit '+str(item.get('unit'))+' needs a company mapping' for item in prepared.get('items',[]) if item.get('unit') not in UNITS)
    return parsed,list(dict.fromkeys(errors))


def save_layout(root,record,layout,demo):
    from pathlib import Path
    from .engine import write_json
    from .extraction import text_from_pdf
    validate_layout(layout)
    path=Path(record['path'])
    from .source_documents import verify_source
    verify_source(root,record)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=record.get('digest'):
        raise ValueError('The sample PDF changed or is outside the invoice folder; scan again')
    if demo!=layout['demo']:
        raise ValueError('Supplier layout mode changed; reopen the editor')
    text=text_from_pdf(path)
    parsed,errors=preview_layout(text,layout,demo)
    if parsed.get('source_ocr'):
        raise ValueError('OCR-derived samples still need per-invoice review; use a text PDF to save an automatic supplier layout')
    if errors:
        raise ValueError('Resolve the preview before saving: '+'; '.join(errors))
    if not matches_layout(layout,text,parse_with_layout(text,layout),demo):
        raise ValueError('The sample does not contain all supplied headings/labels')
    # A valid preview must still agree with a previously checked sample.
    expected=record['invoice']
    for key in ('seller_name','seller_gstin','number','date','buyer_name','buyer_gstin','classification','taxable','total','cgst','sgst','igst'):
        if expected.get(key) not in (None,'') and parsed.get(key) not in (None,''):
            same=(money(expected[key])==money(parsed[key])) if key in ('taxable','total','cgst','sgst','igst') else str(expected[key]).strip()==str(parsed[key]).strip()
            if not same:
                raise ValueError('Preview '+key.replace('_',' ')+' differs from the checked invoice; correct the mapping/sample first')
    expected_items=expected.get('items',[])
    if expected_items:
        if len(expected_items)!=len(parsed.get('items',[])):
            raise ValueError('Preview item count differs from the checked invoice')
        for old,item in zip(expected_items,parsed['items']):
            for key in ('name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate'):
                if key=='unit' and old.get('unit_auto') and not item.get('unit'):continue
                if old.get(key) not in (None,''):
                    same=(money(old[key])==money(item.get(key))) if key in ('quantity','rate','value','cgst_rate','sgst_rate','igst_rate') else old[key]==item.get(key)
                    if key=='unit':
                        from .unit_inference import canonical_unit
                        same=bool(canonical_unit(old[key])) and canonical_unit(old[key])==canonical_unit(item.get(key))
                    if not same:
                        raise ValueError('Preview item '+key+' differs from the checked invoice')
    folder=root/'.invoice_app'/'supplier_layouts'
    for old in load_layouts(root):
        if old['id']!=layout['id'] and matches_layout(old,text,parsed,demo):
            raise ValueError('This sample already matches '+old['name']+'; edit that saved layout instead')
    destination=folder/(layout['id']+'.json')
    if destination.exists():
        old=validate_layout(json.loads(destination.read_text(encoding='utf-8')))
        if old['seller_gstin']!=layout['seller_gstin'] or old['demo']!=layout['demo']:
            raise ValueError('Cannot move a retained layout to another supplier/mode')
        write_json(folder/'backups'/(layout['id']+'_'+uuid.uuid4().hex+'.json'),old)
    write_json(destination,layout)
    return destination


def remove_layout(root,layout):
    """Archive the layout; source PDFs, reviews and company history stay intact."""
    from .engine import write_json
    validate_layout(layout)
    folder=root/'.invoice_app'/'supplier_layouts'
    path=folder/(layout['id']+'.json')
    if path.is_symlink():
        raise ValueError('Supplier layout must not be a symbolic link')
    if path.exists():
        saved=validate_layout(json.loads(path.read_text(encoding='utf-8')))
        write_json(folder/'backups'/(layout['id']+'_'+uuid.uuid4().hex+'.json'),saved)
        path.unlink()

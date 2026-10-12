"""Source inspection and isolated company workspaces for the desktop UI."""
import hashlib
from pathlib import Path
import re
import shutil
import uuid

from .accounting import gstin_valid, state_code
from .accounting import EXPORT_MODES, export_notice, invoice_key
from .demo import test_gstin
from .engine import (discover, init_client, invoice_paths, process_client,
                     read_json, write_json)
from .extraction import parse_text, text_from_pdf

UNITS = {
    'Nos': {'formal_name':'Numbers','uqc':'NOS','decimal_places':0},
    'KG': {'formal_name':'Kilograms','uqc':'KGS','decimal_places':3},
    'ROLL': {'formal_name':'Rolls','uqc':'ROL','decimal_places':0,'tally_uqc':'ROL-ROLLS'},
    'SET': {'formal_name':'Sets','uqc':'SET','decimal_places':0},
}
PARSER_REVISION = hashlib.sha256(b''.join((Path(__file__).parent/name).read_bytes()
    for name in ('extraction.py','paired_layout.py','section_layout.py','ocr.py'))).hexdigest()


def _same_review_value(left,right):
    if left in (None,'') and right in (None,''):
        return True
    if isinstance(left,(str,int,float)) and isinstance(right,(str,int,float)):
        return str(left).strip()==str(right).strip()
    return left==right


def refresh_review(source, saved):
    """Rebase unchanged extraction fields, preserving explicit human edits."""
    reviewed=saved['invoice']
    original=saved.get('original_extraction')
    # Without a baseline, never guess which fields the user intentionally set.
    # Keep prior OCR approvals intact rather than replacing them with new OCR.
    if not isinstance(original,dict) or source.get('source_ocr'):
        return dict(reviewed)
    refreshed=dict(source)
    if source.get('extraction_warnings',[])==original.get('extraction_warnings',[]):
        # An approval resolves the same warnings, but not new parser warnings.
        refreshed['extraction_warnings']=reviewed.get('extraction_warnings',[])
    for field,value in reviewed.items():
        if field in ('items','extraction_warnings'):
            continue
        if not _same_review_value(value,original.get(field)):
            refreshed[field]=value
    old_items=original.get('items',[])
    reviewed_items=reviewed.get('items',[])
    if reviewed_items!=old_items:
        fresh_items=source.get('items',[])
        same_rows=(len(old_items)==len(reviewed_items)==len(fresh_items) and
            all((old.get('name'),old.get('hsn'))==(fresh.get('name'),fresh.get('hsn'))
                for old,fresh in zip(old_items,fresh_items)))
        if same_rows:
            updated=[]
            for old,edited,fresh in zip(old_items,reviewed_items,fresh_items):
                item=dict(fresh)
                item.update({field:value for field,value in edited.items() if not _same_review_value(value,old.get(field))})
                updated.append(item)
            refreshed['items']=updated
        else:
            refreshed['items']=reviewed_items
    return refreshed


def reset_source_reviews(root, records):
    """Archive only selected source reviews/caches; never reset company history."""
    backup=root/'.invoice_app'/'review_backups'/uuid.uuid4().hex
    archived=[]
    digests=set()
    for record in records:
        digest=record.get('digest','')
        if not re.fullmatch(r'[a-f0-9]{64}',digest):
            raise ValueError('Scan the selected PDF before re-reading it')
        path=Path(record['path'])
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('The selected PDF changed or is outside the invoice folder; scan again')
        digests.add(digest)
    for digest in sorted(digests):
        for folder in ('reviews','extraction'):
            source=root/'.invoice_app'/folder/(digest+'.json')
            if source.exists():
                destination=backup/folder/source.name
                destination.parent.mkdir(parents=True,exist_ok=True)
                source.replace(destination)
                archived.append(str(destination))
    return archived


def inspect_sources(root, client_names=None):
    records = []
    for folder in discover(root):
        if client_names is not None and folder.name not in client_names:
            continue
        for path in invoice_paths(folder):
            record = {'path':str(path),'client':folder.name,'errors':[],'invoice':{}}
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Source path escapes the selected folder')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                record['digest'] = digest
                try:
                    cache = root/'.invoice_app'/'extraction'/(digest+'.json')
                    saved = read_json(cache) if cache.exists() else {}
                    if saved.get('parser_revision') == PARSER_REVISION and saved.get('source_sha256') == digest:
                        record['invoice'] = saved['invoice']
                    else:
                        record['invoice'] = parse_text(text_from_pdf(path))
                        write_json(cache,{'parser_revision':PARSER_REVISION,'source_sha256':digest,'invoice':record['invoice']})
                except Exception as exc:
                    record['errors'].append(f'PDF extraction failed: {exc}')
                record['source_invoice'] = record['invoice']
                review = root/'.invoice_app'/'reviews'/(digest+'.json')
                if review.exists():
                    saved = read_json(review)
                    if saved.get('source_sha256') != digest or saved.get('approved') is not True:
                        raise ValueError('Review must be approved and match this PDF')
                    record['invoice'] = refresh_review(record['source_invoice'],saved)
                    original = record['source_invoice']
                    if (record['invoice'].get('classification') == 'export' and
                        original.get('classification') == 'export_lut' and
                        record['invoice'].get('supply') == original.get('supply') == 'EXPORT' and
                        record['invoice'].get('export_mode') == original.get('export_mode') == 'LUT_without_payment'):
                        # Older approved reviews used the general export label;
                        # normalize it only when the PDF explicitly states LUT.
                        record['invoice'] = {**record['invoice'],'classification':'export_lut'}
                    record['reviewed'] = True
                    record['errors'] = []
                record['errors'].extend(record['invoice'].get('extraction_warnings',[]))
            except (ValueError,OSError,KeyError,TypeError) as exc:
                record['errors'].append(str(exc))
            except Exception as exc:
                record['errors'].append(f'PDF extraction failed: {exc}')
            records.append(record)
    return records


def save_review(root, record, invoice):
    path = Path(record['path'])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != record['digest']:
        raise ValueError('The source PDF changed. Scan again before saving its review.')
    edited = dict(invoice)
    edited['extraction_warnings'] = []
    write_json(root/'.invoice_app'/'reviews'/(digest+'.json'),
               {'source_sha256':digest,'approved':True,'invoice':edited,
                'original_extraction':record.get('source_invoice',record['invoice'])})


def process_sources(root, demo=True, client_names=None):
    records = inspect_sources(root,client_names)
    workspace = root/'.invoice_app'/'companies'
    workspace.mkdir(parents=True,exist_ok=True)
    groups = {}
    for record in records:
        raw = record['invoice']
        try:
            source = record.get('source_invoice',{})
            if source.get('supply') == 'EXPORT' and (raw.get('supply') != 'EXPORT' or raw.get('classification') != source.get('classification') or raw.get('export_mode') != source.get('export_mode')):
                raise ValueError('Reviewed export treatment must match the source PDF; it cannot be changed to a domestic sale')
            if record['errors']:
                continue
            if not record.get('digest'):
                raise ValueError('Unreadable source PDF')
            if demo and not raw.get('dummy_document'):
                raise ValueError('Select real-invoice mode for real documents; dummy mode requires explicit fictional markers')
            if not demo and raw.get('dummy_document'):
                raise ValueError('This document is explicitly fictional; use dummy mode')
            if raw.get('supply') == 'EXPORT':
                if raw.get('export_mode') != EXPORT_MODES.get(raw.get('classification'),False):
                    raise ValueError('Export requires an explicit matching LUT/IGST payment mode')
            seller = raw.get('seller_gstin','').upper()
            name = raw.get('seller_name','').strip()
            if not name or not seller:
                raise ValueError('Seller name/GSTIN missing; correct the invoice in the review form')
            if demo:
                if seller == 'NOT ASSIGNED':
                    code = state_code(raw.get('seller_state',''))
                    canonical = test_gstin(code+'DEMCO0000A1Z')
                else:
                    canonical = test_gstin(seller[:14])
                    code = canonical[:2]
            else:
                if not gstin_valid(seller):
                    raise ValueError('Seller GSTIN fails validation; correct it in the review form')
                canonical = seller
                code = seller[:2]
            # Same GSTIN stays one company. Mode is part of the identity.
            identity = ('demo|' if demo else 'real|')+seller
            if seller == 'NOT ASSIGNED':
                identity += '|'+name+'|'+code
            binding = root/'.invoice_app'/'routing'/(record['digest']+'.json')
            if binding.exists() and read_json(binding).get('identity') != identity:
                raise ValueError('This PDF already belongs to another retained company/mode; restore its seller identity before processing')
            suffix = hashlib.sha256(identity.encode()).hexdigest()[:16]
            slug = re.sub(r'[^A-Za-z0-9_-]+','_',name)[:40] or 'Company'
            # Resolve retained identities independently of a changed display name.
            matches = list(workspace.glob('*_'+suffix))
            company = matches[0] if matches else workspace/(slug+'_'+suffix)
            if not (company/'client.json').exists():
                if (company/'.automation/history.sqlite3').exists():
                    raise ValueError('Existing company history needs its original configuration restored')
                profile = {'version':1 if seller == 'NOT ASSIGNED' else 2,'seller_state':code,'unit':'Nos'} if demo else None
                init_client(workspace,company.name,name,canonical,demo_profile=profile)
                config = read_json(company/'client.json')
                config['units'] = dict(UNITS)
                config['source_seller_gstin'] = seller
                config['source_seller_name'] = name
                write_json(company/'client.json',config)
            config = read_json(company/'client.json')
            if 'unified_sales_ledger' not in config:
                # Add the desktop default without replacing identity, history,
                # unit mappings or any existing explicit ledger preference.
                config['unified_sales_ledger'] = True
                write_json(company/'client.json',config)
            if raw.get('classification') in EXPORT_MODES:
                record['notices'] = [export_notice(config)]
            if config.get('source_seller_name') != name:
                raise ValueError('Seller GSTIN matches a retained company but seller name differs; review the source identity')
            filename = record['digest']+'.pdf'
            target = company/filename
            if not target.exists():
                shutil.copy2(record['path'],target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != record['digest']:
                raise ValueError('Retained source copy differs from the original PDF')
            write_json(company/'reviews'/(record['digest']+'.json'),
                       {'source_sha256':record['digest'],'approved':True,'invoice':raw})
            write_json(binding,{'identity':identity,'company':company.name})
            record['company_path'] = str(company)
            groups.setdefault(company,[]).append(record)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            record['errors'].append(str(exc))
    for company, group in groups.items():
        try:
            report = process_client(workspace,company)
            config = read_json(company/'client.json')
            history = {entry['invoice_key']:entry['status'] for entry in report['history']}
            issues = {}
            for issue in report['issues']:
                issues.setdefault(issue.get('source'),[]).extend(issue.get('errors',[]))
            for record in group:
                record['errors'].extend(issues.get(record['digest']+'.pdf',[]))
                # Master-plan/export failures must not be displayed as success.
                if report['issues'] and not record['errors']:
                    record['errors'].extend(error for issue in report['issues'] if not issue.get('source') for error in issue.get('errors',[]))
                record['export'] = report['export']
                record['batch_voucher_count'] = report['pending_validated']
                if not record['errors']:
                    try:
                        key = invoice_key({**record['invoice'],'seller_gstin':config['seller_gstin']})
                    except (ValueError,KeyError,TypeError):
                        key = None
                    status = history.get(key)
                    record['display_status'] = ('Already confirmed imported' if status == 'imported' else
                        'Sales XML prepared; import not confirmed' if status == 'generated' else
                        report['export'])
                if record['invoice'].get('classification') in EXPORT_MODES and not record['errors']:
                    record['export'] = 'Export accounting voucher prepared; verify GST in Tally'
                    if history.get(key) != 'imported':
                        record['display_status'] = 'Export sales XML prepared; verify GST in Tally'
        except Exception as exc:
            for record in group:
                record['errors'].append(str(exc))
    return records

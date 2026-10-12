"""Source inspection and isolated company workspaces for the desktop UI."""
import hashlib
from pathlib import Path
import re
import shutil

from .accounting import gstin_valid, state_code
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
    for name in ('extraction.py','paired_layout.py','ocr.py'))).hexdigest()


def inspect_sources(root):
    records = []
    for folder in discover(root):
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
                    record['invoice'] = saved['invoice']
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


def process_sources(root, demo=True):
    records = inspect_sources(root)
    workspace = root/'.invoice_app'/'companies'
    workspace.mkdir(parents=True,exist_ok=True)
    groups = {}
    for record in records:
        raw = record['invoice']
        try:
            if record.get('source_invoice',{}).get('supply') == 'EXPORT':
                record['errors'] = ['Export extracted for inspection; export-specific GST XML is not implemented']
                continue
            if record['errors']:
                continue
            if not record.get('digest'):
                raise ValueError('Unreadable source PDF')
            if demo and not raw.get('dummy_document'):
                raise ValueError('Select real-invoice mode for real documents; dummy mode requires explicit fictional markers')
            if not demo and raw.get('dummy_document'):
                raise ValueError('This document is explicitly fictional; use dummy mode')
            if raw.get('supply') == 'EXPORT' or raw.get('classification') == 'export':
                raise ValueError('Export extracted for inspection; export-specific GST XML is not implemented')
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
            issues = {}
            for issue in report['issues']:
                issues.setdefault(issue.get('source'),[]).extend(issue.get('errors',[]))
            for record in group:
                record['errors'].extend(issues.get(record['digest']+'.pdf',[]))
                # Master-plan/export failures must not be displayed as success.
                if report['issues'] and not record['errors']:
                    record['errors'].extend(error for issue in report['issues'] if not issue.get('source') for error in issue.get('errors',[]))
                record['export'] = report['export']
        except Exception as exc:
            for record in group:
                record['errors'].append(str(exc))
    return records

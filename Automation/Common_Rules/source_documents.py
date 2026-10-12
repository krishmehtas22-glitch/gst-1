"""Expand complete independent invoice pages without changing source PDFs."""
import hashlib
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from .engine import read_json, write_json
from .flat_layout import parse_flat_layout


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source(root, record):
    for path, digest in ((record['path'], record['digest']),
                         (record.get('source_path', record['path']), record.get('source_sha256', record['digest']))):
        path = Path(path)
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or sha(path) != digest:
            raise ValueError('The source PDF changed or is outside the invoice folder. Scan again before saving.')


def expand_source(root, path, client):
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Source path escapes the selected folder')
    digest = sha(path)
    base = {'path':str(path), 'client':client, 'digest':digest,
            'source_path':str(path), 'source_sha256':digest}
    reader = PdfReader(path)
    if len(reader.pages) < 2:
        return [base]
    invoices = [parse_flat_layout(page.extract_text() or '') for page in reader.pages]
    # A continuation, cover, missing header, or duplicate number prevents
    # splitting. Never silently discard pages or assume one invoice per page.
    complete = all(inv and all(inv.get(key) for key in ('number','date','seller_name','buyer_name','items')) for inv in invoices)
    if not complete:
        return [base]
    numbers = [(inv['seller_name'],inv['number'],inv['date']) for inv in invoices]
    if len(set(numbers)) != len(numbers):
        return [base]
    directory = root/'.invoice_app'/'source_pages'/digest
    directory.mkdir(parents=True,exist_ok=True)
    index = directory/'index.json'
    manifest = read_json(index) if index.exists() else {}
    previous = manifest.get('pages',{}) if manifest.get('source_sha256') == digest else {}
    records = []; hashes = {}
    for number,page in enumerate(reader.pages,1):
        target = directory/f'page-{number:04d}.pdf'
        if target.is_symlink():
            raise ValueError('Generated invoice page must not be a symbolic link')
        if target.exists():
            page_digest = sha(target)
            if previous.get(str(number)) != page_digest:
                raise ValueError('Generated invoice page differs from its retained source proof; restore the source page cache')
        else:
            writer = PdfWriter(); writer.add_page(page)
            with target.open('wb') as stream: writer.write(stream)
            page_digest = sha(target)
        hashes[str(number)] = page_digest
        records.append({**base,'path':str(target),'digest':page_digest,
                        'page_number':number,'page_count':len(reader.pages)})
    write_json(index, {'source_sha256':digest,'pages':hashes})
    return records


def settings_path(root, record):
    return root/'.invoice_app'/'document_settings'/(record.get('source_sha256',record['digest'])+'.json')


def confirmed_test(root, record):
    path = settings_path(root, record)
    if not path.exists(): return False
    saved = read_json(path)
    return saved.get('source_sha256') == record.get('source_sha256',record['digest']) and saved.get('fictional_test_data') is True


def confirm_test_document(root, record):
    verify_source(root, record)
    write_json(settings_path(root,record), {'source_sha256':record.get('source_sha256',record['digest']),
                                          'fictional_test_data':True})

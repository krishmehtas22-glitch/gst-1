"""List source PDF metadata only. No PDF reading, OCR, providers or XML writes."""
from copy import deepcopy
from pathlib import Path
from .engine import discover, invoice_paths


def source_path(record):
    return str(Path(record.get('source_path', record['path'])).resolve())


def list_sources(root, client_names=None, previous=()):
    root = Path(root).resolve()
    old = {}
    for record in previous:
        old.setdefault(source_path(record), []).append(record)
    rows = []
    for client in discover(root):
        if client_names is not None and client.name not in client_names:
            continue
        for path in invoice_paths(client):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            stat = path.stat()
            signature = [stat.st_size, stat.st_mtime_ns]
            retained = old.get(str(path.resolve()), [])
            if retained and all(r.get('listing_signature') == signature for r in retained):
                rows.extend(deepcopy(retained))
            else:
                rows.append({'path': str(path), 'source_path': str(path), 'client': client.name,
                    'invoice': {'number': path.name, 'items': []}, 'errors': [],
                    'listing_only': True, 'listing_signature': signature,
                    'display_status': 'Waiting for your AI action'})
    return rows

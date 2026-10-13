"""Remember the most recently successful provider for each verified source."""
from pathlib import Path
from .engine import read_json, write_json


def activate(root, record, provider):
    from .ai_providers import PROVIDERS
    if provider not in PROVIDERS:raise ValueError('Unknown invoice API provider')
    write_json(Path(root)/'.invoice_app'/'api_selection'/(record['digest']+'.json'),
               {'source_sha256':record['digest'],'provider':provider})


def candidate(root, record):
    path=Path(root)/'.invoice_app'/'api_selection'/(record['digest']+'.json')
    selected=read_json(path) if path.exists() else {'provider':'Gemini'}
    if path.exists() and selected.get('source_sha256')!=record['digest']:
        raise ValueError('API provider selection does not match this PDF')
    from .ai_providers import reader
    return reader(selected.get('provider')).candidate(root,record)

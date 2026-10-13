"""Remember the most recently successful provider for each verified source."""
from pathlib import Path
from .engine import read_json, write_json


def activate(root, record, provider):
    if provider not in ('Gemini','Groq'):raise ValueError('Unknown invoice API provider')
    write_json(Path(root)/'.invoice_app'/'api_selection'/(record['digest']+'.json'),
               {'source_sha256':record['digest'],'provider':provider})


def candidate(root, record):
    path=Path(root)/'.invoice_app'/'api_selection'/(record['digest']+'.json')
    selected=read_json(path) if path.exists() else {'provider':'Gemini'}
    if path.exists() and selected.get('source_sha256')!=record['digest']:
        raise ValueError('API provider selection does not match this PDF')
    if selected.get('provider')=='Groq':
        from .groq_reader import candidate as load
    elif selected.get('provider')=='Gemini':
        from .gemini_reader import candidate as load
    else:raise ValueError('Unknown invoice API provider selection')
    return load(root,record)

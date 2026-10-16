"""Selected AI reading uses the same complete client XML path as batch reading."""
from pathlib import Path


def analyse_paths(root, records, provider, demo, auto_units, summary_accounting,
                  progress=lambda message: None, stop_event=None):
    from .ai_first import run_ai_first
    from .invoice_queue import source_path
    paths = sorted({source_path(r) for r in records})
    clients = sorted({r['client'] for r in records})
    if not paths:
        raise ValueError('Select at least one PDF.')
    return run_ai_first(root, demo, clients, auto_units, summary_accounting,
        primary=provider, progress=progress, stop_event=stop_event,
        selected_paths=paths, max_new_requests=len(paths), confirm_test=demo)


def selected_to_xml(root, record, provider, demo, auto_units, summary_accounting,
                    progress=lambda message: None, stop_event=None):
    from .source_documents import verify_source
    from .ai_first import run_ai_first, token
    root = Path(root)
    verify_source(root, record)
    client = record['client']
    # Only this PDF can consume an AI attempt. Prepare the client's full current
    # XML from saved/local data, preserving other clients and human approvals.
    updated, summary = run_ai_first(root, demo, [client], auto_units, summary_accounting,
        primary=provider, progress=progress, stop_event=stop_event,
        selected_source=token(record), confirm_test=demo)
    selected = [r for r in summary['sources'] if token(r) == token(record)]
    return selected, updated, summary['warnings']

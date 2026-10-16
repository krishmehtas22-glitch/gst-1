"""Selected AI reading uses the same complete client XML path as batch reading."""
from pathlib import Path


def selected_to_xml(root, record, provider, demo, auto_units, summary_accounting,
                    progress=lambda message: None, stop_event=None):
    from .source_documents import verify_source
    from .gemini_batch import run_batch_to_xml
    from .desktop import process_sources
    root = Path(root)
    verify_source(root, record)
    client = record['client']
    # Only this PDF can consume an AI attempt. Prepare the client's full current
    # XML from saved/local data, preserving other clients and human approvals.
    return run_batch_to_xml(root, [record], primary=provider,
        exporter=lambda: process_sources(root, demo, [client], auto_units, summary_accounting),
        progress=progress, confirm_test=demo, stop_event=stop_event, max_new_requests=1)

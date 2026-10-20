"""AI extracts invoice meaning first; the existing Python writer converts it later."""
from pathlib import Path

from .ai_providers import ACTIVE_PROVIDERS,LOCAL_PROVIDER
from .engine import read_json, write_json
from .source_documents import verify_source


def configured_primary(root):
    path = Path(root)/'.invoice_app'/'ai_first_settings.json'
    try:
        provider = read_json(path).get('primary', 'Groq') if path.exists() else 'Groq'
    except (ValueError, OSError, TypeError):
        provider = 'Groq'
    return provider if provider in ACTIVE_PROVIDERS+(LOCAL_PROVIDER,) else 'Groq'


def save_primary(root, provider):
    if provider not in ACTIVE_PROVIDERS+(LOCAL_PROVIDER,):
        raise ValueError('Choose an active invoice AI provider.')
    write_json(Path(root)/'.invoice_app'/'ai_first_settings.json', {'version': 1, 'primary': provider})


def token(record):
    return record['client'], record.get('digest'), record['path']


def approved_result(root, record):
    """An approved digest-bound source stays terminal without being called AI."""
    path = Path(root)/'.invoice_app'/'reviews'/(record.get('digest', '')+'.json')
    if not path.exists():
        return None
    saved = read_json(path)
    if (saved.get('source_sha256') != record.get('digest') or saved.get('approved') is not True or
            not isinstance(saved.get('invoice'), dict) or not isinstance(saved['invoice'].get('items'), list)):
        raise ValueError('Saved review needs manual attention.')
    return {'status': 'approved_review', 'provider': 'Human review', 'cached': True}


def run_ai_first(root, demo=True, client_names=None, auto_units=True,
                 summary_accounting=False, primary=None, progress=lambda message: None,
                 stop_event=None, batch_runner=None, selected_source=None, confirm_test=False,
                 selected_paths=None, max_new_requests=None):
    from .desktop import inspect_sources, process_sources
    from .gemini_batch import read_with_fallback, find_retained, RequestBudget
    from .tally_review_export import enable
    root = Path(root)
    primary = primary or configured_primary(root)
    if primary not in ACTIVE_PROVIDERS+(LOCAL_PROVIDER,):
        raise ValueError('Choose an active invoice AI provider.')
    progress('Preparing PDF text/OCR for AI; XML conversion has not started.')
    records = inspect_sources(root, client_names, demo, auto_units)
    from .tally_master_matching import context,match_cached
    if primary==LOCAL_PROVIDER:
        from .ollama_reader import match_cached
    elif primary=='OpenRouter':
        from .openrouter_reader import match_cached
    approved_paths = None if selected_paths is None else {str(Path(p).resolve()) for p in selected_paths}
    if approved_paths is not None:
        present = {str(Path(r.get('source_path', r['path'])).resolve()) for r in records}
        if not approved_paths or not approved_paths.issubset(present):
            raise ValueError('Selected PDFs changed or disappeared; refresh the list and choose again.')
    def selected(record):
        return ((selected_source is None or token(record) == selected_source) and
                (approved_paths is None or str(Path(record.get('source_path', record['path'])).resolve()) in approved_paths))
    if selected_source is not None and selected_source not in {token(r) for r in records}:
        raise ValueError('Selected source changed or disappeared; scan the client again.')
    bound_clients={r['client'] for r in records if selected(r) and context(root,r)}
    decisions, pending, warnings = {}, [], []
    for record in records:
        try:
            verify_source(root, record)
        except (ValueError, OSError, KeyError, TypeError):
            decisions[token(record)] = {'status': 'source_needs_review', 'provider': 'Python'}
            continue
        try:
            approved = approved_result(root, record)
        except (ValueError, OSError, KeyError, TypeError):
            decisions[token(record)] = {'status': 'saved_review_needs_attention', 'provider': 'Human review'}
            continue
        if approved:
            decisions[token(record)] = approved
        elif not selected(record):
            retained = find_retained(root, record, primary)
            decisions[token(record)] = ({'status': 'extracted', 'provider': retained['provider'], 'cached': True}
                if retained else {'status': 'not_selected_for_new_ai', 'provider': 'Python', 'cached': False})
        else:
            pending.append(record)
    limit = len(pending)
    if bound_clients:limit=len([r for r in records if selected(r)])
    if approved_paths is not None:limit = min(limit, len(approved_paths))
    if max_new_requests is not None:limit = min(limit, max(0, int(max_new_requests)))
    budget = RequestBudget(limit)
    progress(f'AI stage: {len(pending)} sources use saved AI reads or new extraction; '
             f'{len(records)-len(pending)} sources retain manual/source review status.')
    provider_unavailable=False
    try:
        if pending:
            answers = (batch_runner or read_with_fallback)(root, pending, primary=primary,
                progress=progress, confirm_test=False, stop_event=stop_event, request_budget=budget)
            import json
            provider_unavailable=any(primary+' HTTP '+str(code) in json.dumps(answers) for code in (401,402,403,404,429))
            for record, answer in zip(pending, answers):
                if (answer.get('client'), answer.get('digest'), answer.get('path')) != token(record):
                    raise ValueError('AI batch result does not match its source.')
                decisions[token(record)] = {
                    'status': answer.get('status', 'local fallback'),
                    'provider': answer.get('provider', 'Python'),
                    'cached': bool(answer.get('cached') or answer.get('status') == 'extracted' and not answer.get('attempts'))}
    except Exception as exc:
        provider_unavailable=any(primary+' HTTP '+str(code) in str(exc) for code in (401,402,403,404,429))
        warnings.append('AI stage ended with '+type(exc).__name__+'; saved reads are retained.')
        progress(warnings[-1])
    # Matching cached selected invoices shares the original confirmed budget.
    # Fresh Groq reads already receive candidate masters in the same AI call.
    matching_start=budget.used
    if bound_clients and not provider_unavailable and not (stop_event and stop_event.is_set()):
        current=inspect_sources(root,client_names,demo,auto_units)
        for record in current:
            if selected(record) and record['client'] in bound_clients and decisions.get(token(record),{}).get('status') in ('extracted','approved_review'):
                try:
                    if match_cached(root,record,budget,stop_event):progress('Tally master matching saved for '+str(record.get('invoice',{}).get('number') or Path(record['path']).name))
                except (ValueError,OSError,KeyError,TypeError) as exc:
                    warnings.append('Tally master matching unavailable; current creation method retained: '+str(exc))
                    if any(primary+' HTTP '+str(code) in str(exc) for code in (401,402,403,404,429)):break
    # A worker/report failure must not discard saved successes or trigger retries.
    for record in pending:
        if token(record) not in decisions or decisions[token(record)]['status'] != 'extracted':
            retained = find_retained(root, record, primary)
            if retained:
                decisions[token(record)] = {'status': 'extracted', 'provider': retained['provider'], 'cached': True}
            else:
                decisions.setdefault(token(record), {'status': 'local fallback', 'provider': 'Python', 'cached': False})
    for client in {r['client'] for r in records}:
        enable(root, client)
    if confirm_test:
        from .source_documents import confirm_test_document
        for record in records:
            if selected(record):
                try:
                    verify_source(root, record)
                    confirm_test_document(root, record)
                except (ValueError, OSError, KeyError, TypeError):
                    warnings.append('A source test-data confirmation could not be retained; source remains for review.')
    status_map = {token(record): decisions[token(record)] for record in records}
    summary = {
        'mode': 'desktop_ai_first', 'primary_provider': primary,
        'master_matching_clients': sorted(bound_clients),
        'master_matching_attempts': budget.used-matching_start,
        'input_invoices': len(records), 'new_ai_attempts': budget.used,
        'new_ai_attempt_limit': budget.limit,
        'ai_read_invoices': sum(d['status'] == 'extracted' for d in decisions.values()),
        'approved_reviews_retained': sum(d['status'] == 'approved_review' for d in decisions.values()),
        'local_or_review_fallbacks': sum(d['status'] not in ('extracted', 'approved_review') for d in decisions.values()),
        'ai_stopped': bool(stop_event and stop_event.is_set()), 'warnings': warnings,
        'xml_prepared': 0, 'tally_imports': 0,
        'sources': [{'client': r['client'], 'path': r['path'], 'digest': r.get('digest'),
                     **decisions[token(r)]} for r in records]}
    progress('AI stage finished. Python is now validating retained/extracted values and preparing client XML.')
    try:
        updated = process_sources(root, demo, client_names, auto_units, summary_accounting,
                                  reading_status=status_map)
        summary['xml_prepared'] = sum(bool(r.get('output_path')) and not r.get('errors') for r in updated)
        from .workflow_validation import enabled as workflow_enabled
        if workflow_enabled(root):
            summary['xml_ready']=sum(bool(r.get('output_path')) and r.get('workflow_ready',False) for r in updated)
            summary['workflow_review_required']=sum(bool(r.get('workflow_issues')) for r in updated)
    except Exception as exc:
        summary['xml_error_type'] = type(exc).__name__
        try:
            write_json(root/'.invoice_app'/'AI_First_Last_Run.json', summary)
        except OSError:
            pass
        raise ValueError('AI results were retained, but Python XML conversion failed. Check AI_First_Last_Run.json.') from None
    try:
        write_json(root/'.invoice_app'/'AI_First_Last_Run.json', summary)
    except OSError:
        summary['warnings'].append('AI-first report could not be saved; prepared XML and saved reads remain available.')
    return updated, summary


def summary_text(summary):
    return (f'AI-first: {summary["ai_read_invoices"]} AI reads; '
            f'{summary["approved_reviews_retained"]} approved reviews reused; '
            f'{summary["local_or_review_fallbacks"]} Python/review fallbacks. '
            f'Python prepared {summary["xml_prepared"]} XML vouchers. No Tally import sent.'+
            (f' {summary["xml_ready"]} ready; {summary["workflow_review_required"]} need workflow review/correction.' if 'workflow_review_required' in summary else ''))

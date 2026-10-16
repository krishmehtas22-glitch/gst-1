"""Separate PDF -> evidence -> optional AI -> review XML workflow.

Never call Tally, modify the desktop workflow, or publish into its current XML.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

from .reader import read_invoice, validate, decimal, date_value
from .evaluate import discover_pdfs
from .ai_assist import assist, Budget
from .retained_audit import audit_retained


def retained_input(root, source, result):
    """Read matching human approvals/selected AI caches without updating them."""
    if root is None:
        return None
    root = Path(root).resolve()
    if not Path(source).resolve().is_relative_to(root):
        raise ValueError('Retained reading root does not own this source')
    digest = result['source_sha256']
    review = root/'.invoice_app'/'reviews'/(digest+'.json')
    if review.exists():
        saved = json.loads(review.read_text(encoding='utf-8'))
        if saved.get('source_sha256') != digest or saved.get('approved') is not True:
            raise ValueError('Saved review does not match this source/approval')
        invoice = saved.get('invoice')
        if not isinstance(invoice, dict) or not isinstance(invoice.get('items'), list):
            raise ValueError('Invalid retained review')
        return 'approved_review', deepcopy(invoice)
    from Common_Rules.api_selection import candidate
    invoice = candidate(root, {'path': str(source), 'digest': digest, 'invoice': result['invoice']})
    return ('selected_ai_cache', invoice) if invoice is not None else None


def export_review_xml(output, documents):
    from Common_Rules.tally_review_export import export_all, verify_vouchers
    from Common_Rules.tally_units import unit_symbol
    stage = Path(output)/'xml_workspace'
    inputs = stage/'inputs'
    inputs.mkdir(parents=True, exist_ok=False)
    records = []
    for index, document in enumerate(documents, 1):
        source = Path(document['source'])
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != document['result']['source_sha256']:
            raise ValueError('Source changed before XML preparation')
        client = document.get('client', 'Public reading review')
        client_dir = inputs/hashlib.sha256(client.encode()).hexdigest()[:16]
        client_dir.mkdir(exist_ok=True)
        path = client_dir/(f'{index:04d}_'+document['result']['source_sha256'][:16]+'.pdf')
        path.write_bytes(data)
        result = document['result']
        notes = list(result['warnings'])
        if result['review_required']:
            notes.append('Reading review required; source roles/item completeness are not approved.')
        if result['invoice'].get('currency') not in (None, '', 'INR'):
            notes.append('Foreign-currency source: exchange rate and Indian tax treatment require review; no currency conversion was performed.')
        if result.get('invoice_grouping_required'):
            notes.append('Multiple identifiers: invoice grouping is unresolved. Do not import this placeholder as a verified invoice.')
        record = {'client': client, 'path': str(path),
                  'source_path': str(path), 'digest': result['source_sha256'],
                  'source_sha256': result['source_sha256'],
                  'invoice': deepcopy(result['invoice']),
                  'errors': notes, 'notices': []}
        records.append(record)
    exported = export_all(stage, records, False)
    folders = sorted({Path(r['output_path']) for r in exported})
    count = 0
    transfer_review = []
    original_values = {d['result']['source_sha256']: deepcopy(d['result']['invoice']) for d in documents}
    for folder in folders:
        units = ET.parse(folder/'Units.xml')
        masters = ET.parse(folder/'Masters.xml')
        sales = ET.parse(folder/'Sales_Vouchers.xml')
        verify_vouchers(sales.getroot())
        symbols = {unit_symbol(u) for u in units.findall('.//UNIT')}
        stocks = {s.get('NAME'): s.findtext('BASEUNITS') for s in masters.findall('.//STOCKITEM')}
        if any(unit not in symbols for unit in stocks.values()):
            raise ValueError('Exported stock master references a missing unit')
        if any(i.findtext('STOCKITEMNAME') not in stocks for i in sales.findall('.//ALLINVENTORYENTRIES.LIST')):
            raise ValueError('Exported voucher references a missing stock master')
        count += len(sales.findall('.//VOUCHER'))
        by_guid = {v.findtext('GUID'): v for v in sales.findall('.//VOUCHER')}
        report = json.loads((folder/'Batch_Report.json').read_text(encoding='utf-8'))
        for row in report['invoices']:
            original = original_values[row['digest']]
            voucher = by_guid[row['voucher_guid']]
            expected_date = date_value(str(original.get('date') or ''))
            posted_date = voucher.findtext('DATE')
            if expected_date is None and posted_date:
                transfer_review.append({'source_sha256': row['digest'], 'field': 'date',
                                        'reason': 'Legacy source recovery supplied a date missing from the new read; check its role before import.'})
            elif expected_date and posted_date != expected_date.replace('-', ''):
                transfer_review.append({'source_sha256': row['digest'], 'field': 'date',
                                        'reason': 'Exported date differs from the source reading.'})
            amount = decimal(original.get('total'))
            if amount is None:
                transfer_review.append({'source_sha256': row['digest'], 'field': 'total',
                                        'reason': 'Exact source total was not available; review placeholder/derived posting.'})
    if count != len(documents):
        raise ValueError('Review XML source/voucher count mismatch')
    return {'folders': [str(p) for p in folders], 'voucher_count': count,
            'structurally_checked': True, 'live_tally_imported': False,
            'financial_accuracy_proven': False, 'field_transfer_review': transfer_review,
            'ready_for_automatic_import': False}


def run(paths, output, providers=(), maximum=0, xml=False, stop=lambda: False,
        progress=print, transport=None, cache_root=None, structured=True, source_root=None,
        guidance_root=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    budget = Budget(maximum)
    cache_root = Path(cache_root) if cache_root else output.parent/'reading_v3_ai_cache'
    documents = []
    failed = []
    for index, source in enumerate(paths, 1):
        source = Path(source)
        progress(f'Reading {index}/{len(paths)}: {source.name}')
        try:
            result = read_invoice(source)
            client = 'Public reading review'
            if source_root is not None:
                relative = source.resolve().relative_to(Path(source_root).resolve())
                client = relative.parts[0] if len(relative.parts)>1 else Path(source_root).name
            retained = None
            try:
                retained = retained_input(source_root, source, result)
            except (ValueError, KeyError, TypeError, OSError):
                result['warnings'].append('Retained source review/cache needs attention; no AI reread scheduled.')
                result['review_required'] = True
                result['source_kind'] = 'retained_reading_error'
            if retained:
                kind, invoice = retained
                result = audit_retained(result, kind, invoice)
            if structured and not result.get('source_kind'):
                from .structured import read_embedded, agrees_with_visible_source
                try:
                    embedded = read_embedded(source)
                except (ValueError, ET.ParseError):
                    embedded = None
                    result['warnings'].append('Embedded invoice data was invalid or ambiguous; local reading retained.')
                    result['review_required'] = True
                if embedded:
                    disagreements = agrees_with_visible_source(embedded, result)
                    if disagreements:
                        result['structured_candidate'] = embedded
                        result['warnings'].append('Embedded/visible invoice agreement not established for: '+', '.join(disagreements)+'. Attachment was not applied.')
                        result['review_required'] = True
                        embedded = None
                if embedded:
                    merged = deepcopy(result['invoice'])
                    merged.update(embedded['invoice'])
                    if not embedded['invoice']['items']:
                        merged['items'] = result['invoice'].get('items', [])
                    result.update(invoice=merged, source_kind='embedded_cii', review_required=True,
                                  structured_attachment=embedded['attachment_name'], checks=validate(merged))
                    result['warnings'].extend(embedded['warnings'])
            ai_status = 'not_requested'
            from .teaching import match_guidance
            try:
                result['reading_guidance'] = match_guidance(result, guidance_root)
            except (ValueError, OSError, KeyError, TypeError):
                result['reading_guidance'] = {'status': 'invalid_library', 'rules': []}
            guidance_status = result['reading_guidance']['status']
            if guidance_status in {'invalid_library', 'ambiguous_rules', 'layout_changed_review'}:
                result['warnings'].append('Saved reading guidance needs review: '+guidance_status+'. No rule was applied.')
                result['review_required'] = True
                result['validation_review_required'] = True
            # Quota/unknown failures stop the current run's AI calls, retaining
            # successful reads and processing later sources locally.
            for provider in providers:
                if result.get('source_kind') in {'approved_review', 'selected_ai_cache', 'retained_reading_error'}:
                    ai_status = result['source_kind']
                    break
                if result.get('source_kind') == 'embedded_cii' and result['invoice'].get('items'):
                    ai_status = 'structured_invoice_used'
                    break
                if (not result['review_required'] and not result.get('legacy_fallback_fields')
                        and guidance_status != 'matched'):
                    ai_status = 'local_review_checks_passed'
                    break
                attempts_before = budget.used
                try:
                    response = assist(source, result, cache_root, budget,
                                      provider=provider, stop=stop, transport=transport)
                except ValueError:
                    ai_status = 'evidence_or_configuration_rejected'
                    if budget.used > attempts_before:
                        result['reading_guidance_usage'] = {
                            'status': 'request_attempted_no_accepted_result',
                            'rule_ids': [r['id'] for r in result['reading_guidance']['rules']]}
                    continue
                ai_status = response['status']
                result = response['result']
                if budget.used > attempts_before and ai_status not in {'cached', 'extracted'}:
                    result['reading_guidance_usage'] = {
                        'status': 'request_attempted_no_accepted_result',
                        'rule_ids': [r['id'] for r in result['reading_guidance']['rules']]}
                if ai_status in {'cached', 'extracted'} or budget.stopped:
                    break
            if 'reading_guidance_usage' not in result:
                result['reading_guidance_usage'] = {'status': 'not_sent_to_ai', 'rule_ids': [],
                                                    'reason': ai_status}
            if ai_status not in {'not_requested', 'cached', 'extracted', 'local_review_checks_passed', 'structured_invoice_used', 'approved_review', 'selected_ai_cache'}:
                result['warnings'].append('AI assistance status: '+ai_status+'; local reading retained.')
                result['review_required'] = True
            filename = f'{index:04d}_{result["source_sha256"][:16]}.json'
            (output/filename).write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
            documents.append({'source': str(source.resolve()), 'result_file': filename,
                              'client': client, 'ai_status': ai_status, 'result': result})
        except Exception as exc:
            # Avoid printing provider response bodies, keys or uncontrolled errors.
            failed.append({'source': str(source.resolve()), 'error_type': type(exc).__name__,
                           'status': 'read_or_evidence_failed'})
    summary = {'mode': 'isolated_review_workflow', 'input_pdfs': len(paths),
               'read_pdfs': len(documents), 'failed_pdfs': len(failed),
               'review_required': sum(d['result']['review_required'] for d in documents),
               'validation_review_required': sum(d['result'].get('validation_review_required',
                   d['result']['review_required']) for d in documents),
               'retained_human_approvals': sum(d['result'].get('approval_status') == 'retained_human_approval'
                   for d in documents),
               'source_verified_unit_metadata': sum(len(d['result'].get('unit_metadata_corrections', []))
                   for d in documents),
               'matched_reading_guidance': sum(d['result']['reading_guidance']['status'] == 'matched'
                   for d in documents),
               'new_ai_reads_with_guidance': sum(d['result']['reading_guidance_usage']['status'] == 'used_for_new_request'
                   and bool(d['result']['reading_guidance_usage']['rule_ids']) for d in documents),
               'ai_requests': budget.used, 'ai_request_limit': maximum,
               'ai_stopped': budget.stopped, 'active_app_changed': False,
               'ai_disabled_providers': sorted(budget.disabled),
               'tally_imports': 0, 'accuracy_measured': False,
               'documents': [{k: v for k, v in d.items() if k != 'result'} for d in documents],
               'failures': failed}
    if xml and documents:
        summary['xml'] = export_review_xml(output, documents)
    (output/'Workflow_Summary.json').write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description='Separate evidence-based reader with optional AI and review XML; never imports into Tally.')
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--xml', action='store_true', help='Create separate Units/Masters/Sales XML for review.')
    parser.add_argument('--ai-provider', choices=['Groq', 'Gemini'], action='append', default=[])
    parser.add_argument('--max-ai-requests', type=int, default=0)
    parser.add_argument('--text-only', action='store_true', help='Disable embedded CII reading for visual/text benchmark comparison.')
    parser.add_argument('--guidance-root', type=Path, help='Optional folder containing the shared .invoice_app/reading_guidance.json library.')
    args = parser.parse_args()
    if not 0 <= args.max_ai_requests <= 50:
        parser.error('AI request budget must be between 0 and 50.')
    paths = discover_pdfs(args.folder)
    if not paths:
        parser.error('No PDFs found.')
    parent = args.folder if args.folder.is_dir() else args.folder.parent
    source_root = parent
    if not (parent/'.invoice_app').is_dir() and (parent.parent/'.invoice_app').is_dir():
        source_root = parent.parent
    output = args.output or parent/'.invoice_app'/'reading_v3_runs'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    try:
        result = run(paths, output, args.ai_provider, args.max_ai_requests, args.xml,
                     structured=not args.text_only, source_root=source_root, guidance_root=args.guidance_root)
    except KeyboardInterrupt:
        raise SystemExit('Stopped. Completed reports/caches remain on disk; no Tally import was sent.')
    print('Report: '+str(output.resolve()/'Workflow_Summary.json'))
    print(f'Read {result["read_pdfs"]}/{result["input_pdfs"]} PDFs; AI requests {result["ai_requests"]}. No Tally imports sent.')
    print(f'Current validation issues: {result["validation_review_required"]}; retained human approvals: {result["retained_human_approvals"]}; source-verified unit labels: {result["source_verified_unit_metadata"]}.')
    print(f'Matched saved reading rules: {result["matched_reading_guidance"]}; new AI reads using them: {result["new_ai_reads_with_guidance"]}.')
    print('Separate experimental XML still requires review before import; financial accuracy is not certified.')
    if result['failed_pdfs']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

"""Audit retained readings without rewriting their saved approvals or caches."""
from copy import deepcopy

from .reader import equal, date_value, validate


def audit_retained(result, kind, invoice):
    invoice = deepcopy(invoice)
    result['local_reading_audit'] = {name: deepcopy(result.get(name, [])) for name in
        ('warnings', 'conflicts', 'checks', 'legacy_fallback_fields')}
    warnings = list(result['document'].get('warnings', []))
    conflicts = []
    checks = validate(invoice)
    # The evidence belongs to this PDF, but the invoice being checked has changed.
    # Do not reuse warnings/checks describing the superseded local parse.
    for field, evidence in result.get('field_evidence', {}).items():
        if not evidence or evidence.get('origin') not in ('positioned_label', 'positioned_masthead'):
            continue
        raw = evidence.get('raw_text', '')
        value = invoice.get(field)
        if value in (None, ''):
            continue
        matches = (date_value(str(value)) == date_value(raw) and date_value(raw) is not None
                   if field == 'date' else equal(value, raw, field))
        if not matches:
            conflicts.append({'field': field, 'retained_value': value,
                              'visible_value': raw, 'resolution': 'Retained value preserved; review required.'})
    rows = [row for table in result.get('table_candidates', []) for row in table['rows']]
    items = invoice.get('items', [])
    complete = bool(rows) and len(rows) == len(items) and not any(
        table.get('warnings') for table in result.get('table_candidates', []))
    matched = complete and all(all(equal(item.get(field), row['values'].get(field), field)
        for field in ('name', 'hsn', 'quantity', 'unit', 'rate', 'value'))
        for item, row in zip(items, rows))
    checks.append({'check': 'retained_items_visible_agreement',
                   'status': 'pass' if matched else 'review'})
    changes = []
    if matched and kind != 'approved_review':
        for index, (item, row) in enumerate(zip(items, rows), 1):
            evidence = row['evidence'].get('unit')
            if not evidence or evidence.get('origin') != 'positioned_table' or not evidence.get('token_ids'):
                continue
            if item.get('unit_origin') == 'manual' or item.get('unit_correction_reviewed'):
                continue
            previous = {k: deepcopy(v) for k, v in item.items() if k.startswith('unit_')}
            item.update(unit_basis='printed', unit_origin='printed', unit_auto=False,
                        unit_reason='Verified printed UOM in the matching source row',
                        unit_evidence='Source row: '+evidence['raw_text'])
            # No model confidence is invented from token agreement.
            item.pop('unit_confidence', None)
            changes.append({'item': index, 'previous_metadata': previous, 'source_evidence': evidence})
    for index, item in enumerate(items, 1):
        if (item.get('unit_origin') != 'manual' and not item.get('unit_correction_reviewed') and
                (item.get('unit_auto') or item.get('unit_basis') == 'inferred')):
            checks.append({'check': 'unverified_unit_assumption', 'item': index, 'status': 'review'})
    if conflicts:
        warnings.append('Retained values disagree with positioned source evidence; retained values were preserved.')
    if result.get('invoice_grouping_required'):
        warnings.append('Multiple invoice identifiers require grouping review.')
    if result.get('document_kind') != 'invoice_candidate':
        warnings.append('Document type requires review before treating it as a sales invoice.')
    issues = bool(conflicts or warnings or any(c['status'] != 'pass' for c in checks))
    result.update(invoice=invoice, source_kind=kind, checks=checks, conflicts=conflicts,
                  warnings=warnings, validation_review_required=issues,
                  review_required=True, automatic_import_enabled=False,
                  approval_status='retained_human_approval' if kind == 'approved_review' else 'unapproved_saved_ai',
                  review_reasons=(['current_validation_issues'] if issues else []) +
                      ['experimental_workflow_requires_review'],
                  unit_metadata_corrections=changes,
                  notices=['Existing source approval/selected AI read retained without another API request.'])
    return result

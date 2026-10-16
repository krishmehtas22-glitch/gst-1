from copy import deepcopy

import pytest

from Reading_V2.retained_audit import audit_retained


def example():
    item = dict(name='Widget', hsn='1234', quantity='2', unit='PCS', rate='5', value='10',
                unit_origin='ai_assumed', unit_basis='inferred', unit_auto=True)
    invoice = dict(number='INV-1', date='2026-01-02', seller_name='Seller', buyer_name='Buyer',
                   total='10', taxable='10', items=[item])
    result = dict(invoice=deepcopy(invoice), document={'warnings': []},
        field_evidence={'buyer_name': {'origin': 'positioned_label', 'raw_text': 'Buyer'}},
        table_candidates=[{'rows': [{'values': deepcopy(item), 'evidence': {'unit':
            {'origin': 'positioned_table', 'raw_text': 'PCS', 'token_ids': ['p1w1']}}}], 'warnings': []}],
        warnings=['Ambiguous buyer_name: label and layout values differ'], conflicts=[],
        checks=[], legacy_fallback_fields=[], document_kind='invoice_candidate')
    return result, invoice


def test_verified_printed_unit_changes_metadata_only_and_archives_local_warnings():
    result, invoice = example()
    original = deepcopy(invoice)
    answer = audit_retained(result, 'selected_ai_cache', invoice)
    assert invoice == original
    item = answer['invoice']['items'][0]
    assert item['unit_basis'] == item['unit_origin'] == 'printed'
    assert item['unit_auto'] is False
    assert all(item[k] == original['items'][0][k] for k in ('name','hsn','quantity','unit','rate','value'))
    assert answer['warnings'] == [] and not answer['validation_review_required']
    assert answer['local_reading_audit']['warnings']
    assert answer['review_required'] and not answer['automatic_import_enabled']


@pytest.mark.parametrize('field,value', [('name','Other'), ('quantity','3'), ('unit','BOX'), ('rate','6')])
def test_nonmatching_row_keeps_assumption_and_requires_review(field, value):
    result, invoice = example()
    result['table_candidates'][0]['rows'][0]['values'][field] = value
    answer = audit_retained(result, 'selected_ai_cache', invoice)
    assert answer['invoice'] == invoice
    assert not answer['unit_metadata_corrections']
    assert answer['validation_review_required']


def test_human_approval_is_preserved_exactly_without_erasing_real_conflict():
    result, invoice = example()
    invoice['buyer_name'] = 'Human Corrected Buyer'
    answer = audit_retained(result, 'approved_review', invoice)
    assert answer['invoice'] == invoice
    assert answer['approval_status'] == 'retained_human_approval'
    assert answer['conflicts'][0]['field'] == 'buyer_name'
    assert answer['validation_review_required']


def test_valid_human_approval_has_separate_status_from_experimental_review():
    result, invoice = example()
    invoice['items'][0]['unit_origin'] = 'manual'
    invoice['items'][0]['unit_auto'] = False
    answer = audit_retained(result, 'approved_review', invoice)
    assert answer['invoice'] == invoice
    assert not answer['validation_review_required']
    assert answer['approval_status'] == 'retained_human_approval'
    assert answer['review_reasons'] == ['experimental_workflow_requires_review']


def test_missing_printed_unit_evidence_cannot_clear_assumption():
    result, invoice = example()
    result['table_candidates'][0]['rows'][0]['evidence'] = {}
    answer = audit_retained(result, 'selected_ai_cache', invoice)
    assert answer['invoice'] == invoice and not answer['unit_metadata_corrections']
    assert answer['validation_review_required']

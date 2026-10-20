"""Isolated MD experiment: raw replies retained, no app or accounting mutation."""
import json
from pathlib import Path
import re
import pytest
from reportlab.pdfgen.canvas import Canvas
import Test_MD_Extraction as test_reader


def invoice(tmp_path):
    path = tmp_path / 'invoice.pdf'
    canvas = Canvas(str(path))
    canvas.drawString(30, 700, 'Tax Invoice INV/0042 - Seller Example - GSTIN 27INVALID0000Z0')
    canvas.save()
    return path


def test_system_prompt_and_output_shape_match_uploaded_spec_exactly():
    blocks = re.findall(r'```[^\n]*\n(.*?)\n```', test_reader.MD_SPEC, re.S)
    payload = test_reader.payload_for('sample.pdf', 2, 'INVOICE SOURCE', 'test-model')
    assert payload['messages'][0]['content'] == blocks[0]
    assert payload['messages'][1]['content'].endswith(blocks[2])
    assert 'INVOICE SOURCE' in payload['messages'][1]['content']
    assert '{if masters enabled:}' not in payload['messages'][1]['content']


@pytest.mark.parametrize('provider', ['Groq', 'Gemma'])
def test_raw_invalid_gstin_is_not_checked_or_corrected(tmp_path, provider):
    source = invoice(tmp_path); original = source.read_bytes(); calls = []
    answer = '{"invoices":[{"seller":{"gstin":"27INVALID0000Z0"},"items":[]}]}'
    def transport(payload, selected):
        calls.append(selected)
        if selected == 'Groq':
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': answer}}]}
        return {'done': True, 'done_reason': 'stop', 'message': {'content': answer}}
    folder = test_reader.run(source, provider, True, tmp_path / 'output', transport)
    assert calls == [provider]
    assert (folder / 'AI_Response.txt').read_text() == answer
    assert json.loads((folder / 'AI_Output.json').read_text())['invoices'][0]['seller']['gstin'] == '27INVALID0000Z0'
    report = json.loads((folder / 'Test_Report.json').read_text())
    assert report['gstin_checksum_checked'] is False and report['tally_imports'] == 0
    assert report['request_attempts'] == 1 and report['xml_generated'] is False
    assert source.read_bytes() == original
    assert not (tmp_path / '.invoice_app').exists()


def test_dry_run_never_calls_provider(tmp_path):
    folder = test_reader.run(invoice(tmp_path), 'Gemma', False, tmp_path / 'output', lambda *a: pytest.fail('No consent'))
    report = json.loads((folder / 'Test_Report.json').read_text())
    assert report['request_attempts'] == 0
    assert not (folder / 'AI_Response.txt').exists()


def test_incomplete_invalid_json_is_retained_without_retry(tmp_path):
    calls = []
    def transport(*args):
        calls.append(1)
        return {'choices': [{'finish_reason': 'length', 'message': {'content': '{"invoices":['}}]}
    folder = test_reader.run(invoice(tmp_path), 'Groq', True, tmp_path / 'output', transport)
    assert len(calls) == 1 and (folder / 'AI_Response.txt').read_text() == '{"invoices":['
    report = json.loads((folder / 'Test_Report.json').read_text())
    assert report['valid_json'] is False and report['response_complete'] is False

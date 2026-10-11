from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from reportlab.pdfgen import canvas

from Common_Rules.accounting import gstin_valid, validate
from Common_Rules.demo import prepare_demo_invoice
from Common_Rules.engine import init_demo_client, inspect_invoices, read_json, run, write_json
from Common_Rules.extraction import parse_text
from helpers import gstin


def banner_text(number='SAMPLE-001', inter=False, consumer=False, rate=18):
    state = '29' if inter else '27'
    buyer = 'Unregistered' if consumer else gstin(state, 'PQRSX5678L')
    component = rate if inter else rate / 2
    amount = 250 * component / 100
    tax = f'IGST ({component:g}%)      {amount:.2f}' if inter else f'CGST ({component:g}%)      {amount:.2f}\nSGST ({component:g}%)      {amount:.2f}'
    return f'''Example Synthetic Supplier      TAX INVOICE
Fictional seller | Maharashtra | GSTIN: NOT ASSIGNED      TEST DOCUMENT - NOT VALID FOR FILING
INVOICE NO.      INVOICE DATE      TYPE
{number}      01 Oct 2026      {'B2C' if consumer else 'B2B'}
BILL TO
Example Synthetic Customer {state}{' Consumer' if consumer else ''}
Customer GSTIN: {buyer}
Place of supply (state code): {state}
ITEM DETAILS
Description      HSN      Qty      Rate      Amount
Example product      4820      2      125.00      250.00
Taxable value      250.00
{tax}
INVOICE TOTAL      {250 * (1 + rate / 100):.2f}
All parties, GSTINs, HSN mappings and rates are synthetic examples for automation testing.
DUMMY / NOT FOR COMMERCIAL USE'''


def banner_pdf(path, text):
    out = canvas.Canvas(str(path))
    out.setFont('Courier', 7)
    for index, line in enumerate(text.splitlines()):
        out.drawString(25,810-index*16,line)
    out.save()


def config(root):
    folder = init_demo_client(root,'Test Client','abc','Maharashtra','Nos')
    return folder, read_json(folder/'client.json')


def test_extract_grid_banner_and_summary_without_inventing_missing_fields():
    inv = parse_text(banner_text())
    assert inv['number'] == 'SAMPLE-001'
    assert inv['date'] == '2026-10-01'
    assert inv['seller_name'] == 'Example Synthetic Supplier'
    assert inv['seller_gstin'] == 'NOT ASSIGNED'
    assert inv['seller_state'] == 'Maharashtra'
    assert inv['buyer_name'] == 'Example Synthetic Customer 27'
    assert inv['cgst'] == inv['sgst'] == '22.50'
    assert inv['items'][0]['cgst_rate'] == '9'
    assert 'unit' not in inv['items'][0]
    assert 'igst' not in inv
    assert 'buyer_registration' not in inv
    assert inv['classification'] == 'taxable'
    assert inv['dummy_document'] is True
    assert not inv['extraction_warnings']


def test_explicit_unregistered_label_is_not_a_gstin_or_exemption():
    inv = parse_text(banner_text(consumer=True))
    assert inv['buyer_gstin'] == ''
    assert inv['buyer_registration'] == 'Unregistered'
    assert inv['classification'] == 'taxable'
    assert 'buyer_state' not in inv


def test_conflicting_grid_and_label_stays_ambiguous():
    inv = parse_text(banner_text() + '\nInvoice Number: ANOTHER')
    assert 'number' not in inv
    assert any('Ambiguous number' in message for message in inv['extraction_warnings'])


@pytest.mark.parametrize('inter,consumer', [(False,False),(True,False),(False,True),(True,True)])
def test_demo_substitutions_are_recorded_and_still_pass_accounting(tmp_path,inter,consumer):
    _, cfg = config(tmp_path)
    raw = parse_text(banner_text(inter=inter,consumer=consumer))
    original = deepcopy(raw)
    demo = prepare_demo_invoice(raw,cfg)
    assert raw == original
    assert demo['demo_source_invoice'] == original
    assert demo['demo_only'] is True
    assert demo['items'][0]['unit'] == 'Nos'
    assert '[DEMO HSN 4820 GST 18%]' in demo['items'][0]['name']
    assert gstin_valid(demo['seller_gstin'])
    assert not validate(demo,cfg)[1]
    assert {change['field'] for change in demo['demo_adjustments']} >= {'seller_gstin','unit','name'}
    if consumer:
        assert demo['buyer_gstin'] == ''
    else:
        assert gstin_valid(demo['buyer_gstin'])


def test_invalid_synthetic_buyer_checksum_is_corrected_only_in_demo_copy(tmp_path):
    _, cfg = config(tmp_path)
    raw = parse_text(banner_text())
    valid = raw['buyer_gstin']
    raw['buyer_gstin'] = valid[:-1] + ('0' if valid[-1] != '0' else '1')
    demo = prepare_demo_invoice(raw,cfg)
    assert demo['buyer_gstin'] == valid
    assert demo['demo_source_invoice']['buyer_gstin'] == raw['buyer_gstin']
    assert any(change['field'] == 'buyer_gstin' for change in demo['demo_adjustments'])


@pytest.mark.parametrize('change', [
    {'dummy_document':False}, {'seller_gstin':gstin()}, {'seller_state':'Karnataka'},
    {'extraction_warnings':['Ambiguous total']}, {'invoice_type':'Export'},
    {'buyer_registration':'Composition'}, {'buyer_state':'29'},
])
def test_demo_rejects_unmarked_real_or_ambiguous_source(tmp_path,change):
    _, cfg = config(tmp_path)
    raw = parse_text(banner_text())
    raw.update(change)
    with pytest.raises(ValueError):
        prepare_demo_invoice(raw,cfg)


def test_demo_unit_does_not_overwrite_a_conflicting_printed_unit(tmp_path):
    _, cfg = config(tmp_path)
    raw = parse_text(banner_text())
    raw['items'][0]['unit'] = 'Kg'
    with pytest.raises(ValueError, match='Printed unit conflicts'):
        prepare_demo_invoice(raw,cfg)


def test_demo_wrong_amount_is_blocked_by_accounting(tmp_path):
    folder, _ = config(tmp_path)
    banner_pdf(folder/'wrong.pdf',banner_text().replace('INVOICE TOTAL      295.00','INVOICE TOTAL      999.00'))
    result = run(tmp_path)['clients'][0]
    assert result['counts']['review'] == 1
    assert result['pending_validated'] == 0
    assert not (folder/'imports'/'Sales_Vouchers.xml').exists()
    assert any('Invoice total does not balance' in str(issue) for issue in result['issues'])


def test_demo_cannot_be_validated_with_production_config(tmp_path):
    _, cfg = config(tmp_path)
    demo = prepare_demo_invoice(parse_text(banner_text()),cfg)
    production = dict(cfg)
    del production['demo_only']
    assert any('Demo invoices require a demo client' in issue for issue in validate(demo,production)[1])


def test_demo_batch_rate_variants_and_repeat_run(tmp_path):
    folder, cfg = config(tmp_path)
    for n in range(4):
        banner_pdf(folder/f'{n}.pdf',banner_text(f'SAMPLE-{n}',inter=bool(n%2),consumer=n==3,rate=5 if n==1 else 18))
    first = run(tmp_path)['clients'][0]
    assert first['counts']['new'] == first['pending_validated'] == 4, first['issues']
    assert not first['issues']
    vouchers = ET.parse(folder/'imports'/'Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers) == 4
    assert all(v.findtext('NARRATION').startswith('DEMO ONLY') for v in vouchers)
    assert read_json(folder/'imports'/'manifest.json')['demo_only'] is True
    assert 'DEMO ONLY' in (folder/'imports'/'Masters.xml').read_text()
    audit = read_json(folder/'reports'/'demo_adjustments.json')
    assert len(audit['invoices']) == 4
    assert all(record['printed_invoice']['seller_gstin'] == 'NOT ASSIGNED' for record in audit['invoices'])
    again = run(tmp_path)['clients'][0]
    assert again['counts']['new'] == 0
    assert again['counts']['duplicate'] == 4
    assert not again['issues']
    cfg['demo_only'] = False
    write_json(folder/'client.json',cfg)
    blocked = run(tmp_path)['clients'][0]
    assert blocked['pending_validated'] == 0
    assert not (folder/'imports'/'Sales_Vouchers.xml').exists()


def test_inspection_works_without_client_setup_and_does_not_modify_imports(tmp_path):
    folder = tmp_path/'Unconfigured Client'
    folder.mkdir()
    banner_pdf(folder/'sample.pdf',banner_text())
    imports = folder/'imports'
    imports.mkdir()
    existing = imports/'Sales_Vouchers.xml'
    existing.write_text('existing output')
    summary = inspect_invoices(folder)
    assert summary['pdf_count'] == summary['extracted_invoice_count'] == 1
    assert summary['printed_totals_balanced'] == 1
    assert summary['needs_review'] == 1
    assert summary['xml_generated'] is False
    assert not (folder/'client.json').exists()
    assert not (folder/'.automation').exists()
    assert existing.read_text() == 'existing output'
    findings = read_json(Path(summary['report']))['invoices'][0]['issues']
    assert 'Item 1: missing unit' in findings
    assert 'Seller GSTIN is missing, unassigned or invalid' in findings


def test_demo_and_inspection_cli(tmp_path):
    script = Path(__file__).resolve().parents[1]/'main.py'
    initialized = subprocess.run([sys.executable,str(script),'--root',str(tmp_path),
        'init-demo-client','Example','--company','abc','--state','Maharashtra','--unit','Nos'],capture_output=True,text=True)
    assert initialized.returncode == 0, initialized.stderr
    assert '"demo_only": true' in initialized.stdout
    banner_pdf(tmp_path/'Example'/'sample.pdf',banner_text())
    inspected = subprocess.run([sys.executable,str(script),'--root',str(tmp_path),
        'inspect-invoices','Example'],capture_output=True,text=True)
    assert inspected.returncode == 0, inspected.stderr
    assert '"extracted_invoice_count": 1' in inspected.stdout

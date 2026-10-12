from pathlib import Path
import pytest

from Common_Rules.accounting import validate
from Common_Rules.demo import prepare_demo_invoice
from Common_Rules.engine import init_demo_client, read_json
from Common_Rules.extraction import parse_text


def text():
    return (Path(__file__).parent/'fixtures/paired_intra.txt').read_text()


def configuration(tmp_path):
    client = init_demo_client(tmp_path,'CLIENT 7','CLIENT 7','Maharashtra','Nos')
    return read_json(client/'client.json')


def test_uploaded_multi_item_layout_and_demo_accounting(tmp_path):
    raw = parse_text(text())
    assert raw['number'] == 'TEST-26-27-001'
    assert raw['date'] == '2026-10-02'
    assert raw['seller_name'] == 'Western Trade Supplies'
    assert raw['buyer_name'] == 'Mumbai Retail Mart'
    assert raw['buyer_gstin'] == '27TESTA1000A1Z5'
    assert raw['total'] == '25960.00'
    assert len(raw['items']) == 2
    assert [item['hsn'] for item in raw['items']] == ['940320','940130']
    assert raw['extraction_warnings'] == []
    config = configuration(tmp_path)
    prepared = prepare_demo_invoice(raw,config)
    assert prepared['demo_source_invoice'] == raw
    assert raw['items'][0]['unit'] == 'NOS'
    assert prepared['items'][0]['unit'] == 'Nos'
    assert any(change['field'] == 'buyer_gstin' for change in prepared['demo_adjustments'])
    _, errors = validate(prepared,config)
    assert errors == []


@pytest.mark.parametrize('before,after', [
    ('DEMO DOCUMENT - NOT VALID FOR GST FILING OR COMMERCIAL USE','TAX INVOICE'),
    ('GSTIN (fictional):','GSTIN:'),
    ('Reverse charge: No','Reverse charge: Yes'),
    ('Supply: INTRA','Supply: EXPORT'),
    ('900.00','901.00'),
    ('18%','17%'),
    ('NOS','KG'),
])
def test_unmarked_unsupported_or_inconsistent_input_rejected(tmp_path,before,after):
    raw = parse_text(text().replace(before,after))
    with pytest.raises(ValueError):
        prepare_demo_invoice(raw,configuration(tmp_path))


def test_bad_summary_still_fails_accounting(tmp_path):
    raw = parse_text(text().replace('25,960.00','25,961.00'))
    config = configuration(tmp_path)
    _, errors = validate(prepare_demo_invoice(raw,config),config)
    assert errors

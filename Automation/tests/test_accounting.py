from copy import deepcopy
from decimal import Decimal
import pytest

from Common_Rules.accounting import accounting_entries, gstin_valid, invoice_key, money, validate
from Common_Rules.engine import read_json
from Common_Rules.extraction import parse_text
from Common_Rules.masters import plan_masters, required_masters
from helpers import client, gstin, invoice


@pytest.mark.parametrize('kind,credit_ledgers', [
    ('intra',['Sales','Output CGST','Output SGST']),
    ('inter',['Sales','Output IGST']),
    ('exempt',['Exempt Sales'])])
def test_balanced_sales(tmp_path,kind,credit_ledgers):
    config = read_json(client(tmp_path) / 'client.json')
    inv, errors = validate(invoice(kind=kind),config)
    assert not errors
    rows = accounting_entries(inv,config)
    assert [r['ledger'] for r in rows[1:]] == credit_ledgers
    assert sum(money(r['debit']) - money(r['credit']) for r in rows) == Decimal('0')


def test_gstin_checksum():
    assert gstin_valid(gstin())
    assert not gstin_valid(gstin()[:-1] + ('0' if gstin()[-1] != '0' else '1'))


@pytest.mark.parametrize('mutation,fragment', [
    (lambda i:i.update(total='2300'), 'Invoice total'),
    (lambda i:i.update(total='2360.01'), 'Invoice total'),
    (lambda i:i.update(cgst='179'), 'CGST amount'),
    (lambda i:i.update(place_of_supply='29'), 'inter-state sale'),
    (lambda i:i.update(buyer_registration='Unregistered'), 'conflicts with unregistered'),
    (lambda i:i.update(classification='exempt'), 'conflicts with GST'),
    (lambda i:i['items'][0].update(quantity='3'), 'quantity × rate'),
    (lambda i:i['items'][0].update(hsn='12'), 'invalid HSN'),
    (lambda i:i.update(cess='20'), 'Cess requires'),
    (lambda i:i.update(total='NaN'), 'Non-finite'),
    (lambda i:i.update(seller_gstin=gstin('29')), 'does not match'),
])
def test_invalid_data_goes_to_review(tmp_path,mutation,fragment):
    config = read_json(client(tmp_path) / 'client.json')
    inv = invoice()
    mutation(inv)
    _, errors = validate(inv,config)
    assert any(fragment in error for error in errors)


def test_unregistered_is_not_exempt(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    inv = invoice()
    inv.update(buyer_gstin='',buyer_registration='Unregistered')
    normalized, errors = validate(inv,config)
    assert not errors
    assert normalized['classification'] == 'taxable'
    assert accounting_entries(normalized,config)[1]['ledger'] == 'Sales'
    del inv['classification']
    assert 'Missing classification' in validate(inv,config)[1]


def test_fiscal_year_boundary():
    first = invoice()
    first['date'] = '2026-03-31'
    second = dict(first, date='2026-04-01')
    assert invoice_key(first) != invoice_key(second)


def test_master_reuse_conflict_and_dependency_order(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    inv, errors = validate(invoice(),config)
    assert not errors
    needed, errors = plan_masters({'a':inv}, config, [])
    assert not errors
    assert needed[0]['kind'] == 'unit'
    assert needed[-1]['kind'] == 'stock_item'
    assert len({(m['kind'],m['name']) for m in needed}) == len(needed)
    assert plan_masters({'a':inv},config,needed) == ([], {})
    conflict = deepcopy(needed)
    customer = next(m for m in conflict if m.get('group') == 'Sundry Debtors')
    customer['gstin'] = gstin('27', 'XXXXX1111X')
    assert 'a' in plan_masters({'a':inv},config,conflict)[1]


def test_master_conflict_propagates_to_all_using_same_name(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    a, _ = validate(invoice('A'),config)
    b = deepcopy(a)
    b['items'][0]['hsn'] = '8504'
    c = deepcopy(a)
    _, errors = plan_masters({'a':a,'b':b,'c':c},config,[])
    assert set(errors) == {'a','b','c'}


def test_missing_unit_is_flagged(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    inv, _ = validate(invoice(),config)
    inv['items'][0]['unit'] = 'Kg'
    assert 'a' in plan_masters({'a':inv},config,[])[1]


def test_ambiguous_labels_and_layout_variation():
    inv = parse_text('Invoice Number = X\nInvoice Date: 01/04/2026\nGrand Total: 2360\nGrand Total: 2500')
    assert inv['number'] == 'X'
    assert inv['date'] == '2026-04-01'
    assert 'total' not in inv
    assert any('Ambiguous total' in e for e in inv['extraction_warnings'])


def test_separate_stock_group_dependency(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    config['stock_group'] = 'Appliances'
    inv, _ = validate(invoice(),config)
    masters = required_masters(inv,config)
    assert {'kind':'stock_group','name':'Appliances','parent':'Primary'} in masters


def test_unit_precision_conflict(tmp_path):
    config = read_json(client(tmp_path) / 'client.json')
    inv, _ = validate(invoice(),config)
    inv['items'][0]['quantity'] = '1.5'
    _, errors = plan_masters({'a':inv},config,[])
    assert 'precision conflicts' in errors['a'][0]

"""Only generated master names/references change; financial XML stays identical."""
from copy import deepcopy
from pathlib import Path
import json,re
import xml.etree.ElementTree as ET

from test_review_voucher_structure import record
from Common_Rules.tally_review_export import export_all,clean
from Common_Rules.plain_master_names import PlainMasterNames


def sample_rows(root):
    rows=[]
    for i in range(3):
        row=record(root);row['path']=f'/invoice-source/sale-{i+1}.pdf';row['digest']=chr(97+i)*64
        inv=row['invoice'];inv['number']=f'TEST-{i+1}';inv['buyer_name']=f'Customer {i+1}'
        for item in inv['items']:item['name']+=f' {i+1}'
        if i==2:
            inv.update(supply='EXPORT',classification='export_lut',cgst='0',sgst='0',total='22000')
        rows.append(row)
    return rows


def test_only_batch_suffix_changes_against_prechange_golden_xml(tmp_path):
    rows=sample_rows(tmp_path);original=deepcopy([r['invoice'] for r in rows])
    export_all(tmp_path,rows,True);output=Path(rows[0]['output_path'])
    fixture=Path(__file__).parent/'fixtures/plain_names_before'
    for filename in ('Units.xml','Masters.xml','Sales_Vouchers.xml'):
        before=(fixture/filename).read_text()
        expected=re.sub(r' \[batch [0-9a-f]+\]','',before)
        actual=(output/filename).read_text()
        assert ET.canonicalize(actual,strip_text=True)==ET.canonicalize(expected,strip_text=True)
    assert original==[r['invoice'] for r in rows]
    report=json.loads((output/'Batch_Report.json').read_text())
    assert all(r['buyer']==r['buyer_ledger'] for r in report['invoices'])
    assert report['xml_voucher_count']==3


def test_same_item_different_units_stays_separate_without_batch_hashes():
    rows=sample_rows(Path('/unused'))[:2]
    for row,unit in zip(rows,('PCS','KG')):
        row['invoice']['items']=[{**rows[0]['invoice']['items'][0],'name':'Material','unit':unit}]
    names=PlainMasterNames(rows,clean)
    assert [names.stock(r['invoice']['items'][0],r['invoice']) for r in rows]==['Material (PCS)','Material (KG)']


def test_same_party_different_gstin_and_reserved_ledgers_do_not_merge():
    rows=sample_rows(Path('/unused'))
    for row,gstin in zip(rows,('27AAA','29BBB','')):
        row['invoice'].update(buyer_name='Sales' if not gstin else 'Customer',buyer_gstin=gstin)
    names=PlainMasterNames(rows,clean)
    values=[names.party(r['invoice']['buyer_name'],r['invoice']['buyer_gstin'],r['invoice']) for r in rows]
    assert len(set(values))==3 and all('[batch' not in name for name in values)
    assert values[:2]==['Customer (GSTIN 27AAA)','Customer (GSTIN 29BBB)']
    assert values[2]!='Sales'


def test_readable_variants_cannot_steal_another_printed_item_name():
    rows=sample_rows(Path('/unused'))
    for row,name,unit in zip(rows,('Material','Material','Material (PCS)'),('PCS','KG','PCS')):
        row['invoice']['items']=[{**row['invoice']['items'][0],'name':name,'unit':unit}]
    names=PlainMasterNames(rows,clean)
    assigned=[names.stock(r['invoice']['items'][0],r['invoice']) for r in rows]
    assert assigned[2]=='Material (PCS)' and len(set(assigned))==3


def test_same_named_parties_at_different_addresses_keep_separate_ledgers():
    rows=sample_rows(Path('/unused'))[:2]
    for row,address in zip(rows,('10 North Road','20 South Road')):
        row['invoice'].update(buyer_name='Retailer',buyer_gstin='',buyer_address=address)
    names=PlainMasterNames(rows,clean)
    labels=[names.party('Retailer','',r['invoice']) for r in rows]
    assert labels[0]!=labels[1] and '10 North Road' in labels[0] and '20 South Road' in labels[1]

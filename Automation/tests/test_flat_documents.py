"""Regression coverage for ordered embedded text and independent invoice pages."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from pypdf import PdfReader, PdfWriter
from Common_Rules.desktop import inspect_sources, process_sources, save_review, reset_source_reviews
from Common_Rules.engine import read_json
from Common_Rules.extraction import parse_text, text_from_pdf
from Common_Rules.source_documents import confirm_test_document, expand_source

FIXTURES=Path(__file__).parent/'fixtures/client15'


def setup(root, bundle=False):
    folder=root/('medical' if bundle else 'sales');folder.mkdir()
    paths=[FIXTURES/'GSTR1_Test_Invoices.pdf'] if bundle else sorted(FIXTURES.glob('Sales_Invoice*.pdf'))
    for path in paths:shutil.copy2(path,folder/path.name)
    return folder


def choose_unit(root,record,unit):
    inv=deepcopy(record['invoice']);inv['items'][0]['unit']=unit
    save_review(root,record,inv)


def vouchers(records):
    companies={Path(r['company_path']) for r in records if not r['errors']}
    return [v for company in companies for v in ET.parse(company/'imports/Sales_Vouchers.xml').findall('.//VOUCHER')]


def test_fifteen_styles_extract_fields_leave_individual_units_unresolved(tmp_path):
    folder=setup(tmp_path)
    originals={p.name:p.read_bytes() for p in folder.glob('*.pdf')}
    records=process_sources(tmp_path)
    assert len(records)==15
    assert [r['invoice']['number'] for r in records]==[f'DM/26-27/{i:04d}' for i in range(11,26)]
    for record in records:
        inv=record['invoice']
        assert inv['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED'
        assert inv['buyer_name'] and inv['seller_gstin']=='27ABCDE1234F1Z5'
        assert inv['dummy_document'] and not inv['extraction_warnings']
        assert inv['source_unit_note']=='Unit: Nos / Kg (as applicable)'
        assert 'unit' not in inv['items'][0]
        assert len(record['errors'])==1 and 'choose the quantity unit' in record['errors'][0]
        choose_unit(tmp_path,record,'KG' if inv['classification']=='exempt' else 'Nos')
    accepted=process_sources(tmp_path)
    assert all(not r['errors'] for r in accepted)
    assert len(vouchers(accepted))==15
    assert all(r['invoice']['items'][0]['unit']=='KG' for r in accepted[-3:])
    assert originals=={p.name:p.read_bytes() for p in folder.glob('*.pdf')}
    assert all(not r['errors'] for r in process_sources(tmp_path))
    export=accepted[11]['invoice']
    assert export['classification']=='export_lut' and export['items'][0]['printed_gst_rate']=='12'
    assert export['items'][0]['igst_rate']=='0' and export['igst']=='0.00'


def test_twenty_page_bundle_confirmation_and_individual_units(tmp_path):
    folder=setup(tmp_path,True);original=next(folder.glob('*.pdf'));source_bytes=original.read_bytes()
    records=process_sources(tmp_path)
    assert len(records)==20 and {r['source_path'] for r in records}=={str(original)}
    assert [r['page_number'] for r in records]==list(range(1,21))
    assert len({r['invoice']['number'] for r in records})==20
    assert all(r['invoice']['seller_name']=='MedTech Pharma Distributors' for r in records)
    assert all('Confirm test PDF' in '; '.join(r['errors']) for r in records)
    digests=[r['digest'] for r in records]
    confirm_test_document(tmp_path,records[0])
    records=process_sources(tmp_path)
    assert [r['digest'] for r in records]==digests
    assert all('choose the quantity unit' in '; '.join(r['errors']) for r in records[:5])
    assert all(not r['errors'] for r in records[5:])
    for record in records[:5]:choose_unit(tmp_path,record,'Nos') # Explicit test choice, never a reader default.
    records=process_sources(tmp_path)
    assert all(not r['errors'] for r in records)
    vs=vouchers(records);assert len(vs)==20
    ledger_amounts={}
    for v in vs:
        for node in v.findall('ALLLEDGERENTRIES.LIST')+v.findall('LEDGERENTRIES.LIST'):
            name=node.findtext('LEDGERNAME');ledger_amounts[name]=ledger_amounts.get(name,Decimal('0'))+Decimal(node.findtext('AMOUNT'))
        for node in v.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST'):
            name=node.findtext('LEDGERNAME');ledger_amounts[name]=ledger_amounts.get(name,Decimal('0'))+Decimal(node.findtext('AMOUNT'))
    assert ledger_amounts['Sales']==Decimal('18909500')
    assert ledger_amounts['Output CGST']==ledger_amounts['Output SGST']==Decimal('13420')
    assert ledger_amounts['Output IGST']==Decimal('70550')
    assert sum(Decimal(r['invoice']['total']) for r in records)==Decimal('19006890')
    assert source_bytes==original.read_bytes()
    assert all('fictional' in '; '.join(r['errors']) for r in process_sources(tmp_path,demo=False))


def test_bundle_reviews_and_confirmation_reject_changed_parent_pdf(tmp_path):
    folder=setup(tmp_path,True);record=inspect_sources(tmp_path)[0]
    Path(record['source_path']).write_bytes(Path(record['source_path']).read_bytes()+b'\nchanged')
    for action in (lambda:save_review(tmp_path,record,record['invoice']),
                   lambda:confirm_test_document(tmp_path,record),lambda:reset_source_reviews(tmp_path,[record])):
        with pytest.raises(ValueError,match='changed'):action()


def test_continuation_and_cover_pages_are_not_blindly_split(tmp_path):
    folder=setup(tmp_path,True);source=next(folder.glob('*.pdf'))
    page=PdfReader(source).pages[0]
    for name,blank in [('continuation.pdf',False),('cover.pdf',True)]:
        writer=PdfWriter();writer.add_page(page)
        if blank:writer.add_blank_page(width=595,height=842)
        else:writer.add_page(page)
        path=folder/name
        with path.open('wb') as stream:writer.write(stream)
        records=expand_source(tmp_path,path,folder.name)
        assert len(records)==1 and records[0]['path']==str(path)
        if not blank:
            invoice=parse_text(text_from_pdf(path))
            assert any('Multiple invoice sections' in warning for warning in invoice['extraction_warnings'])


def test_generated_page_tampering_blocks_bundle(tmp_path):
    setup(tmp_path,True);record=inspect_sources(tmp_path)[0]
    Path(record['path']).write_bytes(Path(record['path']).read_bytes()+b'\nchanged')
    records=inspect_sources(tmp_path)
    assert len(records)==1 and 'retained source proof' in '; '.join(records[0]['errors'])


def test_same_fictional_gstin_different_suppliers_keep_history(tmp_path):
    setup(tmp_path);sales=process_sources(tmp_path)
    for record in sales:choose_unit(tmp_path,record,'Nos')
    sales=process_sources(tmp_path)
    company=Path(sales[0]['company_path']);config=(company/'client.json').read_bytes()
    setup(tmp_path,True);medical=inspect_sources(tmp_path,client_names=['medical']);confirm_test_document(tmp_path,medical[0])
    medical=process_sources(tmp_path,client_names=['medical'])
    assert all(not r['errors'] for r in medical[5:])
    assert Path(medical[5]['company_path'])!=company
    assert (company/'client.json').read_bytes()==config
    assert all(not r['errors'] for r in process_sources(tmp_path,client_names=['sales']))
    assert len(vouchers(process_sources(tmp_path,client_names=['sales'])))==15

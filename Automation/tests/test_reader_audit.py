"""Broader source roles, text fallbacks, and unresolved-data workflows."""
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from reportlab.pdfgen import canvas
from Common_Rules.desktop import inspect_sources, process_sources, save_review
from Common_Rules.extraction import parse_text, choose_embedded_text, text_from_pdf
from Common_Rules.party_evidence import read_party_roles
from Common_Rules.unit_choices import save_unit_choices, missing_units
from Common_Rules.workflow_status import invoice_status, scan_summary
from Common_Rules.source_documents import confirm_test_document
from test_flexible_extraction import alternate_text

FIXTURES=Path(__file__).parent/'fixtures'


def make_pdf(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    out=canvas.Canvas(str(path));out.setFont('Courier',6)
    for i,line in enumerate(text.splitlines()):out.drawString(20,800-i*15,line)
    out.save()


@pytest.mark.parametrize('heading',['VENDOR INFORMATION','SUPPLIER DETAILS','BILL FROM','ISSUED BY','SELLER / SUPPLIER','EXPORTER (SELLER)'])
def test_future_role_variants_generate_without_a_supplier_name_dictionary(tmp_path,heading):
    text=alternate_text().replace('SUPPLIER\n',heading+'\n').replace('NEW-001','SI-0029')
    make_pdf(tmp_path/'Client'/'invoice.pdf',text)
    record=process_sources(tmp_path,demo=False)[0]
    assert record['errors']==[]
    assert record['invoice']['seller_name']=='Example Seller'
    assert record['invoice']['buyer_name']=='Example Buyer'
    assert record['invoice']['number']=='SI-0029'
    assert record['batch_voucher_count']==1
    assert invoice_status(record).startswith('Sales XML prepared')


def test_ordered_text_fallback_recovers_fields_without_healing_spelling():
    plain=alternate_text().replace('SUPPLIER\n','VENDOR INFORMATION\n')
    damaged=plain.replace('VENDOR INFORMATION','V EN DO R  IN FOR MA TION')
    assert not parse_text(damaged).get('seller_name')
    assert choose_embedded_text(plain,damaged)==plain
    assert choose_embedded_text(plain,plain)==plain


def test_two_party_columns_remain_separate_with_unfamiliar_headings():
    warnings=[]
    roles,_=read_party_roles('''VENDOR DETAILS                 CUSTOMER INFORMATION
Example Seller                 Example Buyer
GSTIN: 27ABCDE1234F1Z0          GSTIN: 29PQRSX5678L1ZW
State: Maharashtra             State: Karnataka
Invoice Reference: OTHER-1
''',warnings)
    assert roles['seller_name']=='Example Seller' and roles['buyer_name']=='Example Buyer'
    assert roles['seller_gstin']=='27ABCDE1234F1Z0' and roles['buyer_gstin']=='29PQRSX5678L1ZW'
    assert not warnings


def test_supplier_and_metadata_columns_do_not_use_invoice_number_as_party_name():
    warnings=[]
    roles,_=read_party_roles('''SUPPLIER INFORMATION           INVOICE DETAILS
Seller With New Layout         Invoice No: SI-0029
GSTIN: 27ABCDE1234F1Z0          Date: 12/10/2026
BILL TO                        SUPPLY DETAILS
A Different Buyer              Place of Supply: 27
GSTIN: Unregistered            Currency: INR
''',warnings)
    assert roles['seller_name']=='Seller With New Layout'
    assert roles['buyer_name']=='A Different Buyer'
    assert not warnings


def test_contradictory_party_names_and_unknown_labels_never_guess():
    warnings=[]
    roles,_=read_party_roles('SUPPLIER\nFirst Seller\nSUPPLIER\nSecond Seller',warnings)
    assert roles['seller_name'] is None and warnings
    raw=parse_text('VENDOR\nLegal Entity: Seller\nBILLING PARTY\nLegal Entity: Buyer\nDELIVERY\nInvoice Value: 100')
    assert not raw.get('seller_name')


def test_generic_fictional_role_invoice_uses_demo_adapter_without_old_template_requirement(tmp_path):
    text=alternate_text().replace('SUPPLIER\n','VENDOR INFORMATION\n')+'\nSYNTHETIC TEST DATA - NOT A VALID TAX DOCUMENT OR GST REGISTRATION'
    make_pdf(tmp_path/'Client'/'invoice.pdf',text)
    record=process_sources(tmp_path)[0]
    assert record['invoice']['source_layout']=='flexible_roles_v1'
    assert not record['errors'] and record['batch_voucher_count']==1


def install_units(root):
    folder=root/'Client';folder.mkdir()
    for path in (FIXTURES/'client15').glob('Sales_Invoice*.pdf'):shutil.copy2(path,folder/path.name)
    return process_sources(root)


def test_single_sheet_unit_choices_resolve_all_fifteen_keep_individual_choices(tmp_path):
    records=install_units(tmp_path)
    assert len(records)==15 and all(invoice_status(r)=='Choose quantity unit' for r in records)
    assert '0 XML prepared' in scan_summary(records)
    assert len(missing_units(records))==15
    choices=[(r,0,'KG' if i in (0,13,14) else 'Nos') for i,r in enumerate(records)]
    assert save_unit_choices(tmp_path,choices)==15
    accepted=process_sources(tmp_path)
    assert all(not r['errors'] for r in accepted)
    assert [r['invoice']['items'][0]['unit'] for r in accepted]==[choice[2] for choice in choices]
    folder=Path(accepted[0]['output_path'])
    assert len(ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER'))==15
    assert '15 XML prepared' in scan_summary(accepted)
    assert not missing_units(accepted)


def test_unit_choices_do_not_approve_unrelated_tax_or_ocr_warnings(tmp_path):
    folder=tmp_path/'Client';folder.mkdir()
    shutil.copy2(FIXTURES/'client15/Sales_Invoice_11_INTRA.pdf',folder/'invoice.pdf')
    record=inspect_sources(tmp_path)[0]
    record['invoice']=deepcopy(record['invoice'])
    record['invoice']['extraction_warnings']=['OCR-derived fields must be checked against the PDF in Review']
    record['invoice']['source_ocr']=True
    record['source_invoice']=deepcopy(record['invoice'])
    save_unit_choices(tmp_path,[(record,0,'Nos')])
    current=process_sources(tmp_path)[0]
    assert current['invoice']['items'][0]['unit']=='Nos'
    assert current['errors'] and invoice_status(current)=='Verify scanned invoice'
    assert not current.get('output_path')


def test_blank_and_conflicting_unit_choices_do_not_silently_approve(tmp_path):
    records=install_units(tmp_path)
    assert save_unit_choices(tmp_path,[(records[0],0,'')])==0
    with pytest.raises(ValueError,match='same item unit'):
        save_unit_choices(tmp_path,[(records[0],0,'Nos'),(records[0],0,'KG')])
    assert 'unit' not in inspect_sources(tmp_path)[0]['invoice']['items'][0]


def test_pending_test_confirmation_and_missing_units_have_separate_actions(tmp_path):
    folder=tmp_path/'Client';folder.mkdir();shutil.copy2(FIXTURES/'client15/GSTR1_Test_Invoices.pdf',folder/'bundle.pdf')
    records=process_sources(tmp_path)
    assert len(records)==20 and all(invoice_status(r)=='Confirm test PDF' for r in records)
    confirm_test_document(tmp_path,records[0]);records=process_sources(tmp_path)
    assert all(invoice_status(r)=='Choose quantity unit' for r in records[:5])
    assert all(not r['errors'] for r in records[5:])
    assert '15 XML prepared' in scan_summary(records)
    save_unit_choices(tmp_path,[(r,0,'Nos') for r in records[:5]])
    assert all(not r['errors'] for r in process_sources(tmp_path))


@pytest.mark.parametrize('family',['client1','client7','client8','client11','client12','client15'])
def test_all_available_fixture_families_keep_sellers_without_manual_name_entry(family):
    for path in sorted((FIXTURES/family).glob('*.pdf')):
        # Bundles are tested through page expansion elsewhere.
        if path.name=='GSTR1_Test_Invoices.pdf':continue
        invoice=parse_text(text_from_pdf(path))
        assert invoice.get('seller_name'),path.name
        assert invoice.get('seller_gstin'),path.name
        assert invoice.get('buyer_name'),path.name


def test_unlabelled_seller_banner_needs_one_printed_business_and_header_gstin(tmp_path):
    text=alternate_text().replace('SUPPLIER\nExample Seller','TAX INVOICE\nNova Industrial Traders')
    make_pdf(tmp_path/'Client'/'invoice.pdf',text)
    record=process_sources(tmp_path,demo=False)[0]
    assert not record['errors'] and record['invoice']['seller_name']=='Nova Industrial Traders'
    assert record['invoice']['buyer_name']=='Example Buyer'
    conflicting=text.replace('Nova Industrial Traders','Nova Industrial Traders\nOther Trading Limited')
    assert not parse_text(conflicting).get('seller_name')


def test_conflicting_signatory_cannot_approve_a_masthead():
    text=alternate_text().replace('SUPPLIER\nExample Seller','TAX INVOICE\nNova Industrial Traders')+'\nFor Another Company'
    invoice=parse_text(text)
    assert not invoice.get('seller_name')
    assert any('signatory conflict' in warning for warning in invoice['extraction_warnings'])


def test_old_blank_name_review_recovers_name_preserves_explicit_edits(tmp_path):
    from Common_Rules.engine import write_json
    folder=tmp_path/'Client';folder.mkdir();shutil.copy2(FIXTURES/'client15/Sales_Invoice_11_INTRA.pdf',folder/'one.pdf')
    record=inspect_sources(tmp_path)[0]
    old=deepcopy(record['invoice']);old['seller_name']='';old['buyer_name']='Manually checked buyer';old['items'][0]['unit']='KG'
    write_json(tmp_path/'.invoice_app/reviews'/(record['digest']+'.json'),{'source_sha256':record['digest'],'approved':True,'invoice':old})
    current=process_sources(tmp_path)[0]
    assert current['invoice']['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED'
    assert current['invoice']['buyer_name']=='Manually checked buyer'
    assert current['invoice']['items'][0]['unit']=='KG'
    assert not current['errors']


def test_real_unit_capitalization_does_not_require_a_unit_choice(tmp_path):
    text=alternate_text().replace('2 | Nos | 1000','2 | kg | 1000')
    make_pdf(tmp_path/'Client'/'invoice.pdf',text)
    record=process_sources(tmp_path,demo=False)[0]
    assert not record['errors']
    assert record['invoice']['items'][0]['unit']=='KG'
    assert record['invoice']['items'][0]['printed_unit']=='kg'
    assert not missing_units([record])


def test_unmarked_real_document_in_dummy_mode_has_a_mode_action(tmp_path):
    make_pdf(tmp_path/'Client'/'invoice.pdf',alternate_text())
    record=process_sources(tmp_path)[0]
    assert invoice_status(record)=='Choose invoice mode'
    assert record['invoice']['seller_name']=='Example Seller'
    assert not record.get('output_path')


def test_six_original_uploaded_demo_pdfs_still_generate(tmp_path):
    folder=tmp_path/'Client';folder.mkdir()
    for path in (FIXTURES/'client1').glob('*.pdf'):shutil.copy2(path,folder/path.name)
    records=process_sources(tmp_path)
    assert len(records)==6 and all(not r['errors'] for r in records)
    assert all(r['invoice']['seller_name']=='DEMO SUPPLIES PRIVATE LIMITED' for r in records)
    assert {r['batch_voucher_count'] for r in records}=={6}


def test_review_cannot_remove_an_explicit_source_fictional_marker(tmp_path):
    folder=tmp_path/'Client';folder.mkdir();shutil.copy2(FIXTURES/'client15/Sales_Invoice_11_INTRA.pdf',folder/'one.pdf')
    record=inspect_sources(tmp_path)[0];edited=deepcopy(record['invoice'])
    edited['dummy_document']=False;edited['items'][0]['unit']='Nos'
    save_review(tmp_path,record,edited)
    current=process_sources(tmp_path,demo=False)[0]
    assert 'fictional' in '; '.join(current['errors'])
    assert not current.get('output_path')

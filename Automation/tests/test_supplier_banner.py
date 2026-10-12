"""Supplier headers survive harmless footer text and legal suffix formatting."""
from Common_Rules.extraction import parse_text
from test_flexible_extraction import alternate_text
from Common_Rules.supplier_identity import restore_known_supplier
from Common_Rules.engine import write_json


def text():return alternate_text().replace('SUPPLIER\nExample Seller','TAX INVOICE\nNova Trading Private Limited')


def test_authorized_signatory_delimiters_and_pvt_suffix_do_not_conflict():
 for footer in ['For Nova Trading Private Limited | Authorized Signatory (sample)',
                'For Nova Trading Pvt. Ltd. - Authorised Signatory',
                'For Nova Trading Private Limited\nFor testing only']:
  inv=parse_text(text()+'\n'+footer)
  assert inv['seller_name']=='Nova Trading Private Limited'
  assert not inv['extraction_warnings']


def test_true_conflict_keeps_printed_candidate_without_approving_identity():
 inv=parse_text(text()+'\nFor Other Trading Limited')
 assert not inv.get('seller_name')
 assert inv['seller_name_candidate']=='Nova Trading Private Limited'
 assert any('signatory conflict' in e for e in inv['extraction_warnings'])


def test_name_can_be_read_even_when_gstin_is_missing():
 inv=parse_text(text().replace('GSTIN: 27ABCDE1234F1Z0','GSTIN: Not available'))
 assert inv['seller_name']=='Nova Trading Private Limited'
 assert not inv.get('seller_gstin')


def test_verified_profile_is_reused_by_gstin_without_guessing_a_buyer(tmp_path):
 company=tmp_path/'.invoice_app/companies/Supplier'
 write_json(company/'client.json',{'demo_only':False,'source_seller_gstin':'27ABCDE1234F1Z0','source_seller_name':'Nova Trading Private Limited'})
 record={'digest':'new','invoice':{'seller_gstin':'27ABCDE1234F1Z0','buyer_name':'Buyer Trading Limited'}}
 restore_known_supplier(tmp_path,record,False)
 assert record['invoice']['seller_name']=='Nova Trading Private Limited'
 another={'digest':'other','invoice':{'seller_gstin':'29ABCDE1234F1Z0','buyer_name':'Buyer Trading Limited'}}
 restore_known_supplier(tmp_path,another,False);assert not another['invoice'].get('seller_name')
 conflicting={'digest':'conflict','invoice':{'seller_gstin':'27ABCDE1234F1Z0','extraction_warnings':['Seller masthead and signatory conflict']}}
 restore_known_supplier(tmp_path,conflicting,False);assert not conflicting['invoice'].get('seller_name')


def test_equal_unregistered_labels_do_not_raise_a_false_gstin_conflict():
 from Common_Rules.extraction import unique_field,party_value
 warnings=[]
 raw=unique_field('Buyer GSTIN: N/A - Export\nBuyer GSTIN: Unregistered - Export',('buyer gstin',),'buyer_gstin',warnings)
 assert not warnings and party_value('buyer_gstin',raw)==''
 warnings=[]
 assert unique_field('Buyer GSTIN: 27ABCDE1234F1Z0\nBuyer GSTIN: 29ABCDE1234F1Z0',('buyer gstin',),'buyer_gstin',warnings) is None
 assert warnings


def test_alternative_item_headers_still_extract_quantities_and_units():
 t=alternate_text().replace('Description of Goods','Product / Description').replace('HSN |','HSN / SAC |').replace('UOM |','Unit of measurement |').replace('Taxable Amount','Net value').replace('Unit Rate','Price (INR)')
 inv=parse_text(t)
 assert len(inv['items'])==1 and inv['items'][0]['quantity']=='2' and inv['items'][0]['unit']=='Nos'

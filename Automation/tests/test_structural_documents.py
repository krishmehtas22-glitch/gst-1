"""Unfamiliar document layout compared against independent embedded-text facts."""
from pathlib import Path
from decimal import Decimal
import shutil,re
import xml.etree.ElementTree as ET
from pypdf import PdfReader
from Common_Rules.desktop import process_sources
from Common_Rules.extraction import parse_text,text_from_pdf
from Common_Rules.accounting import money

FIXTURES=Path(__file__).parent/'fixtures/client22'


def printed(path):
 lines=[s.strip() for s in PdfReader(path).pages[0].extract_text().splitlines() if s.strip()]
 number=next(s.removeprefix('Invoice ') for s in lines if s.startswith('Invoice DM/'))
 buyer=lines[lines.index('INVOICE DETAILS')+1]
 start=lines.index('AMOUNT INR')+1;end=lines.index('Taxable / exempt value')
 cells=lines[start:end];assert len(cells)%5==0
 items=[dict(zip(('name','hsn','quantity','rate','value'),cells[i:i+5])) for i in range(0,len(cells),5)]
 amounts={key:lines[lines.index(label)+1] for key,label in [('taxable','Taxable / exempt value'),('cgst','CGST'),('sgst','SGST'),('igst','IGST'),('total','GRAND TOTAL')]}
 return number,buyer,items,amounts


def test_twenty_new_pdfs_recover_all_printed_fields_and_balanced_xml(tmp_path):
 shutil.copytree(FIXTURES,tmp_path/'New20');rows=process_sources(tmp_path,summary_accounting=True)
 assert len(rows)==20 and all(not r['errors'] for r in rows),[r['errors'] for r in rows]
 assert sum(len(r['invoice']['items']) for r in rows)==39
 assert all(any(i.get('unit_auto') for i in r['invoice']['items']) for r in rows)
 assert sum(r['invoice'].get('tax_accounting_basis')=='invoice_summary' for r in rows)==15
 by_number={}
 for record in rows:
  inv=record['invoice'];number,buyer,items,amounts=printed(Path(record['path']))
  assert inv['number']==number and inv['buyer_name']==buyer
  assert inv['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED'
  assert inv['seller_gstin']=='27ABCDE1234F1Z5'
  assert len(items)==len(inv['items'])
  for source,extracted in zip(items,inv['items']):
   assert extracted['name']==source['name'] and extracted['hsn']==source['hsn']
   for key in ('quantity','rate','value'):assert money(extracted[key])==money(source[key])
  for key in amounts:assert money(inv[key])==money(amounts[key])
  by_number[number]=(inv,amounts)
 out=Path(rows[0]['output_path'])/'Sales_Vouchers.xml';vs=ET.parse(out).findall('.//VOUCHER')
 assert len(vs)==20
 for voucher in vs:
  inv,amounts=by_number[voucher.findtext('VOUCHERNUMBER')]
  entries=voucher.findall('ALLLEDGERENTRIES.LIST')+voucher.findall('LEDGERENTRIES.LIST')
  assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')==inv['buyer_name'])==-money(amounts['total'])
  for tax in ('cgst','sgst','igst'):
   assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')=='Output '+tax.upper())==money(amounts[tax])
  balance=sum(money(e.findtext('AMOUNT')) for e in entries)+sum(money(e.findtext('AMOUNT')) for e in voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST'))
  assert balance==0
  if inv.get('tax_accounting_basis')=='invoice_summary':
   assert not voucher.findall('ALLINVENTORYENTRIES.LIST')
   assert voucher.findtext('ISINVOICE')=='No' and 'item GST rates are not printed' in voucher.findtext('NARRATION')
   assert not any('igst_rate' in item for item in inv['items'])
 guids=[v.findtext('GUID') for v in vs]
 assert all(not r['errors'] for r in process_sources(tmp_path,summary_accounting=True))
 assert [v.findtext('GUID') for v in ET.parse(out).findall('.//VOUCHER')]==guids


def test_disabling_summary_accounting_requires_missing_item_rates(tmp_path):
 shutil.copytree(FIXTURES,tmp_path/'New20');rows=process_sources(tmp_path,summary_accounting=False)
 assert sum(not r['errors'] for r in rows)==5
 assert sum(any('Item GST rates are not printed' in e for e in r['errors']) for r in rows)==15


def test_gstin_suffix_metadata_is_not_part_of_the_identifier():
 inv=parse_text(text_from_pdf(FIXTURES/'Sales_Invoice_106_INTRA.pdf'))
 assert inv['seller_gstin']=='27ABCDE1234F1Z5'
 assert not inv['extraction_warnings']


def test_summary_accounting_cannot_hide_wrong_tax_split_or_item_extension(tmp_path):
 from test_generic_treatments import pdf
 folder=tmp_path/'Bad';folder.mkdir()
 source=text_from_pdf(FIXTURES/'Sales_Invoice_106_INTRA.pdf')
 bad_split=re.sub(r'(SGST\s+)INR 742\.50',r'\g<1>INR 0.00',source)
 bad_split=re.sub(r'(IGST\s+)INR 0\.00',r'\g<1>INR 742.50',bad_split)
 pdf(folder/'split.pdf',bad_split)
 bad_item=re.sub(r'(940320\s+)5(\s+1,650)',r'\g<1>4\g<2>',source)
 pdf(folder/'item.pdf',bad_item)
 rows=process_sources(tmp_path,summary_accounting=True)
 assert all(r['errors'] for r in rows)
 assert not any(r.get('batch_voucher_count') for r in rows)
 assert any('intra-state' in e for r in rows for e in r['errors'])
 assert any('quantity × rate' in e for r in rows for e in r['errors'])


def test_reviewed_item_rates_enable_inventory_without_accounting_fallback(tmp_path):
 from copy import deepcopy
 from Common_Rules.desktop import save_review
 folder=tmp_path/'Reviewed';folder.mkdir()
 shutil.copy2(FIXTURES/'Sales_Invoice_106_INTRA.pdf',folder/'invoice.pdf')
 record=process_sources(tmp_path)[0]
 assert any('Item GST rates are not printed' in e for e in record['errors'])
 checked=deepcopy(record['invoice'])
 checked['items'][0].update(cgst_rate='9',sgst_rate='9',igst_rate='0',unit='PCS')
 save_review(tmp_path,record,checked)
 final=process_sources(tmp_path)[0];assert not final['errors']
 voucher=ET.parse(Path(final['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
 assert voucher.findtext('ISINVOICE')=='Yes'
 assert voucher.find('ALLINVENTORYENTRIES.LIST') is not None
 assert not final['invoice'].get('tax_accounting_basis')

"""Role columns, per-item GST continuation lines, and explicit fictional notices."""
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from Common_Rules.desktop import process_sources
from Common_Rules.engine import write_json
from Common_Rules.extraction import parse_text,text_from_pdf
from test_reader_audit import make_pdf

FIXTURES=Path(__file__).parent/'fixtures/client17'


def setup(root):
 folder=root/'Client';folder.mkdir()
 for path in FIXTURES.glob('*.pdf'):shutil.copy2(path,folder/path.name)


def test_all_eight_new_pdfs_generate_without_confirmation_or_manual_extraction(tmp_path):
 setup(tmp_path);rows=process_sources(tmp_path)
 assert len(rows)==8 and all(not r['errors'] for r in rows)
 assert [len(r['invoice']['items']) for r in rows]==[2,3,2,3,2,3,2,3]
 assert all(r['invoice']['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED' for r in rows)
 assert all(r['invoice']['dummy_document'] for r in rows)
 assert all(r['invoice']['currency']=='INR' for r in rows)
 assert all(not item.get('unit_auto') for r in rows for item in r['invoice']['items'])
 assert all(r['invoice']['items'][0]['cgst_rate']=='9' for r in rows[:1])
 assert rows[-1]['invoice']['items'][0]['igst_rate']=='12'
 path=Path(rows[0]['output_path'])/'Sales_Vouchers.xml'
 vs=ET.parse(path).findall('.//VOUCHER');assert len(vs)==8
 guids=[v.findtext('GUID') for v in vs]
 second=process_sources(tmp_path)
 assert all(not r['errors'] for r in second)
 assert [v.findtext('GUID') for v in ET.parse(path).findall('.//VOUCHER')]==guids
 assert all('fictional' in '; '.join(r['errors']) for r in process_sources(tmp_path,demo=False))


def test_unbaselined_old_empty_review_recovers_rows_and_normalizes_intra(tmp_path):
 setup(tmp_path);rows=process_sources(tmp_path);r=rows[0]
 old=deepcopy(r['invoice']);old.update(items=[],classification='intra',currency='INR (Indian Rupees)    Reverse charge: No')
 old.pop('supply');old.pop('source_layout');old.pop('seller_state',None);old.pop('igst')
 write_json(tmp_path/'.invoice_app/reviews'/(r['digest']+'.json'),{'approved':True,'source_sha256':r['digest'],'invoice':old})
 current=process_sources(tmp_path)[0]
 assert not current['errors']
 assert len(current['invoice']['items'])==2
 assert current['invoice']['supply']=='INTRA' and current['invoice']['classification']=='taxable'


def test_marker_needs_both_testing_and_fictional_identity_notice(tmp_path):
 text=text_from_pdf(FIXTURES/'Sales_Invoice_46_INTRA.pdf')
 text=text.replace('Not a valid tax invoice. All GSTINs and buyer identities are fictional.','')
 assert not parse_text(text).get('dummy_document')
 make_pdf(tmp_path/'Client'/'unmarked.pdf',text)
 row=process_sources(tmp_path)[0]
 assert row['errors'] and not row.get('batch_voucher_count')


def test_each_item_requires_its_own_printed_rate_and_conflicting_rates_block(tmp_path):
 text=text_from_pdf(FIXTURES/'Sales_Invoice_46_INTRA.pdf')
 first=text.replace('GST rate: 18%','GST rate: 18%\nGST rate: 12%',1)
 assert any('Conflicting GST' in warning for warning in parse_text(first)['extraction_warnings'])
 second=text.replace('GST rate: 18%','',1)
 make_pdf(tmp_path/'Client'/'missing-rate.pdf',second)
 row=process_sources(tmp_path)[0]
 assert row['errors'] and not row.get('batch_voucher_count')


def test_generic_table_aliases_and_reordered_columns_keep_tax_attachment():
 text=text_from_pdf(FIXTURES/'Sales_Invoice_46_INTRA.pdf')
 lines=[]
 from Common_Rules.extraction import cells
 for line in text.splitlines():
  row=cells(line)
  if len(row)==6 and (row[0]=='ITEM / DESCRIPTION' or row[1].isdigit()):
   row=[row[i] for i in (1,0,3,2,5,4)]
   if row[0]=='HSN':row=['HSN code','Description of Goods','Units','Quantity','Net amount','Unit price']
   line=' | '.join(row)
  lines.append(line)
 inv=parse_text('\n'.join(lines))
 assert not inv['extraction_warnings'] and len(inv['items'])==2
 assert inv['items'][0]['unit']=='PCS' and inv['items'][0]['cgst_rate']=='9'

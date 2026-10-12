"""XML coverage for generic domestic, LUT, IGST export and exempt tables."""
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import pytest
from reportlab.pdfgen import canvas
from Common_Rules.extraction import text_from_pdf,parse_text
from Common_Rules.desktop import process_sources

FIXTURES=Path(__file__).parent/'fixtures/client17'


def variant(treatment,number):
 text=text_from_pdf(FIXTURES/'Sales_Invoice_46_INTRA.pdf')
 text=text.replace('SI-0046',number).replace('NOVA ENTERPRISES 46','Future Buyer '+number)
 text=re.sub(r'CGST\s+INR 923\.40','',text)
 text=re.sub(r'SGST\s+INR 923\.40','',text)
 text=text.replace('CGST + SGST applied according to sample line-item rates.','')
 if treatment.startswith('export'):
  text=text.replace('Supply type: INTRA','Supply type: EXPORT')
  text=text.replace('Place of supply: Pune, Maharashtra','Place of supply: Outside India')
  text=text.replace('GSTIN: 27PQRSX1046L1Z1','GSTIN: Not applicable - overseas buyer')
  text=text.replace('Buyer state: Maharashtra','Buyer state: Outside India')
  text+='\nBuyer country: UAE\n'
  if treatment=='export_lut':text+='\nExport under LUT without payment of IGST.\n'
  else:text+='\nExport with payment of IGST.\nIGST: INR 1,846.80\n'
 else:
  text=text.replace('Supply type: INTRA','Supply type: '+('EXEMPT' if treatment=='exempt' else 'NIL-RATED'))
  text=text.replace('GST rate: 18%','GST rate: 0%')
  if treatment=='exempt':text+='\nExempt supply: no GST charged.\n'
  text=text.replace('Steel Storage Rack',treatment+' sample rack').replace('Plastic File Organizer',treatment+' sample organizer')
 if treatment!='export_igst':text=text.replace('INR 12,106.80','INR 10,260.00')
 return text


def pdf(path,text):
 out=canvas.Canvas(str(path),pagesize=(2200,1600));out.setFont('Courier',6)
 for i,line in enumerate(line for line in text.splitlines() if line.strip()):out.drawString(20,1500-i*18,line)
 out.save()


@pytest.mark.parametrize('treatment',['export_lut','export_igst','exempt','nil_rated'])
def test_printed_treatment_has_correct_payable_component_rates(treatment):
 inv=parse_text(variant(treatment,'NEXT-1'))
 assert not inv['extraction_warnings'],inv['extraction_warnings']
 assert inv['classification']==treatment
 assert len(inv['items'])==2
 for item in inv['items']:
  assert item['cgst_rate']==item['sgst_rate']=='0'
  assert item['igst_rate']==('18' if treatment=='export_igst' else '0')
 if treatment.startswith('export'):
  assert inv['place_of_supply']=='Outside India' and inv['buyer_country']=='UAE'
  assert inv['buyer_gstin']=='' and inv['buyer_registration']=='Unregistered'


def test_sixteen_invoice_batch_has_sixteen_vouchers_and_balanced_gst_entries(tmp_path):
 folder=tmp_path/'Client';folder.mkdir()
 for path in FIXTURES.glob('*.pdf'):shutil.copy2(path,folder/path.name)
 for i,treatment in enumerate(['export_lut','export_igst','exempt','nil_rated']*2):pdf(folder/f'future-{i}.pdf',variant(treatment,f'FUTURE-{i}'))
 records=process_sources(tmp_path)
 assert len(records)==16 and all(not r['errors'] for r in records),[r['errors'] for r in records]
 out=Path(records[0]['output_path'])/'Sales_Vouchers.xml'
 vouchers=ET.parse(out).findall('.//VOUCHER');assert len(vouchers)==16
 for voucher in vouchers:
  values=[entry.findtext('AMOUNT') for entry in voucher.findall('ALLLEDGERENTRIES.LIST')+voucher.findall('LEDGERENTRIES.LIST')]
  values += [entry.findtext('AMOUNT') for entry in voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST')]
  from decimal import Decimal
  assert sum(Decimal(value) for value in values)==0
 before=[v.findtext('GUID') for v in vouchers]
 assert all(not r['errors'] for r in process_sources(tmp_path))
 assert [v.findtext('GUID') for v in ET.parse(out).findall('.//VOUCHER')]==before


def test_conflicting_export_declarations_or_amounts_do_not_become_wrong_vouchers(tmp_path):
 folder=tmp_path/'Client';folder.mkdir()
 pdf(folder/'conflict.pdf',variant('export_lut','BAD-1')+'\nExport with payment of IGST.\n')
 pdf(folder/'wrong-amount.pdf',variant('export_igst','BAD-2').replace('INR 1,846.80','INR 1,845.80'))
 records=process_sources(tmp_path)
 assert all(r['errors'] for r in records)
 assert not any(r.get('batch_voucher_count') for r in records)


def test_exempt_remark_does_not_create_a_second_supply_field():
 inv=parse_text(variant('exempt','EXEMPT-1'))
 assert inv['supply']=='EXEMPT'
 assert not any('Ambiguous supply' in error for error in inv['extraction_warnings'])

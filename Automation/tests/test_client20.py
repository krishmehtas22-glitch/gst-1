"""Regression coverage for all twenty uploaded PDFs and serialized buyer masters."""
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from Common_Rules.desktop import process_sources
from Common_Rules.accounting import money
from Common_Rules.tally_xml import registration_type

FIXTURES=Path(__file__).parent/'fixtures/client20'


def test_all_twenty_sources_have_balanced_vouchers_and_matching_buyer_masters(tmp_path):
 folder=tmp_path/'CLIENT 20';shutil.copytree(FIXTURES,folder)
 original={p.name:p.read_bytes() for p in folder.glob('*.pdf')}
 records=process_sources(tmp_path)
 assert len(records)==20 and all(not r['errors'] for r in records),[r['errors'] for r in records]
 assert [r['invoice']['number'] for r in records]==[f'SI-{n:04d}' for n in range(66,86)]
 out=Path(records[0]['output_path'])
 vouchers=ET.parse(out/'Sales_Vouchers.xml').findall('.//VOUCHER')
 masters=ET.parse(out/'Masters.xml').findall('.//LEDGER')
 debtors={node.get('NAME'):node for node in masters if node.findtext('PARENT')=='Sundry Debtors'}
 assert len(vouchers)==len(debtors)==20
 recovery=ET.parse(out/'Required_Masters.xml')
 assert {n.get('NAME') for n in recovery.findall('.//LEDGER') if n.findtext('PARENT')=='Sundry Debtors'}==set(debtors)
 by_number={r['invoice']['number']:r['invoice'] for r in records}
 for voucher in vouchers:
  inv=by_number[voucher.findtext('VOUCHERNUMBER')]
  buyer=voucher.findtext('PARTYLEDGERNAME')
  assert buyer==inv['buyer_name'] and buyer in debtors
  entries=voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST')
  party=[entry for entry in entries if entry.findtext('LEDGERNAME')==buyer]
  assert len(party)==1 and money(party[0].findtext('AMOUNT'))==-money(inv['total'])
  credits=sum(money(entry.findtext('AMOUNT')) for entry in entries)
  credits+=sum(money(entry.findtext('AMOUNT')) for entry in voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST'))
  assert credits==0
  for field,ledger in [('cgst','Output CGST'),('sgst','Output SGST'),('igst','Output IGST')]:
   assert sum(money(entry.findtext('AMOUNT')) for entry in entries if entry.findtext('LEDGERNAME')==ledger)==money(inv[field])
  master=debtors[buyer]
  expected='Regular' if inv.get('buyer_gstin') else 'Unregistered/Consumer'
  assert master.findtext('GSTREGISTRATIONTYPE')==expected
  assert voucher.findtext('GSTREGISTRATIONTYPE')==expected
 assert debtors['ALPHA TRADERS 79'].findtext('COUNTRYNAME')=='Singapore'
 assert debtors['SAPPHIRE TRADERS 81'].findtext('COUNTRYNAME')=='Canada'
 assert not any(v.findall('ALLINVENTORYENTRIES.LIST') for v in vouchers if by_number[v.findtext('VOUCHERNUMBER')]['supply']=='EXPORT')
 guids=[v.findtext('GUID') for v in vouchers]
 assert all(not r['errors'] for r in process_sources(tmp_path))
 assert [v.findtext('GUID') for v in ET.parse(out/'Sales_Vouchers.xml').findall('.//VOUCHER')]==guids
 assert original=={p.name:p.read_bytes() for p in folder.glob('*.pdf')}


def test_registration_mapping_only_changes_the_tally_label():
 assert registration_type('Unregistered')==registration_type('Consumer')=='Unregistered/Consumer'
 assert registration_type('Regular')=='Regular'
 assert registration_type('Composition')=='Composition'


def test_recovery_master_file_includes_previously_confirmed_dependencies(tmp_path):
 from test_tally_xml import generated
 from helpers import pdf,invoice
 from Common_Rules.engine import read_json,write_json,confirm_import,run
 c,_=generated(tmp_path);manifest=read_json(c/'imports/manifest.json')
 result={'company_id':manifest['company_id'],'generated_at':manifest['generated_at'],
         'tally_result_reference':'Synthetic receipt; no live import',
         'masters':[{'master':m,'status':'imported'} for m in manifest['masters']],
         'vouchers':[{'invoice_key':k,'status':'imported'} for k in manifest['invoice_keys']]}
 path=c/'import_results.json';write_json(path,result);confirm_import(c,path)
 pdf(c/'next.pdf',invoice('NEXT-RECOVERY'))
 report=run(tmp_path)['clients'][0];assert not report['issues']
 assert not (c/'imports/Masters.xml').exists()
 assert (c/'imports/Required_Masters.xml').exists()
 recovery=ET.parse(c/'imports/Required_Masters.xml')
 buyer=ET.parse(c/'imports/Sales_Vouchers.xml').findtext('.//PARTYLEDGERNAME')
 assert buyer in {n.get('NAME') for n in recovery.findall('.//LEDGER')}
 assert read_json(c/'imports/manifest.json')['import_order']==['Sales_Vouchers.xml']

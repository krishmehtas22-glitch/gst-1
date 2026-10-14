"""Automatic estimates stay visible, editable and separate from financial facts."""
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.unit_inference import canonical_unit, quantity_parts, suggest_unit, UnitResolver, remember_units
from Common_Rules.unit_catalog import UNITS
from Common_Rules.desktop import process_sources
from Common_Rules.unit_choices import save_unit_choices
from Common_Rules.source_documents import confirm_test_document
from Common_Rules.engine import read_json
from Common_Rules.history import History
from Common_Rules.accounting import fingerprint

FIXTURES=Path(__file__).parent/'fixtures/client15'

@pytest.mark.parametrize('name,hsn,qty,unit',[
 ('Blue pen','9608','1','Nos'),('Rice','1006','20','KG'),('Box of 12 pens','9608','2','BOX'),
 ('Paracetamol 500 mg','3004','20','Nos'),('Paracetamol tablets 500 mg','3004','20','TBS'),
 ('Cough syrup 100 ml','3004','5','BTL'),('Hand tool assortment','8206','2','SET'),
 ('Oil per litre','1515','10','LTR'),('USB mouse','8471','2','Nos'),
 ('Unspecified service','9983','0.5','Units'),('Rice 1kg','1006','5','Packs')])
def test_product_rules_do_not_read_strength_as_quantity(name,hsn,qty,unit):
 item={'name':name,'hsn':hsn,'quantity':qty};original=deepcopy(item)
 assert suggest_unit(item,{})[0]==unit
 assert item==original

@pytest.mark.parametrize('printed,unit',[('pieces','PCS'),('kg','KG'),('milligrams','MG'),('ml','ML'),('metric tonnes','MT')])
def test_printed_aliases(printed,unit):assert canonical_unit(printed)==unit

def test_quantity_suffix_and_nonstandard_mass_uqc():
 assert quantity_parts('150 mg')==('150','mg')
 assert quantity_parts('12pieces')==('12','pieces')
 assert quantity_parts('12 KVA')==('12','KVA')
 assert UNITS['MG']['uqc'].startswith('OTH')


def record(digest='abc',name='Pen',unit=None,seller='Seller'):
 inv={'seller_gstin':'27ABCDE1234F1Z0','seller_name':seller,'items':[{'name':name,'hsn':'9608','quantity':'1','rate':'100','value':'100'}]}
 if unit is not None:inv['items'][0]['unit']=unit
 return {'digest':digest,'invoice':inv}


def test_printed_units_override_keywords_and_unknown_printed_units_stay_unresolved(tmp_path):
 resolver=UnitResolver(tmp_path)
 r=record(unit='kg');resolver.apply(r)
 assert r['invoice']['items'][0]['unit']=='KG'
 assert r['invoice']['items'][0]['printed_unit']=='kg'
 assert not r['invoice']['items'][0]['unit_auto']
 r=record('other',unit='KVA');resolver.apply(r)
 assert r['invoice']['items'][0]['unit']=='KVA'
 assert not r['invoice']['items'][0].get('unit_auto')


def test_learning_is_supplier_product_and_mode_scoped_and_document_estimates_stay_stable(tmp_path):
 first=record('first');resolver=UnitResolver(tmp_path);resolver.apply(first)
 assert first['invoice']['items'][0]['unit']=='Nos'
 corrected=record('corrected');corrected['invoice']['items'][0].update(unit='BOX',unit_correction_reviewed=True)
 remember_units(tmp_path,corrected,corrected['invoice'])
 new=record('new');UnitResolver(tmp_path).apply(new)
 assert new['invoice']['items'][0]['unit']=='BOX'
 assert new['invoice']['items'][0]['unit_origin']=='learned'
 first=record('first');UnitResolver(tmp_path).apply(first)
 assert first['invoice']['items'][0]['unit']=='Nos'
 other=record('other',seller='Other seller');UnitResolver(tmp_path).apply(other)
 assert other['invoice']['items'][0]['unit']=='Nos'
 real=record('real');UnitResolver(tmp_path,demo=False).apply(real)
 assert real['invoice']['items'][0]['unit']=='Nos'
 printed=record('printed',unit='PCS');UnitResolver(tmp_path).apply(printed)
 assert printed['invoice']['items'][0]['unit']=='PCS'


def test_auto_off_preserves_manual_workflow_and_explicit_suffix(tmp_path):
 r=record();UnitResolver(tmp_path,enabled=False).apply(r)
 assert 'unit' not in r['invoice']['items'][0]
 r=record('suffix');r['invoice']['items'][0]['quantity']='150 mg'
 UnitResolver(tmp_path,enabled=False).apply(r)
 assert r['invoice']['items'][0]['unit']=='MG'
 assert r['invoice']['items'][0]['quantity']=='150'
 assert r['invoice']['items'][0]['rate']=='100'


def install(root,bundle=False):
 folder=root/'Client';folder.mkdir()
 sources=[FIXTURES/'GSTR1_Test_Invoices.pdf'] if bundle else sorted(FIXTURES.glob('Sales_Invoice*.pdf'))
 for source in sources:shutil.copy2(source,folder/source.name)
 return folder


def test_fifteen_available_invoices_generate_without_unit_prompt_and_remain_editable(tmp_path):
 folder=install(tmp_path);before={p.name:p.read_bytes() for p in folder.glob('*.pdf')}
 rows=process_sources(tmp_path)
 assert len(rows)==15 and all(not r['errors'] for r in rows)
 assert all(r['invoice']['items'][0]['unit_auto'] for r in rows)
 assert all(r['invoice']['items'][0]['unit']=='KG' for r in rows[-3:])
 output=Path(rows[0]['output_path'])
 vs=ET.parse(output/'Sales_Vouchers.xml').findall('.//VOUCHER')
 assert len(vs)==15
 guids=[v.findtext('GUID') for v in vs]
 save_unit_choices(tmp_path,[(rows[0],0,'Nos')])
 updated=process_sources(tmp_path)
 assert all(not r['errors'] for r in updated)
 assert updated[0]['invoice']['items'][0]['unit']=='Nos'
 assert not updated[0]['invoice']['items'][0]['unit_auto']
 assert [v.findtext('GUID') for v in ET.parse(output/'Sales_Vouchers.xml').findall('.//VOUCHER')]==guids
 assert before=={p.name:p.read_bytes() for p in folder.glob('*.pdf')}
 assert all(not r['errors'] for r in process_sources(tmp_path))


def test_bundle_test_confirmation_is_still_required_but_units_are_automatic(tmp_path):
 install(tmp_path,True);rows=process_sources(tmp_path)
 assert len(rows)==20 and all(r['errors'] for r in rows)
 confirm_test_document(tmp_path,rows[0]);rows=process_sources(tmp_path)
 assert all(not r['errors'] for r in rows)
 assert all(r['invoice']['items'][0]['unit_auto'] for r in rows[:5])
 assert not any(r['invoice']['items'][0].get('unit_auto') for r in rows[5:])
 assert len(ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==20


@pytest.mark.parametrize('change',['imported','amount','source','unapproved'])
def test_history_unit_changes_cannot_bypass_confirmed_or_financial_checks(tmp_path,change):
 install(tmp_path);rows=process_sources(tmp_path)
 company=Path(rows[0]['company_path'])
 config=read_json(company/'client.json')
 history=History(company/'.automation/history.sqlite3')
 key=history.statuses()[0]['invoice_key'];old=history.lookup(key)['data'];new=deepcopy(old)
 new['items'][0].update(unit='BOX',unit_correction_reviewed=True)
 if change=='imported':history.set_status(key,'imported')
 if change=='amount':new['total']='999999'
 if change=='source':new['sha256']='different'
 if change=='unapproved':new['items'][0].pop('unit_correction_reviewed')
 assert not history.correct_units(key,new)
 assert history.lookup(key)['fingerprint']==fingerprint(old)
 history.db.close()


@pytest.mark.parametrize('heading',['Qty (kg)','Quantity (pieces)'])
def test_quantity_table_heading_is_printed_unit_evidence(heading):
 from test_flexible_extraction import alternate_text
 from Common_Rules.extraction import parse_text
 text=alternate_text().replace('Qty. | UOM','%s | UOM'%heading).replace('2 | Nos | 1000','2 | | 1000')
 inv=parse_text(text);item=inv['items'][0]
 assert canonical_unit(item['unit'])==('KG' if 'kg' in heading else 'PCS')
 assert item['unit_origin']=='printed' and not item['unit_auto']


def test_conflicting_printed_quantity_and_price_units_need_review():
 from test_flexible_extraction import alternate_text
 from Common_Rules.extraction import parse_text
 text=alternate_text().replace('Qty. | UOM','Qty (kg) | UOM').replace('Unit Rate','Rate (per g)').replace('2 | Nos | 1000','2 | | 1000')
 assert any('different units' in warning for warning in parse_text(text)['extraction_warnings'])


def test_quantity_suffix_conflicting_with_printed_uom_needs_review():
 from test_flexible_extraction import alternate_text
 from Common_Rules.extraction import parse_text
 inv=parse_text(alternate_text().replace('2 | Nos | 1000','2 kg | Nos | 1000'))
 assert any('suffix conflicts' in warning for warning in inv['extraction_warnings'])

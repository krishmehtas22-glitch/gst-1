from copy import deepcopy
from Common_Rules.gemini_reader import normalize_invoice_result,infer_api_units
from Common_Rules.tally_review_export import export_all
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest


@pytest.mark.parametrize('provider',['Gemini','Groq'])
def test_ai_unit_assumption_is_visible_without_changing_numeric_fields(provider):
    inv={'items':[{'name':'Ball pen','quantity':'9','rate':'10','value':'90','unit':'pieces','unit_basis':'inferred','unit_reason':'Countable individual pens'}]}
    result=normalize_invoice_result(inv,{'invoice':{}},provider)
    item=result['items'][0]
    assert item['unit']=='PCS' and item['unit_auto']
    assert item['quantity']=='9' and item['rate']=='10' and item['value']=='90'
    assert 'Countable individual pens' in item['unit_evidence']


def test_qty_heading_is_reasoned_not_a_selling_unit():
    inv={'items':[{'name':'Ball pen','quantity':'9','unit':'Qty','value':'90','rate':'10'}]}
    infer_api_units(inv,{'invoice':{}},'Groq')
    assert inv['items'][0]['unit'] in ('Nos','PCS','Units')
    assert inv['items'][0]['unit_auto'] and inv['items'][0]['quantity']=='9'


def test_printed_box_overrides_ai_pieces_and_custom_unit_is_retained():
    record={'invoice':{'items':[{'name':'Ball pen','unit':'BOX','unit_origin':'printed'}]}}
    inv={'items':[{'name':'Ball pen','unit':'PCS','unit_basis':'inferred'}]}
    infer_api_units(inv,record,'Groq')
    assert inv['items'][0]['unit']=='BOX' and not inv['items'][0]['unit_auto']
    custom={'items':[{'name':'Fabric','quantity':'2','unit':'BALE','unit_basis':'printed'}]}
    infer_api_units(custom,{'invoice':{}},'Gemini')
    assert custom['items'][0]['unit']=='BALE'


def test_medicine_strength_is_not_inferred_sold_mass():
    inv={'items':[{'name':'Paracetamol 500 mg','quantity':'10','unit':'MG','unit_basis':'inferred'}]}
    infer_api_units(inv,{'invoice':{}},'Groq')
    assert inv['items'][0]['unit'] not in ('MG','GMS','KG')
    assert inv['items'][0]['quantity']=='10'


def test_unit_reason_is_in_xml_narration_and_report(tmp_path):
    inv={'number':'TEST-1','date':'2026-10-13','seller_name':'Seller','seller_gstin':'INVALID','buyer_name':'Buyer','taxable':'90','total':'90','cgst':'0','sgst':'0','igst':'0',
         'items':[{'name':'Pen','quantity':'9','unit':'PCS','unit_basis':'inferred','unit_reason':'Countable pens','unit_auto':True,'unit_evidence':'Groq assumption: Countable pens','rate':'10','value':'90'}]}
    record={'invoice':inv,'client':'Client','path':str(tmp_path/'test.pdf'),'digest':'a'*64,'errors':[]}
    export_all(tmp_path,[record],True)
    folder=Path(record['output_path'])
    assert 'unit PCS assumed: Groq assumption: Countable pens' in ET.parse(folder/'Sales_Vouchers.xml').findtext('.//NARRATION')
    assert 'Countable pens' in (folder/'Batch_Report.json').read_text()


def test_quantity_suffix_outranks_inferred_unit_without_scaling():
    inv={'items':[{'name':'Pen','quantity':'9 BOX','unit':'PCS','unit_basis':'inferred','rate':'10','value':'90'}]}
    infer_api_units(inv,{'invoice':{}},'Groq')
    assert inv['items'][0]['quantity']=='9' and inv['items'][0]['unit']=='BOX'
    assert inv['items'][0]['unit_basis']=='printed'
    assert inv['items'][0]['rate']=='10' and inv['items'][0]['value']=='90'

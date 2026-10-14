"""Incomplete AI metadata must not erase locally read identity or alter items."""
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules import groq_reader
from Common_Rules.gemini_batch import read_with_fallback
from Common_Rules.invoice_identity import recover_missing_identity
from Common_Rules.engine import read_json


def row(root):
    folder=root/'Client';folder.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/client23/Sales_Invoice_126_INTRA.pdf',folder/'invoice.pdf')
    return inspect_sources(root)[0]


def test_ai_omits_number_buyer_date_local_read_restores_xml_without_new_api(tmp_path,monkeypatch):
    original=row(tmp_path);local=deepcopy(original['invoice'])
    monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    answer={k:local.get(k) for k in groq_reader.FIELDS}
    answer.update(number=None,buyer_name=None,date=None,buyer_gstin=None,buyer_state=None)
    answer['items']=[{k:item.get(k) for k in groq_reader.ITEM_FIELDS} for item in local['items']]
    groq_reader.extract_selected(tmp_path,original,lambda *args:deepcopy(answer))
    cache=groq_reader.cache_path(tmp_path,original)
    raw=read_json(cache)['invoice'];assert not raw.get('number') and not raw.get('buyer_name')
    read_with_fallback(tmp_path,[original],primary='Groq',batch_reader=lambda *a,**kw:None,confirm_test=True)
    updated=process_sources(tmp_path)[0];invoice=updated['invoice']
    assert invoice['number']==local['number'] and invoice['buyer_name']==local['buyer_name']
    assert invoice['date']==local['date']
    assert invoice['seller_name']==raw['seller_name']
    assert invoice['items'][0]['quantity']==raw['items'][0]['quantity']
    # Cache raw response remains unchanged; repair is an evidence-backed overlay.
    assert read_json(cache)['invoice']==raw
    voucher=ET.parse(Path(updated['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
    assert voucher.findtext('DATE')==local['date'].replace('-','')
    assert voucher.findtext('BASICBUYERNAME')==local['buyer_name']


def test_complete_ai_identity_and_all_business_data_left_unchanged(tmp_path):
    record=row(tmp_path)
    ai={'number':'AI-NO','buyer_name':'AI Buyer','seller_name':'Keep Seller','date':'2026-10-20','total':'123.45','items':[{'name':'Keep Item','quantity':'2','unit':'LTR','rate':'10'}]}
    assert recover_missing_identity(tmp_path,record,ai,record['invoice'])==ai


def test_ambiguous_local_buyer_not_copied(tmp_path):
    record=row(tmp_path);local={**record['invoice'],'extraction_warnings':['Ambiguous buyer GSTIN values differ']}
    result=recover_missing_identity(tmp_path,record,{'number':'Keep','items':[]},local)
    assert not result.get('buyer_name')


def test_generic_units_master_explicitly_exported(tmp_path):
    from Common_Rules.tally_review_export import export_all
    record=row(tmp_path)
    for item in record['invoice']['items']:item['unit']='Units'
    export_all(tmp_path,[record],True)
    folder=Path(record['output_path'])
    units=ET.parse(folder/'Units.xml');masters=ET.parse(folder/'Masters.xml')
    unit=units.find(".//UNIT[@NAME='Units']")
    assert unit is not None and unit.findtext('ISSIMPLEUNIT')=='Yes'
    assert unit.findtext('GSTREPUOM')=='UNT-UNITS'
    assert all(stock.findtext('BASEUNITS')=='Units' for stock in masters.findall('.//STOCKITEM'))

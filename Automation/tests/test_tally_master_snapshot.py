"""Incoming Tally reads must include units without changing the working reader."""
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import pytest
from Tally_Master_Snapshot import collect_snapshot, export_request, parse_collection, save_snapshot, COLLECTIONS


COMPANY='Company & Sons <Test>'


def tally_transport(payload):
    request=ET.fromstring(payload)
    assert request.findtext('./HEADER/TALLYREQUEST')=='Export'
    assert request.findtext('./HEADER/TYPE')=='Collection'
    assert not request.findall('.//REQUESTDATA')
    kind=request.findtext('.//COLLECTION/TYPE')
    if kind=='Company':
        root=ET.Element('ENVELOPE');ET.SubElement(ET.SubElement(root,'COLLECTION'),'COMPANY',NAME=COMPANY)
        return ET.tostring(root)
    assert request.findtext('.//SVCURRENTCOMPANY')==COMPANY
    response={
        'Ledger':b'<LEDGER NAME="Customer"><PARENT>Sundry Debtors</PARENT><PARTYGSTIN>27TEST</PARTYGSTIN><ADDRESS.LIST><ADDRESS>Street One</ADDRESS><ADDRESS>Street Two</ADDRESS></ADDRESS.LIST></LEDGER>',
        'StockItem':b'<STOCKITEM NAME="Cable"><PARENT>Primary</PARENT><BASEUNITS>m</BASEUNITS></STOCKITEM>',
        'Unit':b'<UNIT NAME="m"><MAILINGNAME>Metre</MAILINGNAME><GSTREPUOM>MTR-METERS</GSTREPUOM><DECIMALPLACES>3</DECIMALPLACES></UNIT>'}[kind]
    return b'<ENVELOPE><BODY><DATA><COLLECTION>'+response+b'</COLLECTION></DATA></BODY></ENVELOPE>'


def test_all_three_reads_scoped_and_saved_without_touching_existing_data(tmp_path):
    original=tmp_path/'.invoice_app'/'unit_overrides.json';original.parent.mkdir();original.write_bytes(b'{"keep":"original"}')
    old_xml=tmp_path/'Units.xml';old_xml.write_bytes(b'<existing/>')
    calls=[];progress=[]
    def transport(payload):calls.append(payload);return tally_transport(payload)
    result=collect_snapshot(COMPANY,transport,progress.append)
    assert len(calls)==4 and len(progress)==3
    assert result['counts']=={'ledgers':1,'stock_items':1,'units':1}
    assert result['applied_to_reader'] is False and result['mode']=='review_only'
    assert result['units'][0]['fields']['GSTREPUOM']==['MTR-METERS']
    assert result['units'][0]['fields']['MAILINGNAME']==['Metre']
    assert '<ADDRESS>Street Two</ADDRESS>' in result['ledgers'][0]['xml']
    path=save_snapshot(tmp_path,result)
    assert json.loads(path.read_text())==result
    assert 'tally_master_snapshots' in path.parts
    assert original.read_bytes()==b'{"keep":"original"}' and old_xml.read_bytes()==b'<existing/>'
    second=save_snapshot(tmp_path,result);assert second!=path and path.exists()
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file())==sorted([original.relative_to(tmp_path).as_posix(),'Units.xml',path.relative_to(tmp_path).as_posix(),second.relative_to(tmp_path).as_posix()])


@pytest.mark.parametrize('category',COLLECTIONS)
def test_export_request_encodes_company_and_has_no_mutation(category):
    request=ET.fromstring(export_request(COMPANY,category))
    assert request.findtext('.//SVCURRENTCOMPANY')==COMPANY
    assert request.findtext('./HEADER/TALLYREQUEST')=='Export'
    assert request.find('.//IMPORTDATA') is None
    assert not any(n.get('Action') for n in request.iter())


def test_company_closed_aborts_before_master_queries():
    calls=[]
    def transport(payload):calls.append(payload);return b'<ENVELOPE><COLLECTION/></ENVELOPE>'
    with pytest.raises(ValueError,match='no longer open'):collect_snapshot(COMPANY,transport)
    assert len(calls)==1


@pytest.mark.parametrize('response',[b'<RESPONSE>1</RESPONSE>',b'<ENVELOPE><STATUS>0</STATUS><COLLECTION/></ENVELOPE>',b'<ENVELOPE><COLLECTION/><LINEERROR>Denied</LINEERROR></ENVELOPE>',b'<ENVELOPE><COLLECTION><UNIT/></COLLECTION></ENVELOPE>',b'broken'])
def test_invalid_or_failed_collection_is_not_an_empty_success(response):
    with pytest.raises(ValueError):parse_collection(response,'units')


def test_valid_empty_collection_and_tally_system_control_references():
    assert parse_collection(b'<ENVELOPE><COLLECTION/></ENVELOPE>','units')==[]
    rows=parse_collection(b'<ENVELOPE><UNIT>1</UNIT><COLLECTION><UNIT NAME="kg"><PARENT>&#4; Primary</PARENT><MAILINGNAME>Kilogram</MAILINGNAME></UNIT></COLLECTION></ENVELOPE>','units')
    assert len(rows)==1 and rows[0]['fields']['PARENT']==['Primary']
    wrapped='<ENVELOPE><COLLECTION><TALLYMESSAGE><UNIT NAME="L"><MAILINGNAME>Litre</MAILINGNAME></UNIT></TALLYMESSAGE></COLLECTION></ENVELOPE>'
    assert parse_collection(wrapped.encode('utf-16'),'units')[0]['name']=='L'


def test_partial_read_failure_does_not_produce_a_snapshot(tmp_path):
    def transport(payload):
        if ET.fromstring(payload).findtext('.//COLLECTION/TYPE')=='Unit':return b'<RESPONSE><LINEERROR>Could not read units</LINEERROR></RESPONSE>'
        return tally_transport(payload)
    with pytest.raises(ValueError,match='Could not read units'):collect_snapshot(COMPANY,transport)
    assert not list(tmp_path.rglob('*.json'))


def exercise_snapshot_dialog_in_existing_app(root,tmp_path,monkeypatch):
    # Tally is a Toplevel of the running app, not a second Tk interpreter.
    # Recreating Tk after tkdnd teardown is unreliable on the Windows runner.
    import Tally_Master_Dialog as dialog_module
    calls=[];saved=[]
    def transport(payload):calls.append(payload);return tally_transport(payload)
    monkeypatch.setattr(dialog_module,'loaded_companies',lambda:__import__('Common_Rules.tally_import',fromlist=['loaded_companies']).loaded_companies(transport))
    monkeypatch.setattr(dialog_module,'collect_snapshot',lambda company,progress:collect_snapshot(company,transport,progress))
    from Common_Rules.tally_master_matching import bind_snapshot,context
    def selected(snapshot,path):
        saved.append((snapshot,path));bind_snapshot(tmp_path,'Client',path)
    dialog=dialog_module.TallyMasterDialog(root,tmp_path,on_saved=selected,client='Client')
    def wait():
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            root.update();time.sleep(.02)
            if not dialog.running:return
        pytest.fail('Dialog did not finish')
    try:
        root.update();assert calls==[]
        dialog.connect();wait();assert len(calls)==1
        assert dialog.picker.cget('values')==(COMPANY,)
        dialog.company.set(COMPANY);dialog.read();wait()
        assert len(saved)==1 and len(calls)==5 and saved[0][1].is_file()
        assert context(tmp_path,{'client':'Client'})['company']==COMPANY
        assert str(dialog.use_button.cget('state'))=='normal'
        assert all(len(table.get_children())==1 for table in dialog.tables.values())
        dialog.tables['units'].selection_set('0');root.update()
        assert 'MTR-METERS' in dialog.detail.get('1.0','end')
    finally:
        dialog.after_cancel(dialog._poll_id)
        dialog.destroy()

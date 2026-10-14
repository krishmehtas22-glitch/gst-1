"""Complete client snapshots remain bounded and import without changing vouchers."""
from copy import deepcopy
import json,shutil
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.desktop import inspect_sources
from Common_Rules.tally_review_export import export_all
from Common_Rules.tally_import import client_import_groups,response_xml,voucher_count
from Common_Rules.client_xml_output import publish,LAYOUT


def rows(root):
    shutil.copytree(Path(__file__).parent/'fixtures/client23',root/'Client')
    return inspect_sources(root)[:4]


def voucher_map(document):
    return {v.findtext('GUID'):ET.canonicalize(ET.tostring(v,encoding='unicode'),strip_text=True)
            for v in document.findall('.//VOUCHER')}


def test_one_current_folder_preserves_all_vouchers_and_bounds_backups(tmp_path):
    records=rows(tmp_path)
    for row,name in zip(records,['Western Trade Supplies','WESTERN TRADE SUPPLIES','Western  Trade Supplies','Western Trade Supplies']):
        row['invoice']['seller_name']=name
    records[-1]['invoice']['seller_gstin']=''
    before=deepcopy([r['invoice'] for r in records])
    export_all(tmp_path,records,True)
    folder=Path(records[0]['output_path']);base=folder.parent
    first=voucher_map(ET.parse(folder/'Sales_Vouchers.xml'))
    generation=records[0]['output_generation']
    for _ in range(11):export_all(tmp_path,records,True)
    assert {r['output_path'] for r in records}=={str(folder)}
    assert folder.name=='current' and records[0]['output_generation']!=generation
    assert {p.name for p in base.iterdir() if p.is_dir() and p.name!='.automation'}=={'current','previous'}
    assert not any(p.is_dir() for p in folder.iterdir())
    assert first==voucher_map(ET.parse(folder/'Sales_Vouchers.xml'))
    assert before==[r['invoice'] for r in records]
    groups=client_import_groups(folder,folder)
    assert len(groups)==1 and voucher_count(groups[0]['plan'])==4
    assert voucher_map(response_xml(dict(groups[0]['plan'])['Sales_Vouchers.xml']))==first
    manifest=json.loads((folder/'Batch_Report.json').read_text())
    assert manifest['invoices'][-1]['extracted_invoice']['seller_gstin']==''
    assert manifest['input_count']==manifest['xml_voucher_count']==4


def test_different_sellers_route_separately_from_same_folder(tmp_path):
    records=rows(tmp_path);records[1]['invoice']['seller_name']='Another seller'
    records[2]['invoice']['seller_gstin']='29DEMOA1000A1Z5'
    export_all(tmp_path,records,True);folder=Path(records[0]['output_path'])
    saved={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    groups=client_import_groups(folder,folder)
    assert len(groups)==3 and sum(voucher_count(g['plan']) for g in groups)==4
    combined={}
    for group in groups:
        assert group['folders']==[folder]
        plan=dict(group['plan']);vouchers=response_xml(plan['Sales_Vouchers.xml'])
        masters=response_xml(plan['Masters.xml']);units=response_xml(plan['Units.xml'])
        assert {n.text for n in vouchers.findall('.//LEDGERNAME')}<={n.get('NAME') for n in masters.findall('.//LEDGER')}
        assert {n.text for n in vouchers.findall('.//STOCKITEMNAME')}=={n.get('NAME') for n in masters.findall('.//STOCKITEM')}
        assert {n.findtext('BASEUNITS') for n in masters.findall('.//STOCKITEM')}=={n.findtext('NAME') for n in units.findall('.//UNIT')}
        subset=voucher_map(vouchers);assert not set(subset)&set(combined);combined.update(subset)
    assert combined==voucher_map(ET.parse(folder/'Sales_Vouchers.xml'))
    assert saved=={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_publication_rolls_back_current_if_replacement_fails(tmp_path,monkeypatch):
    current=tmp_path/'current';current.mkdir();(current/'Batch_Report.json').write_text(json.dumps({'layout':LAYOUT}))
    (current/'original').write_text('retained')
    staged=tmp_path/'.staging-test';staged.mkdir()
    rename=Path.rename
    def fail(path,target):
        if path==staged:raise OSError('replacement failed')
        return rename(path,target)
    monkeypatch.setattr(Path,'rename',fail)
    with pytest.raises(OSError):publish(tmp_path,staged)
    assert (current/'original').read_text()=='retained'


def test_generation_change_rejects_mixed_snapshot(tmp_path,monkeypatch):
    from Common_Rules import tally_import
    records=rows(tmp_path);export_all(tmp_path,records,True);folder=Path(records[0]['output_path'])
    original=tally_import.import_plan
    def concurrent(path):
        result=original(path)
        manifest=json.loads((folder/'Batch_Report.json').read_text());manifest['generation']='changed'
        (folder/'Batch_Report.json').write_text(json.dumps(manifest))
        return result
    monkeypatch.setattr(tally_import,'import_plan',concurrent)
    with pytest.raises(ValueError,match='updated while reading'):client_import_groups(folder,folder)


def test_export_and_import_manifest_use_utf8_with_windows_default_encoding(tmp_path,monkeypatch):
    records=rows(tmp_path)
    for row in records:
        row['invoice']['seller_name']='व्यापार Supplies'
        row['invoice']['buyer_name']='ग्राहक Buyer'
    write_text=Path.write_text;read_text=Path.read_text
    def windows_write(path,data,encoding=None,errors=None,newline=None):
        return write_text(path,data,encoding=encoding or 'cp1252',errors=errors,newline=newline)
    def windows_read(path,encoding=None,errors=None):
        return read_text(path,encoding=encoding or 'cp1252',errors=errors)
    monkeypatch.setattr(Path,'write_text',windows_write)
    monkeypatch.setattr(Path,'read_text',windows_read)
    export_all(tmp_path,records,True)
    folder=Path(records[0]['output_path'])
    assert '→' in (folder/'Import_Instructions.txt').read_text(encoding='utf-8')
    assert len(ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER'))==4
    assert (folder/'Batch_Report.json').is_file()
    groups=client_import_groups(folder,folder)
    assert len(groups)==1 and 'व्यापार Supplies' in groups[0]['label']
    assert voucher_count(groups[0]['plan'])==4


def test_packs_export_has_distinct_explicit_formal_name_and_preserves_stock_unit(tmp_path):
    records=rows(tmp_path)[:1]
    for item in records[0]['invoice']['items']:item['unit']='Packs'
    export_all(tmp_path,records,True);folder=Path(records[0]['output_path'])
    unit=ET.parse(folder/'Units.xml').find('.//UNIT')
    assert unit.findtext('NAME')=='Packs'
    assert unit.findtext('ORIGINALNAME')=='Pack'
    assert unit.attrib=={'Action':'Create'}
    assert unit.find('ADDITIONALNAME') is None
    assert {n.text for n in ET.parse(folder/'Masters.xml').findall('.//BASEUNITS')}=={'Packs'}
    assert all(n.text.endswith(' Packs') for n in ET.parse(folder/'Sales_Vouchers.xml').findall('.//ACTUALQTY'))


def test_single_seller_button_plan_uses_exact_current_xml_files(tmp_path):
    records=rows(tmp_path);export_all(tmp_path,records,True)
    folder=Path(records[0]['output_path']);groups=client_import_groups(folder,folder)
    assert len(groups)==1
    assert dict(groups[0]['plan'])=={name:(folder/name).read_bytes() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}

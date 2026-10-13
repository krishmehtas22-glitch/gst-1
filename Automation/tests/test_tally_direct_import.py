"""Direct import changes destination only and observes actual Tally replies."""
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.tally_review_export import enable
from Common_Rules.tally_import import import_plan,company_payload,loaded_companies,send_plan,launch_tally

COMPANIES=b'<ENVELOPE><BODY><DATA><COLLECTION><COMPANY NAME="Client &amp; Sons"><NAME>Client &amp; Sons</NAME></COMPANY><COMPANY NAME="Other Company"/></COLLECTION></DATA></BODY></ENVELOPE>'
OK=b'<RESPONSE><CREATED>12</CREATED><ALTERED>0</ALTERED><IGNORED>0</IGNORED><ERRORS>0</ERRORS></RESPONSE>'


def prepared(root):
    folder=root/'Client';folder.mkdir()
    for pdf in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:2]:shutil.copy2(pdf,folder/pdf.name)
    enable(root,'Client');rows=process_sources(root)
    return Path(rows[0].get('group_output_path') or rows[0]['output_path'])


def test_direct_import_order_exact_business_output_and_files_unchanged(tmp_path):
    folder=prepared(tmp_path);plan=import_plan(folder)
    before={file.name:file.read_bytes() for file in folder.glob('*.xml')}
    posts=[]
    def transport(payload):
        document=ET.fromstring(payload)
        if document.findtext('./HEADER/TALLYREQUEST')=='Export':return COMPANIES
        posts.append(payload);return OK
    result=send_plan(plan,'Client & Sons',transport)
    assert [r['file'] for r in result]==['Units.xml','Masters.xml','Sales_Vouchers.xml']
    assert all(r['counts']['CREATED']==12 and not r['errors'] for r in result)
    for (_,original),sent in zip(plan,posts):
        before_doc=ET.fromstring(original);after_doc=ET.fromstring(sent)
        assert after_doc.findtext('.//SVCURRENTCOMPANY')=='Client & Sons'
        assert ET.tostring(before_doc.find('.//REQUESTDATA'))==ET.tostring(after_doc.find('.//REQUESTDATA'))
    assert before=={file.name:file.read_bytes() for file in folder.glob('*.xml')}


def test_master_rejection_does_not_send_dependent_vouchers(tmp_path):
    plan=import_plan(prepared(tmp_path));calls=[]
    def transport(payload):
        if ET.fromstring(payload).findtext('./HEADER/TALLYREQUEST')=='Export':return COMPANIES
        calls.append(payload)
        return OK if len(calls)==1 else b'<RESPONSE><ERRORS>1</ERRORS><LINEERROR>Missing stock unit</LINEERROR></RESPONSE>'
    result=send_plan(plan,'Other Company',transport)
    assert len(calls)==len(result)==2
    assert result[-1]['errors']==['Missing stock unit']


@pytest.mark.parametrize('failure',[b'<html>gateway</html>',b'not xml',b'<RESPONSE><STATUS>0</STATUS></RESPONSE>'])
def test_unknown_or_failure_result_is_not_retried(tmp_path,failure):
    plan=import_plan(prepared(tmp_path));calls=[]
    def transport(payload):
        if ET.fromstring(payload).findtext('./HEADER/TALLYREQUEST')=='Export':return COMPANIES
        calls.append(payload);return failure
    result=send_plan(plan,'Other Company',transport)
    assert len(calls)==len(result)==1 and result[0]['errors']


def test_network_failure_keeps_completed_stage_and_never_retries(tmp_path):
    plan=import_plan(prepared(tmp_path));calls=[]
    def transport(payload):
        if ET.fromstring(payload).findtext('./HEADER/TALLYREQUEST')=='Export':return COMPANIES
        calls.append(payload)
        if len(calls)==2:raise OSError('Connection lost after request')
        return OK
    result=send_plan(plan,'Other Company',transport)
    assert len(calls)==2 and result[-1]['status']=='unknown'
    assert result[0]['counts']['CREATED']==12


def test_destination_disappeared_stops_before_any_import(tmp_path):
    plan=import_plan(prepared(tmp_path));calls=[]
    def transport(payload):calls.append(payload);return COMPANIES
    with pytest.raises(ValueError,match='no longer available'):send_plan(plan,'Unavailable',transport)
    assert len(calls)==1
    assert ET.fromstring(calls[0]).findtext('./HEADER/TALLYREQUEST')=='Export'


def test_company_choice_required_and_xml_escaping(tmp_path):
    plan=import_plan(prepared(tmp_path))
    with pytest.raises(ValueError,match='Select'):company_payload(plan[0][1],'')
    assert loaded_companies(lambda _:COMPANIES)==['Client & Sons','Other Company']
    assert ET.fromstring(company_payload(plan[0][1],'Client & Sons')).findtext('.//SVCURRENTCOMPANY')=='Client & Sons'


def test_legacy_embedded_units_supported_without_xml_changes(tmp_path):
    folder=prepared(tmp_path);(folder/'Units.xml').unlink()
    assert [name for name,_ in import_plan(folder)]==['Masters.xml','Sales_Vouchers.xml']


def test_missing_or_wrong_envelope_rejected_before_external_write(tmp_path):
    with pytest.raises(ValueError,match='current XML'):import_plan(tmp_path)
    folder=prepared(tmp_path);(folder/'Masters.xml').write_text('<ENVELOPE/>')
    with pytest.raises(ValueError,match='Unexpected'):import_plan(folder)


def test_tally_launch_is_argv_not_shell(tmp_path,monkeypatch):
    from Common_Rules import tally_import
    executable=tmp_path/'Tally Prime'/'tally.exe';executable.parent.mkdir();executable.write_bytes(b'fixture')
    calls=[]
    monkeypatch.setattr(tally_import.os,'name','nt')
    # Keep pathlib's native path type when simulating a Windows launch on Linux.
    monkeypatch.setattr(tally_import,'Path',type(executable))
    monkeypatch.setattr(tally_import.subprocess,'Popen',lambda *a,**kw:calls.append((a,kw)))
    launch_tally(executable)
    assert calls==[(([str(executable)],),{'cwd':str(executable.parent)})]


def split_case_run(root,different_gstin=False):
    from Common_Rules.tally_review_export import export_all
    folder=root/'Client';folder.mkdir()
    for pdf in sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:12]:shutil.copy2(pdf,folder/pdf.name)
    rows=inspect_sources(root)
    for i,row in enumerate(rows):
        row['invoice']['seller_name']='Western Trade Supplies' if i<8 else 'WESTERN TRADE SUPPLIES'
        row['invoice']['seller_gstin']='27DEMOA1000A1Z5' if i<8 or not different_gstin else '29DEMOA1000A1Z5'
    exported=export_all(root,rows,True)
    return Path(exported[0]['output_path']),Path(exported[0]['group_output_path']),Path(exported[8]['group_output_path'])


def test_uppercase_and_normal_case_sets_import_together_without_output_change(tmp_path):
    from Common_Rules.tally_import import seller_import_plan,voucher_count
    run,normal,caps=split_case_run(tmp_path)
    files={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()}
    assert voucher_count(import_plan(normal))==8 and voucher_count(import_plan(caps))==4
    plan,folders=seller_import_plan(run,normal)
    assert set(folders)=={normal,caps} and voucher_count(plan)==12
    assert [name for name,_ in plan]==['Units.xml','Masters.xml','Sales_Vouchers.xml']
    before={v.findtext('GUID'):ET.tostring(v) for folder in (normal,caps)
            for v in ET.parse(folder/'Sales_Vouchers.xml').findall('.//VOUCHER')}
    after={v.findtext('GUID'):ET.tostring(v) for name,data in plan if name=='Sales_Vouchers.xml'
           for v in ET.fromstring(data).findall('.//VOUCHER')}
    assert before==after  # buyer, quantity, unit, rates, taxes, date, GUID, narration
    masters=ET.fromstring(dict(plan)['Masters.xml'])
    assert len([n for n in masters.findall('.//LEDGER') if n.get('NAME')=='Sales'])==1
    alternate,_=seller_import_plan(run,caps)
    assert dict(plan)==dict(alternate)
    assert files=={str(p):p.read_bytes() for p in run.rglob('*') if p.is_file()}


def test_same_name_different_gstin_remains_separate(tmp_path):
    from Common_Rules.tally_import import seller_import_plan,voucher_count
    run,normal,caps=split_case_run(tmp_path,different_gstin=True)
    plan,folders=seller_import_plan(run,normal)
    assert folders==[normal] and voucher_count(plan)==8
    other,folders=seller_import_plan(run,caps)
    assert folders==[caps] and voucher_count(other)==4


def test_report_cannot_pull_xml_from_another_run_or_client(tmp_path):
    import json
    from Common_Rules.tally_import import seller_import_plan
    run,normal,caps=split_case_run(tmp_path)
    path=run/'Batch_Report.json';report=json.loads(path.read_text())
    report['invoices'][0]['xml_folder']=str(tmp_path/'different-client')
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='outside the current run'):seller_import_plan(run,normal)


def test_all_folders_included_with_destinations_for_distinct_sellers(tmp_path):
    from Common_Rules.tally_import import client_import_groups,voucher_count
    run,normal,caps=split_case_run(tmp_path,different_gstin=True)
    groups=client_import_groups(run,normal)
    assert len(groups)==2
    assert {p for g in groups for p in g['folders']}=={normal,caps}
    assert sum(voucher_count(g['plan']) for g in groups)==12
    posts=[]
    def transport(payload):
        document=ET.fromstring(payload)
        if document.findtext('./HEADER/TALLYREQUEST')=='Export':return COMPANIES
        posts.append(document)
        return OK
    for group,target in zip(groups,['Client & Sons','Other Company']):
        send_plan(group['plan'],target,transport)
    voucher_requests=[p for p in posts if p.findtext('.//REPORTNAME')=='Vouchers']
    assert [(p.findtext('.//SVCURRENTCOMPANY'),len(p.findall('.//VOUCHER'))) for p in voucher_requests]==[('Client & Sons',8),('Other Company',4)]


def test_all_case_variant_folders_have_one_company_selection(tmp_path):
    from Common_Rules.tally_import import client_import_groups,voucher_count
    run,normal,caps=split_case_run(tmp_path)
    groups=client_import_groups(run,caps)
    assert len(groups)==1 and set(groups[0]['folders'])=={normal,caps}
    assert voucher_count(groups[0]['plan'])==12

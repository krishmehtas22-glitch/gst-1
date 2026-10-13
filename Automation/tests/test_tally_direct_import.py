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

"""Read-only company prerequisite prevents automatic replacement of invoice numbers."""
import xml.etree.ElementTree as ET
from copy import deepcopy
import pytest
from Common_Rules.tally_import import send_plan
from Common_Rules.voucher_number_guard import check_numbering


def sales_plan():
    return [('Sales_Vouchers.xml',b'<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA><TALLYMESSAGE><VOUCHER VCHTYPE="Sales" REMOTEID="stable"><GUID>stable</GUID><VOUCHERNUMBER>INV/26-27/001</VOUCHERNUMBER><REFERENCE>INV/26-27/001</REFERENCE><AMOUNT>123.45</AMOUNT></VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>')]


@pytest.mark.parametrize('reply',[
    b'<ENVELOPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>Automatic</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>',
    b'<ENVELOPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>None</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>',
    b'<ENVELOPE><VOUCHERTYPE NAME="Sales"/></ENVELOPE>',
    b'<ENVELOPE><VOUCHERTYPE NAME="Other"><NUMBERINGMETHOD>Manual</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>',
    b'<ENVELOPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>Manual</NUMBERINGMETHOD></VOUCHERTYPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>Automatic</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>',
    b'<RESPONSE><LINEERROR>Lookup failed</LINEERROR></RESPONSE>',b'not xml',
])
def test_unsafe_or_unknown_numbering_stops_before_any_import(reply):
    calls=[]
    def transport(payload):
        doc=ET.fromstring(payload);calls.append(doc)
        assert doc.findtext('./HEADER/TALLYREQUEST')=='Export'
        if doc.findtext('./HEADER/ID')=='InvoiceReaderCompanies':return b'<ENVELOPE><COMPANY NAME="A &amp; B"/></ENVELOPE>'
        assert doc.findtext('.//SVCURRENTCOMPANY')=='A & B'
        assert doc.findtext('.//FETCH')=='Name,NumberingMethod'
        return reply
    with pytest.raises(ValueError,match='No import sent.*Manual'):
        send_plan(sales_plan(),'A & B',transport,submit_all=True)
    assert len(calls)==2


def test_manual_numbering_preserves_complete_voucher_and_ids():
    plan=sales_plan();before=deepcopy(plan);calls=[]
    def transport(payload):
        doc=ET.fromstring(payload);calls.append(doc)
        if doc.findtext('./HEADER/ID')=='InvoiceReaderCompanies':return b'<ENVELOPE><COMPANY NAME="Client"/></ENVELOPE>'
        if doc.findtext('./HEADER/ID')=='InvoiceReaderVoucherNumbering':return b'<ENVELOPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>Manual</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>'
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    result=send_plan(plan,'Client',transport,submit_all=True)
    assert len(calls)==3 and result[0]['counts']['CREATED']==1
    assert ET.tostring(calls[-1].find('.//VOUCHER'))==ET.tostring(ET.fromstring(plan[0][1]).find('.//VOUCHER'))
    assert plan==before


def test_lookup_network_failure_does_not_retry_or_write():
    calls=[]
    def transport(payload):
        calls.append(payload);raise OSError('Disconnected')
    with pytest.raises(ValueError,match='No import sent'):
        check_numbering(sales_plan(),'Client',transport)
    assert len(calls)==1


def test_master_only_plan_needs_no_numbering_lookup():
    check_numbering([('Masters.xml',b'<ENVELOPE/>')],'Client',lambda _:pytest.fail('No vouchers'))


def test_installer_and_backup_record_exact_authorized_change():
    from pathlib import Path
    import hashlib,json,runpy,zipfile
    root=Path(__file__).parents[2]
    change=json.loads((root/'Automation/INVOICE_NUMBER_GUARD_CHANGE.json').read_text())
    package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(root/change['backup']) as archive:
        for name,entry in change['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==entry['baseline_sha256']
            expected=entry['authorized_sha256']
            for filename in ('LOCAL_GEMMA_CHANGE.json','AI_WORKFLOW_CHANGE.json','IMPORT_REVIEW_UX_CHANGE.json'):
                latest=json.loads((root/'Automation'/filename).read_text())
                if name in latest['files']:
                    update=latest['files'][name];assert update['baseline_sha256']==expected
                    with zipfile.ZipFile(root/latest['backup']) as previous:
                        assert hashlib.sha256(previous.read(name)).hexdigest()==expected
                    expected=update['authorized_sha256']
            from test_sales_invoice_procedure import after_sales_procedure
            after_sales_procedure(root,name,expected)
    for name,digest in change['new_files'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
        assert package['FILES'][name.removeprefix('Automation/')].encode()==(root/name).read_bytes()
    assert package['FILES']['Common_Rules/tally_import.py'].encode()==(root/'Automation/Common_Rules/tally_import.py').read_bytes()
    assert change['files']['Automation/Common_Rules/tally_import.py']['baseline_sha256'] in package['AUTHORIZED_ENGINE']['Common_Rules/tally_import.py']

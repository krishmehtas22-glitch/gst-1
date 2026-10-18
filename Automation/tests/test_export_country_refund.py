from copy import deepcopy
from decimal import Decimal
import importlib.util,json,sys,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.desktop import inspect_sources
from Common_Rules.tally_review_export import export_all
from Common_Rules.export_metadata import export_country
from Export_Refund_Review import summary,save_review,load_review


def row(country='United Kingdom',classification='export_igst'):
    return {'client':'Client','path':'invoice.pdf','digest':'source','invoice':{'number':'EXP-1','date':'2026-10-17','seller_gstin':'27TEST',
        'buyer_country':country,'classification':classification,'supply':'EXPORT','place_of_supply':'Outside India',
        'taxable':'100000.00','total':'118000.00','igst':'18000.00','cgst':'0','sgst':'0'}}


def fixture_rows(tmp_path):
    import shutil
    shutil.copytree(Path(__file__).parent/'fixtures/client23',tmp_path/'Client')
    return inspect_sources(tmp_path)


def old_exporter():
    import types
    root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Before_Export_Country_Refund.zip') as z:source=z.read('Automation/Common_Rules/tally_review_export.py')
    module=types.ModuleType('Common_Rules._previous_exporter');module.__package__='Common_Rules'
    exec(compile(source,'previous_exporter.py','exec'),module.__dict__)
    return module


def xml_files(rows):
    folder=Path(rows[0]['output_path'])
    return {name:(folder/name).read_bytes() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}


def test_domestic_output_is_byte_identical_to_previous_exporter(tmp_path):
    rows=[r for r in fixture_rows(tmp_path) if r['invoice'].get('supply')!='EXPORT']
    before=xml_files(old_exporter().export_all(tmp_path,deepcopy(rows),True))
    after=xml_files(export_all(tmp_path,deepcopy(rows),True))
    assert before==after


def test_export_country_added_without_changing_financial_allocations(tmp_path):
    rows=[r for r in fixture_rows(tmp_path) if r['invoice'].get('supply')=='EXPORT']
    assert rows
    before=xml_files(old_exporter().export_all(tmp_path,deepcopy(rows),True))
    original=deepcopy(rows)
    result=export_all(tmp_path,rows,True);after=xml_files(result)
    old=ET.fromstring(before['Sales_Vouchers.xml']);new=ET.fromstring(after['Sales_Vouchers.xml'])
    for prior,current,source in zip(old.findall('.//VOUCHER'),new.findall('.//VOUCHER'),rows):
        assert current.findtext('COUNTRYOFRESIDENCE')==export_country(source['invoice'])
        assert current.findtext('PLACEOFSUPPLY')=='Outside India'
        for field in ('GUID','VOUCHERNUMBER','DATE','PARTYLEDGERNAME'):assert current.findtext(field)==prior.findtext(field)
        assert [ET.tostring(x) for x in current.findall('ALLLEDGERENTRIES.LIST')]==[ET.tostring(x) for x in prior.findall('ALLLEDGERENTRIES.LIST')]
    masters=ET.fromstring(after['Masters.xml'])
    for r in rows:
        name=next(v.findtext('PARTYLEDGERNAME') for v in new.findall('.//VOUCHER') if v.findtext('VOUCHERNUMBER')==r['invoice']['number'])
        ledger=next(n for n in masters.findall('.//LEDGER') if n.get('NAME')==name)
        assert ledger.findtext('COUNTRYNAME')==export_country(r['invoice'])
    assert [r['invoice'] for r in rows]==[r['invoice'] for r in original]
    assert before['Units.xml']==after['Units.xml']


@pytest.mark.parametrize('country',['',None,'India','Imaginaryland'])
def test_missing_invalid_country_preserves_previous_output(tmp_path,country):
    rows=[r for r in fixture_rows(tmp_path) if r['invoice'].get('supply')=='EXPORT']
    current=export_all(tmp_path,deepcopy(rows),True);prior=xml_files(current)
    rows[0]['invoice']['buyer_country']=country
    with pytest.raises(ValueError,match='Export country required'):export_all(tmp_path,rows,True)
    assert xml_files(current)==prior


def test_refund_is_invoice_igst_reference_and_review_is_separate(tmp_path):
    record=row();before=deepcopy(record)
    info=summary(record)
    assert info['estimate']=='18000.00' and info['status']=='Unverified'
    assert 'proof of tax payment' in info['reason']
    assert load_review(tmp_path,record) is None
    saved=save_review(tmp_path,record,'Eligibility reviewed',notes='Checked documents and applicable eligibility separately.')
    assert saved['tally_posting'] is False and saved['manual_review'] is True
    assert record==before and not list(tmp_path.rglob('*.xml'))
    assert load_review(tmp_path,record)['status']=='Eligibility reviewed'
    record['invoice']['igst']='17000.00'
    assert load_review(tmp_path,record) is None


def test_lut_does_not_mean_zero_itc_refund():
    record=row(classification='export_lut');record['invoice'].update(igst='0',total='100000')
    info=summary(record)
    assert info['estimate'] is None and 'ITC' in info['status']


@pytest.mark.parametrize('patch',[{'igst':None},{'cgst':'10'},{'sgst':None},{'igst':'NaN'},{'igst':'-1'}, {'buyer_country':''},{'place_of_supply':'Maharashtra'},{'place_of_supply':'27 - Maharashtra'},{'foreign_currency':'USD','exchange_rate':None}])
def test_missing_conflicting_tax_country_and_currency_never_produce_estimate(patch):
    record=row();record['invoice'].update(patch)
    assert summary(record)['estimate'] is None


def test_claimed_status_requires_separate_amount_reference_and_no_excess(tmp_path):
    for amount,reference in [('18000',''),('19000','SB-1'),('-1','SB-1')]:
        with pytest.raises(ValueError):save_review(tmp_path,row(),'Claimed',amount,reference)
    saved=save_review(tmp_path,row(),'Claimed','15000','SB-1')
    assert saved['claim_amount']=='15000.00' and saved['invoice_igst_reference']=='18000.00'
    assert saved['tally_posting'] is False


def exercise_refund_dialog_in_existing_app(root,app,tmp_path):
    import tkinter as tk
    from tkinter import ttk
    record=deepcopy(app.records[0]);record.update(invoice=row()['invoice'],listing_only=False)
    app.records[0]=record;app.table.selection_set('0');app.apply_filter();root.update()
    assert app.table.set('0','export_country')=='United Kingdom'
    assert '18,000.00' in app.table.set('0','refund_estimate')
    app.export_refund_review();root.update()
    top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Export IGST refund review')
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    widgets=list(descendants(top))
    next(w for w in widgets if isinstance(w,ttk.Combobox)).set('Eligibility reviewed')
    next(w for w in widgets if isinstance(w,tk.Text)).insert('1.0','Manually checked supporting records.')
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Save review').invoke();root.update()
    assert not top.winfo_exists()
    assert 'Eligibility reviewed' in app.table.set('0','refund_estimate')
    assert load_review(tmp_path,record)['notes']=='Manually checked supporting records.'


def test_source_installer_installs_country_helpers_and_can_repeat_without_changing_core(tmp_path):
    import runpy,hashlib
    root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Reader_Before_BillSync_UI.zip') as z:
        for name in z.namelist():
            if name.startswith('Automation/') and not name.endswith('/'):
                target=tmp_path/name.removeprefix('Automation/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
    installer=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    original=(tmp_path/'Invoice_Desktop.py').read_bytes()
    backup=installer['install'](tmp_path)
    assert (backup/'Common_Rules/tally_review_export.py').exists()
    assert (tmp_path/'Common_Rules/export_metadata.py').read_bytes()==(root/'Automation/Common_Rules/export_metadata.py').read_bytes()
    assert (tmp_path/'Export_Refund_Review.py').is_file()
    installer['install'](tmp_path)
    update=json.loads((root/'Automation/AI_WORKFLOW_CHANGE.json').read_text())['files']['Automation/Invoice_Desktop.py']
    assert hashlib.sha256(original).hexdigest()==update['baseline_sha256']
    assert (backup/'Invoice_Desktop.py').read_bytes()==original
    latest=json.loads((root/'Automation/IMPORT_REVIEW_UX_CHANGE.json').read_text())['files']['Automation/Invoice_Desktop.py']
    assert latest['baseline_sha256']==update['authorized_sha256']
    from test_sales_invoice_procedure import after_sales_procedure
    after_sales_procedure(root,'Automation/Invoice_Desktop.py',latest['authorized_sha256'])
    assert (tmp_path/'Invoice_Desktop.py').read_bytes()==(root/'Automation/Invoice_Desktop.py').read_bytes()
    target=tmp_path/'Common_Rules/tally_import.py';target.write_bytes(target.read_bytes()+b'\n# local change\n')
    before=(tmp_path/'BillSync_UI.py').read_bytes()
    with pytest.raises(ValueError,match='No files changed'):installer['install'](tmp_path)
    assert (tmp_path/'BillSync_UI.py').read_bytes()==before

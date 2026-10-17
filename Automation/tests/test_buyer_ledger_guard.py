"""Role checks and explicit local correction; no live AI/Tally calls."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.buyer_ledger_guard import party_conflict
from Common_Rules.tally_master_matching import assignments,bind_snapshot,context,save_choices,loaded_choices
from Common_Rules.tally_review_export import export_all
from Buyer_Ledger_Dialog import save_party
from Tally_Master_Snapshot import parse_collection,save_snapshot
from test_tally_master_matching import setup,choices,choice


def assert_after_guard(repo,name,expected):
    change=json.loads((repo/'Automation/BUYER_LEDGER_GUARD_CHANGE.json').read_text())
    if name in change['files']:
        entry=change['files'][name];assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(repo/change['backup']) as z:assert hashlib.sha256(z.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    pdf=json.loads((repo/'Automation/PDF_UPLOAD_VALIDATION_CHANGE.json').read_text())
    if name in pdf['files']:
        entry=pdf['files'][name];assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(repo/pdf['backup']) as z:assert hashlib.sha256(z.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    ocr=json.loads((repo/'Automation/OCR_REVIEW_GUARD_CHANGE.json').read_text())
    if name in ocr['files']:
        entry=ocr['files'][name];assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(repo/ocr['backup']) as z:assert hashlib.sha256(z.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    premium=json.loads((repo/'Automation/PREMIUM_UI_CHANGE.json').read_text())
    if name in premium['files']:
        entry=premium['files'][name];assert entry['baseline_sha256']==expected
        with zipfile.ZipFile(repo/premium['backup']) as z:assert hashlib.sha256(z.read(name)).hexdigest()==expected
        expected=entry['authorized_sha256']
    from test_premium_ui import after_boxed_ui
    after_boxed_ui(repo,name,expected)


@pytest.mark.parametrize('name',['Sales','CGST','SGST','IGST','Cess','Round Off','Round-Off','ROUND_OFF','Invoice differences - review','CGST @9%'])
def test_reserved_names_rejected_even_under_debtors(name):
    assert party_conflict({'name':name,'parent':'Sundry Debtors'})


@pytest.mark.parametrize('group',['Sales Accounts','Duties & Taxes','Bank Accounts','Cash-in-Hand','Indirect Expenses','Purchase Accounts','','Retail Customers'])
def test_non_party_and_unverified_groups_require_review(group):
    assert party_conflict({'name':'Buyer Trading','parent':group})


@pytest.mark.parametrize('group',['Sundry Debtors','Sundry Creditors'])
def test_real_party_names_are_not_rejected_for_containing_sales_or_bank(group):
    assert not party_conflict({'name':'Sales India Traders Pvt Ltd','parent':group})
    assert not party_conflict({'name':'ABC Bank Ltd','parent':group})


def with_bad_party(root,name='CGST',group='Duties & Taxes'):
    record,ctx=setup(root);data=deepcopy(ctx['data'])
    raw='<ENVELOPE><COLLECTION><LEDGER NAME="'+name+'"><PARENT>'+group.replace('&','&amp;')+'</PARENT><PARTYGSTIN>27MATCH</PARTYGSTIN></LEDGER></COLLECTION></ENVELOPE>'
    data['ledgers']+=parse_collection(raw,'ledgers')
    bind_snapshot(root,'Client',save_snapshot(root,data));ctx=context(root,record)
    pick=choices();pick['party']=choice('L1');save_choices(root,record,ctx,record['invoice'],pick)
    return record,ctx


def test_matching_gstin_cannot_override_bad_role_and_old_xml_is_retained(tmp_path):
    record,ctx=setup(tmp_path);export_all(tmp_path,[record],False)
    folder=Path(record['output_path']);before={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    record,ctx=with_bad_party(tmp_path)
    result=assignments(tmp_path,record,ctx)
    assert result['party'] is None and 'reserved' in result['party_conflict']
    with pytest.raises(ValueError,match='Previous XML retained'):export_all(tmp_path,[record],False)
    assert before=={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_existing_debtor_named_sales_blocks_even_with_a_different_correct_buyer(tmp_path):
    record,ctx=with_bad_party(tmp_path,'Sales','Sundry Debtors')
    save_party(tmp_path,record,ctx,'L0')
    with pytest.raises(ValueError,match="needs it Under 'Sales Accounts'"):export_all(tmp_path,[record],False)


def test_correcting_selection_is_local_preserves_item_choices_facts_and_guids(tmp_path):
    record,ctx=setup(tmp_path);export_all(tmp_path,[record],False)
    folder=Path(record['output_path']);before=ET.parse(folder/'Sales_Vouchers.xml').getroot()
    record,ctx=with_bad_party(tmp_path);facts=deepcopy(record['invoice']);olditems=loaded_choices(tmp_path,record,ctx)['items']
    with pytest.raises(ValueError):save_party(tmp_path,record,ctx,'L1')
    save_party(tmp_path,record,ctx,'L0')
    assert loaded_choices(tmp_path,record,ctx)['items']==olditems
    export_all(tmp_path,[record],False);after=ET.parse(folder/'Sales_Vouchers.xml').getroot()
    assert after.findtext('.//PARTYLEDGERNAME')=='Northstar Hardware Account'
    for tag in ('GUID','DATE','VOUCHERNUMBER','ACTUALQTY','BILLEDQTY','RATE'):
        assert [n.text for n in before.iter(tag)]==[n.text for n in after.iter(tag)]
    assert [n.text for n in before.iter('AMOUNT')]==[n.text for n in after.iter('AMOUNT')]
    assert record['invoice']==facts


def test_current_creation_remains_an_explicit_safe_fallback(tmp_path):
    record,ctx=with_bad_party(tmp_path)
    save_party(tmp_path,record,ctx,None);export_all(tmp_path,[record],False)
    doc=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml')
    assert doc.findtext('.//PARTYLEDGERNAME')=='Northstar Hardware'


def test_manual_party_still_checks_buyer_identity(tmp_path):
    record,ctx=setup(tmp_path);record['invoice']['buyer_gstin']='29OTHER'
    with pytest.raises(ValueError,match='GSTIN'):save_party(tmp_path,record,ctx,'L0')


def test_new_backup_and_installer_are_exact():
    import runpy
    repo=Path(__file__).parents[2];change=json.loads((repo/'Automation/BUYER_LEDGER_GUARD_CHANGE.json').read_text())
    for name,entry in change['files'].items():assert_after_guard(repo,name,entry['baseline_sha256'])
    installer=runpy.run_path(str(repo/'Install_BillSync_Source.py'))
    for name in ('Buyer_Ledger_Dialog.py','Common_Rules/buyer_ledger_guard.py','Common_Rules/tally_master_matching.py','Common_Rules/tally_master_xml.py'):
        assert installer['FILES'][name]==(repo/'Automation'/name).read_text()


def exercise_buyer_review_ui(root,app,tmp_path,monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    record,ctx=with_bad_party(tmp_path);app.records[0]=record
    app.table.selection_set('0');app.table.focus('0');app.apply_filter();root.update()
    calls=[];monkeypatch.setattr(app,'reset',lambda:calls.append('reset'))
    monkeypatch.setattr(app,'revalidate',lambda **kw:calls.append(kw))
    app.review_buyer_ledger();root.update()
    top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Review buyer ledger')
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    widgets=list(descendants(top));combo=next(w for w in widgets if isinstance(w,ttk.Combobox))
    options=combo.cget('values');assert not any(str(v).startswith('CGST') for v in options)
    combo.set(next(v for v in options if str(v).startswith('Northstar Hardware Account')))
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Save buyer & prepare XML').invoke();root.update()
    assert not top.winfo_exists() and calls==['reset',{'client_names':['Client']}]
    assert loaded_choices(tmp_path,record,ctx)['party']['id']=='L0'

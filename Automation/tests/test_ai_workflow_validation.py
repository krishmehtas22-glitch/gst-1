"""Whole-workflow checks: real generated XML, fake AI/Tally, no live writes."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,threading,time
import xml.etree.ElementTree as ET
import pytest
from test_review_voucher_structure import record
from test_tally_master_matching import setup,choices
from Common_Rules.demo import test_gstin as make_gstin
from Common_Rules.workflow_validation import enable,checks,MARKER,WorkflowReviewRequired,require_plan,acknowledge
from Common_Rules.tally_review_export import export_all
from Common_Rules.tally_import import import_plan,send_plan
from Common_Rules.tally_master_matching import assignments,save_choices,context,bind_snapshot
from Tally_Master_Snapshot import save_snapshot

SELLER=make_gstin('27ABCDE1234F1Z')
BUYER=make_gstin('27BCDEF2345G1Z')


def source_row(root):
    row=record(root);source=Path(row['path']);source.write_bytes(b'Synthetic invoice source; offline workflow test.')
    row['digest']=hashlib.sha256(source.read_bytes()).hexdigest()
    row['invoice'].update(seller_gstin=SELLER,seller_state='Maharashtra',buyer_gstin=BUYER,buyer_state='Maharashtra')
    enable(root);return row


def output(root,row):
    export_all(root,[row],True);folder=Path(row['output_path'])
    return folder,import_plan(folder),ET.parse(folder/'Sales_Vouchers.xml').find('.//VOUCHER')


def server(gstin=SELLER,state='Maharashtra'):
    writes=[];reads=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            reads.append(doc.findtext('./HEADER/ID'))
            if reads[-1]=='BillSyncWorkflowCompany':return ('<ENVELOPE><COLLECTION><COMPANY NAME="Company"><GSTIN>'+gstin+'</GSTIN><STATENAME>'+state+'</STATENAME></COMPANY></COLLECTION></ENVELOPE>').encode()
            if reads[-1]=='InvoiceReaderVoucherNumbering':return b'<ENVELOPE><VOUCHERTYPE NAME="Sales"><NUMBERINGMETHOD>Manual</NUMBERINGMETHOD></VOUCHERTYPE></ENVELOPE>'
            if reads[-1]=='InvoiceReaderCompanies':return b'<ENVELOPE><COMPANY NAME="Company"/></ENVELOPE>'
            return b'<ENVELOPE><COLLECTION/></ENVELOPE>'
        writes.append(doc)
        assert MARKER not in doc.attrib
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    return transport,writes,reads


def test_valid_domestic_fields_reach_all_three_import_stages_exactly(tmp_path):
    row=source_row(tmp_path);original=deepcopy(row['invoice']);folder,plan,v=output(tmp_path,row)
    assert row['workflow_ready'] and not row['workflow_issues']
    assert v.findtext('DATE')=='20261002' and v.findtext('VOUCHERNUMBER')==original['number']
    assert v.findtext('PARTYGSTIN')==BUYER and v.findtext('STATENAME')==v.findtext('PLACEOFSUPPLY')=='Maharashtra'
    assert ET.parse(folder/'Masters.xml').findtext('.//LEDGER[@NAME="Northstar Hardware"]/LEDSTATENAME')=='Maharashtra'
    transport,writes,reads=server();result=send_plan(plan,'Company',transport,submit_all=True)
    assert [r['file'] for r in result]==['Units.xml','Masters.xml','Sales_Vouchers.xml']
    assert writes[-1].findtext('.//VOUCHERNUMBER')==original['number']
    assert row['invoice']==original and reads[0]=='BillSyncWorkflowCompany'


@pytest.mark.parametrize('field,value',[('number',''),('date',''),('place_of_supply',''),('buyer_name',''),('buyer_state','Mars')])
def test_missing_invoice_data_requires_explicit_user_override_without_invention(tmp_path,field,value):
    row=source_row(tmp_path);row['invoice'][field]=value;_,plan,v=output(tmp_path,row)
    assert not row['workflow_ready']
    transport,writes,reads=server()
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',transport)
    assert any(p['blocking'] for p in caught.value.issues) and not writes
    assert reads==['BillSyncWorkflowCompany']
    approved=acknowledge(plan,caught.value,tmp_path)
    require_plan(approved,'Company',transport)
    assert not writes
    approved_v=ET.fromstring(dict(approved)['Sales_Vouchers.xml']).find('.//VOUCHER')
    assert ET.tostring(approved_v)==ET.tostring(v)
    if field=='number':assert not v.findtext('VOUCHERNUMBER') and 'UNREAD-' not in (v.findtext('VOUCHERNUMBER') or '')


def test_gstin_conflict_has_explicit_exact_output_acknowledgement(tmp_path):
    row=source_row(tmp_path);row['invoice']['buyer_gstin']='27INVALID'
    folder,plan,v=output(tmp_path,row);transport,writes,reads=server()
    with pytest.raises(WorkflowReviewRequired) as caught:send_plan(plan,'Company',transport,submit_all=True)
    assert not writes and any(p['field']=='Buyer GSTIN' for p in caught.value.issues)
    approved=acknowledge(plan,caught.value,folder)
    send_plan(approved,'Company',transport,submit_all=True)
    assert writes[-1].findtext('.//PARTYGSTIN')=='27INVALID'
    assert json.loads((folder/'Workflow_Review_Decisions.json').read_text())['decisions'][0]['token']==caught.value.token
    changed=[]
    for name,data in approved:
        if name=='Sales_Vouchers.xml':
            doc=ET.fromstring(data);doc.find('.//VOUCHERNUMBER').text='CHANGED';data=ET.tostring(doc)
        changed.append((name,data))
    with pytest.raises(ValueError,match='XML changed'):require_plan(changed,'Company',transport)


def test_company_registration_changes_invalidate_prior_acknowledgement(tmp_path):
    row=source_row(tmp_path);folder,plan,_=output(tmp_path,row)
    transport,writes,_=server(BUYER)
    with pytest.raises(WorkflowReviewRequired) as first:require_plan(plan,'Company',transport)
    approved=acknowledge(plan,first.value,folder);require_plan(approved,'Company',transport)
    other,_,_=server(make_gstin('29ABCDE1234F1Z'),'Karnataka')
    with pytest.raises(WorkflowReviewRequired):require_plan(approved,'Company',other)
    assert not writes


def test_source_and_manual_review_changes_block_old_xml(tmp_path):
    row=source_row(tmp_path);_,plan,_=output(tmp_path,row)
    review=tmp_path/'.invoice_app'/'reviews'/(row['digest']+'.json');review.parent.mkdir();review.write_text('{}')
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',lambda _:pytest.fail('No lookup for changed input'))
    assert any(p['field']=='Saved invoice review' and p['blocking'] for p in caught.value.issues)
    review.unlink();Path(row['path']).write_bytes(b'Changed invoice')
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',lambda _:pytest.fail('No lookup for changed source'))
    assert any(p['field']=='Source invoice' for p in caught.value.issues)


def with_masters(root):
    row=source_row(root);sample,ctx=setup(root);row['invoice']['buyer_name']='Northstar Hardware Account'
    data=deepcopy(ctx['data']);ledger=data['ledgers'][0]
    ledger['fields']['PARTYGSTIN']=[BUYER];node=ET.fromstring(ledger['xml']);node.find('PARTYGSTIN').text=BUYER;ledger['xml']=ET.tostring(node,encoding='unicode')
    data['company']='Company';bind_snapshot(root,'Client',save_snapshot(root,data));ctx=context(root,row)
    save_choices(root,row,ctx,row['invoice'],choices());return row,ctx


def test_component_gst_conflict_rejects_reuse_and_warns_before_import(tmp_path):
    row,ctx=with_masters(tmp_path);row['invoice']['items'][0].update(cgst_rate='8',sgst_rate='10')
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    assert assignments(tmp_path,row,ctx)['items'][0]['stock'] is None
    _,plan,_=output(tmp_path,row);transport,writes,_=server()
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',transport)
    assert any('Proposed stock' in p['reason'] for p in caught.value.issues) and not writes


def test_same_name_different_gstin_keeps_invoice_party_and_requires_review(tmp_path):
    row,ctx=with_masters(tmp_path);row['invoice']['buyer_gstin']=make_gstin('29BCDEF2345G1Z')
    row['invoice']['buyer_state']='Karnataka';save_choices(tmp_path,row,ctx,row['invoice'],choices())
    _,plan,v=output(tmp_path,row);transport,_,_=server()
    assert 'invoice party' in v.findtext('PARTYLEDGERNAME')
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',transport)
    assert any(p['master']==BUYER and p['field']=='Buyer GSTIN' for p in caught.value.issues)


def test_case_and_minor_spelling_reuse_compatible_party_and_stock(tmp_path):
    row,ctx=with_masters(tmp_path);row['invoice']['buyer_name']='NORTHSTAR HARDWARE ACCOUNT';row['invoice']['items'][0]['name']='RACK - STEEL'
    save_choices(tmp_path,row,ctx,row['invoice'],choices());found=assignments(tmp_path,row,ctx)
    assert found['party'] and found['items'][0]['stock']
    # Without GSTIN, use a high-confidence AI choice plus close, unique name and no conflicting facts.
    data=deepcopy(ctx['data']);data['ledgers'][0]['fields']['PARTYGSTIN']=['']
    node=ET.fromstring(data['ledgers'][0]['xml']);node.find('PARTYGSTIN').text='';data['ledgers'][0]['xml']=ET.tostring(node,encoding='unicode')
    bind_snapshot(tmp_path,'Client',save_snapshot(tmp_path,data));ctx=context(tmp_path,row)
    row['invoice'].update(buyer_gstin='',buyer_name='Northstar Hardwere Account')
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    assert assignments(tmp_path,row,ctx)['party']['name']=='Northstar Hardware Account'


@pytest.mark.parametrize('mode',['export_lut','export_igst'])
def test_export_posts_items_exact_quantities_and_preserves_gst_mode(tmp_path,mode):
    row=source_row(tmp_path);inv=row['invoice'];igst='0' if mode=='export_lut' else '3960'
    inv.update(supply='EXPORT',classification=mode,export_mode='LUT_without_payment' if mode=='export_lut' else 'with_payment_of_IGST',
        buyer_country='United Kingdom',buyer_gstin='',buyer_state='',place_of_supply='United Kingdom',cgst='0',sgst='0',igst=igst,total='22000' if mode=='export_lut' else '25960')
    for item in inv['items']:item.update(cgst_rate='0',sgst_rate='0',igst_rate='0' if mode=='export_lut' else '18')
    before=deepcopy(inv);folder,plan,v=output(tmp_path,row)
    assert len(v.findall('ALLINVENTORYENTRIES.LIST'))==2
    assert [n.findtext('ACTUALQTY') for n in v.findall('ALLINVENTORYENTRIES.LIST')]==['4 Nos','3 Nos']
    assert v.findtext('PLACEOFSUPPLY')=='Outside India' and v.findtext('COUNTRYOFRESIDENCE')=='United Kingdom'
    assert len(ET.parse(folder/'Masters.xml').findall('.//STOCKITEM'))==2 and row['invoice']==before
    transport,writes,_=server()
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',transport)
    assert not any(p['blocking'] for p in caught.value.issues)
    approved=acknowledge(plan,caught.value,folder);send_plan(approved,'Company',transport,submit_all=True)
    assert len(writes[-1].findall('.//ALLINVENTORYENTRIES.LIST'))==2


def test_export_lut_can_reuse_existing_taxable_stock_without_changing_master(tmp_path):
    row,ctx=with_masters(tmp_path);inv=row['invoice']
    inv.update(supply='EXPORT',classification='export_lut',export_mode='LUT_without_payment',buyer_country='United Kingdom',place_of_supply='United Kingdom',buyer_gstin='',cgst='0',sgst='0',igst='0',total='22000')
    for item in inv['items']:item.update(cgst_rate='0',sgst_rate='0',igst_rate='0')
    pick=choices();pick['party']=None;save_choices(tmp_path,row,ctx,inv,pick)
    assert assignments(tmp_path,row,ctx)['items'][0]['stock']['name']=='Rack - Steel'


def test_groq_batches_overlap_with_shared_cap_and_pacing(tmp_path,monkeypatch):
    from Common_Rules.gemini_batch import read_batch,RequestBudget
    from Common_Rules import groq_reader
    from Common_Rules.ai_providers import INTERVALS
    enable(tmp_path);monkeypatch.setitem(INTERVALS,'Groq',0)
    rows=[]
    for index in range(4):
        folder=tmp_path/str(index);folder.mkdir();row=source_row(folder)
        # Sources must live below the batch root; each unique source needs a distinct cache identity.
        Path(row['path']).write_bytes(str(index).encode());row['digest']=hashlib.sha256(str(index).encode()).hexdigest();rows.append(row)
    barrier=threading.Barrier(2);lock=threading.Lock();active=[0];maximum=[0];calls=[]
    def extract(root,row):
        with lock:active[0]+=1;maximum[0]=max(maximum[0],active[0]);calls.append(row['digest']);number=len(calls)
        if number<=2:barrier.wait(timeout=5)
        try:
            path=groq_reader.cache_path(root,row);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'revision':groq_reader.REVISION,'model':groq_reader.configured_model(),'source_sha256':row['digest'],'invoice':row['invoice']}))
        finally:
            with lock:active[0]-=1
    budget=RequestBudget(4);result=read_batch(tmp_path,rows,provider='Groq',extract=extract,request_budget=budget)
    assert maximum[0]==2 and budget.used==len(calls)==4
    assert [r['digest'] for r in result]==[r['digest'] for r in rows] and all(r['status']=='extracted' for r in result)


def test_selected_invoice_import_excludes_unprocessed_neighbour(tmp_path):
    from Common_Rules.workflow_validation import selected_invoice_plan
    first=source_row(tmp_path);second=deepcopy(first)
    second['path']=str(tmp_path/'second.pdf');Path(second['path']).write_bytes(b'Second source')
    second['digest']=hashlib.sha256(b'Second source').hexdigest();second['invoice']['number']='SECOND'
    second['invoice']['buyer_name']='Other buyer';second['invoice']['place_of_supply']=''
    export_all(tmp_path,[first,second],True);plan=import_plan(first['output_path'])
    transport,writes,_=server()
    with pytest.raises(WorkflowReviewRequired):require_plan(plan,'Company',transport)
    selected=selected_invoice_plan(plan,first);require_plan(selected,'Company',transport)
    send_plan(selected,'Company',transport,submit_all=True)
    assert len(writes[-1].findall('.//VOUCHER'))==1 and writes[-1].findtext('.//VOUCHERNUMBER')==first['invoice']['number']
    assert len(ET.parse(Path(first['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==2


def test_ui_controller_changes_are_confined_to_import_workflow_and_backed_up():
    import ast,zipfile
    root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Before_AI_Workflow_Validation.zip') as archive:before=ast.parse(archive.read('Automation/Invoice_Desktop.py'))
    after=ast.parse((root/'Automation/Invoice_Desktop.py').read_bytes())
    previous=next(n for n in before.body if isinstance(n,ast.ClassDef) and n.name=='InvoiceApp')
    current=next(n for n in after.body if isinstance(n,ast.ClassDef) and n.name=='InvoiceApp')
    old_methods={n.name:n for n in previous.body if isinstance(n,ast.FunctionDef)}
    new_methods={n.name:n for n in current.body if isinstance(n,ast.FunctionDef)}
    assert old_methods.keys()==new_methods.keys()
    for name,node in old_methods.items():
        if name!='import_tally':assert ast.dump(node)==ast.dump(new_methods[name]),name


def test_quota_error_stops_new_groq_requests_and_preserves_source_order(tmp_path,monkeypatch):
    from Common_Rules.gemini_batch import read_batch,RequestBudget
    from Common_Rules.ai_providers import INTERVALS
    enable(tmp_path);monkeypatch.setitem(INTERVALS,'Groq',0);rows=[]
    for index in range(5):
        folder=tmp_path/str(index);folder.mkdir();row=source_row(folder)
        Path(row['path']).write_bytes(str(index).encode());row['digest']=hashlib.sha256(str(index).encode()).hexdigest();rows.append(row)
    calls=[]
    def extract(root,row):calls.append(row['digest']);raise ValueError('Groq HTTP 429: quota reached')
    result=read_batch(tmp_path,rows,provider='Groq',extract=extract,request_budget=RequestBudget(5))
    assert 1<=len(calls)<=2 and len(result)==5
    assert [r['digest'] for r in result]==[r['digest'] for r in rows]
    assert not any(r['status']=='extracted' for r in result)


def test_new_workflow_preserves_cloud_request_start_pacing(tmp_path,monkeypatch):
    from Common_Rules.gemini_batch import read_batch
    from Common_Rules import groq_reader
    from Common_Rules.ai_providers import INTERVALS
    enable(tmp_path);monkeypatch.setitem(INTERVALS,'Groq',13);rows=[];waits=[]
    for index in range(3):
        folder=tmp_path/str(index);folder.mkdir();row=source_row(folder)
        Path(row['path']).write_bytes(str(index).encode());row['digest']=hashlib.sha256(str(index).encode()).hexdigest();rows.append(row)
    def extract(root,row):
        path=groq_reader.cache_path(root,row);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'revision':groq_reader.REVISION,'model':groq_reader.configured_model(),'source_sha256':row['digest'],'invoice':row['invoice']}))
    result=read_batch(tmp_path,rows,provider='Groq',extract=extract,wait=waits.append,clock=lambda:0)
    assert waits==[13,13] and all(r['status']=='extracted' for r in result)


def test_supplier_and_buyer_registration_are_separate_xml_fields(tmp_path):
    row=source_row(tmp_path);_,_,voucher=output(tmp_path,row)
    assert voucher.findtext('CMPGSTIN')==SELLER and voucher.findtext('PARTYGSTIN')==BUYER
    assert voucher.findtext('CMPGSTSTATE')=='Maharashtra'
    assert voucher.findtext('STATENAME')=='Maharashtra'


def exercise_workflow_review_dialog(root):
    from tkinter import ttk
    from Workflow_Review_Dialog import open_workflow_review
    from Common_Rules.workflow_validation import issue
    from BillSync_Theme import descendants
    callbacks=[];previous=root.grab_current()
    review=WorkflowReviewRequired([issue('INV-1','Buyer GSTIN','Invoice GSTIN','Tally GSTIN','Identity differs')],'exact-output-token','Company')
    top=open_workflow_review(root,review,callbacks.append);root.update()
    button=next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Import to Tally anyway')
    assert 'disabled' in button.state()
    checkbox=next(w for w in descendants(top) if isinstance(w,ttk.Checkbutton));checkbox.invoke();root.update()
    assert 'disabled' not in button.state();button.invoke();root.update()
    assert callbacks==[True] and not top.winfo_exists() and root.grab_current()==previous
    review=WorkflowReviewRequired([issue('INV-1','Invoice date','','','Missing date',True)],'blocking','Company')
    top=open_workflow_review(root,review,callbacks.append);root.update()
    button=next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Import to Tally anyway')
    assert button.winfo_rooty()+button.winfo_height()<root.winfo_screenheight()-30
    next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Cancel import').invoke();root.update()
    assert callbacks==[True,False] and root.grab_current()==previous
    original_scale=root.tk.call('tk','scaling')
    try:
        for scale in (1.0,1.333,1.667,2.0):
            root.tk.call('tk','scaling',scale)
            top=open_workflow_review(root,review,lambda _:None);root.update()
            for widget in descendants(top):
                if isinstance(widget,ttk.Button):
                    assert widget.winfo_ismapped()
                    assert widget.winfo_rooty()+widget.winfo_height()<=top.winfo_rooty()+top.winfo_height()
                    assert widget.winfo_rootx()+widget.winfo_width()<=top.winfo_rootx()+top.winfo_width()
            top.destroy();root.update()
    finally:root.tk.call('tk','scaling',original_scale)



def test_company_registration_lookup_accepts_native_utf16_and_system_control_references():
    from Common_Rules.workflow_validation import company_facts
    response=('<?xml version="1.0" encoding="UTF-16"?><ENVELOPE><COMPANY NAME="Company"><GSTIN>'+SELLER+'</GSTIN><STATENAME>Maharashtra</STATENAME><GSTREGISTRATIONDETAILS.LIST><NAME>&#4; Primary</NAME></GSTREGISTRATIONDETAILS.LIST></COMPANY></ENVELOPE>').encode('utf-16')
    facts=company_facts('Company',lambda _:response)
    assert facts['gstins']==[SELLER] and facts['states']==['Maharashtra']


def exercise_import_review_roundtrip(root,app,monkeypatch,mode='import'):
    """Exercise the real import worker -> Tk review -> acknowledgement -> dispatch."""
    import tempfile
    from tkinter import ttk
    import Invoice_Desktop
    from Common_Rules import tally_import
    from BillSync_Theme import descendants
    previous_root=app.root;previous_busy=app.busy
    original_send=tally_import.send_plan
    with tempfile.TemporaryDirectory(prefix='workflow-ui-roundtrip-') as temp:
        storage=Path(temp);row=source_row(storage);row['invoice']['buyer_gstin']='27INVALID'
        folder,_,_=output(storage,row);transport,writes,reads=server();notifications=[]
        monkeypatch.setattr(tally_import,'post_xml',lambda payload,**kwargs:transport(payload))
        monkeypatch.setattr(tally_import,'send_plan',lambda plan,company,**kwargs:original_send(plan,company,transport=transport,**kwargs))
        monkeypatch.setattr(Invoice_Desktop.messagebox,'showinfo',lambda *args,**kwargs:notifications.append(args))
        monkeypatch.setattr(app,'selected',lambda:row)
        monkeypatch.setattr(app,'records',[row])
        edits=[]
        if mode=='edit':monkeypatch.setattr(app,'review',lambda:edits.append((app.busy,app.selected())))
        if mode in ('cancel','edit','partial'):
            original_groups=tally_import.client_import_groups
            def two_groups(*args):
                groups=original_groups(*args)
                return groups+[{**groups[0],'label':'Second seller — must not be reviewed after cancellation'}]
            monkeypatch.setattr(tally_import,'client_import_groups',two_groups)
        app.root=storage;app.busy=False
        try:
            app.import_tally()
            deadline=time.monotonic()+5;dialog=None
            while time.monotonic()<deadline:
                root.update();time.sleep(.01)
                dialog=next((w for w in root.winfo_children() if w.winfo_class()=='Toplevel' and w.title()=='Import existing XML to Tally'),None)
                if dialog:
                    pickers=[w for w in descendants(dialog) if isinstance(w,ttk.Combobox)]
                    if pickers and 'Company' in pickers[0].cget('values'):break
            assert dialog is not None and pickers
            for picker in pickers:picker.set('Company')
            next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Import ALL: Units + Masters + Vouchers').invoke()
            deadline=time.monotonic()+5;review=None
            while time.monotonic()<deadline:
                root.update();time.sleep(.01)
                review=next((w for w in descendants(dialog) if w.winfo_class()=='Toplevel' and w.title()=='Invoice workflow review'),None)
                if review:break
            assert review is not None and not writes
            import Workflow_Review_Dialog
            opened=[]
            monkeypatch.setattr(Workflow_Review_Dialog,'open_source_document',lambda issue:opened.append(issue['read_path']))
            next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Open source PDF / image').invoke()
            assert opened==[str(Path(row['path']).resolve())]
            if mode=='partial':
                next(w for w in descendants(review) if isinstance(w,ttk.Checkbutton)).invoke()
                next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Import to Tally anyway').invoke()
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    root.update();time.sleep(.01)
                    review=next((w for w in descendants(dialog) if w.winfo_class()=='Toplevel' and w.title()=='Invoice workflow review'),None)
                    if review:break
                assert review is not None and len(writes)==3
            if mode in ('cancel','edit','partial'):
                if mode in ('cancel','partial'):review.tk.call(review.protocol('WM_DELETE_WINDOW'))
                else:next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Edit invoice').invoke()
                deadline=time.monotonic()+5
                receipt_path=Path(row['output_path'])/'Last_Tally_Import.json'
                while time.monotonic()<deadline:
                    root.update();time.sleep(.01)
                    if receipt_path.exists() and (edits if mode=='edit' else any('Import cancelled.' in str(w.cget('text')) for w in descendants(dialog) if isinstance(w,ttk.Label))):break
                assert len(writes)==(3 if mode=='partial' else 0) and not notifications
                assert reads.count('BillSyncWorkflowCompany')==(3 if mode=='partial' else 1)
                receipt=json.loads(receipt_path.read_text())
                assert receipt['cancelled'] and len(receipt['results'])==(4 if mode=='partial' else 1)
                assert receipt['results'][-1]['status']=='cancelled'
                if mode=='edit':assert edits==[(False,row)] and not app.busy
                else:
                    if mode=='partial':assert any('Earlier groups may have been sent' in str(w.cget('text')) for w in descendants(dialog) if isinstance(w,ttk.Label))
                    assert not any(w.winfo_class()=='Toplevel' and w.title()=='Invoice workflow review' for w in descendants(dialog))
                    next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Close').invoke()
                return
            next(w for w in descendants(review) if isinstance(w,ttk.Checkbutton)).invoke()
            next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Import to Tally anyway').invoke()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and not notifications:root.update();time.sleep(.01)
            assert notifications and len(writes)==3
            assert reads.count('BillSyncWorkflowCompany')==2
            receipt=json.loads((folder/'Last_Tally_Import.json').read_text())
            assert receipt['expected_vouchers']==1 and len(receipt['results'])==3
            assert (folder/'Workflow_Review_Decisions.json').exists()
            next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Close').invoke();root.update()
            assert not app.busy
        finally:
            if dialog is not None and dialog.winfo_exists():dialog.destroy()
            app.root=previous_root;app.busy=previous_busy


def test_missing_number_keeps_exact_source_link_and_integrity_cannot_be_overridden(tmp_path):
    row=source_row(tmp_path);row['invoice']['number']=''
    folder,plan,_=output(tmp_path,row);transport,writes,_=server()
    with pytest.raises(WorkflowReviewRequired) as caught:require_plan(plan,'Company',transport)
    missing=next(p for p in caught.value.issues if p['field']=='Invoice number')
    assert missing['source']==str(Path(row['path']).resolve()) and missing['read_sha256']==row['digest']
    from Common_Rules.workflow_validation import cannot_override
    assert not cannot_override(missing)
    approved=acknowledge(plan,caught.value,folder)
    Path(row['path']).write_bytes(b'Changed original')
    with pytest.raises(WorkflowReviewRequired) as stale:require_plan(approved,'Company',transport)
    assert any(cannot_override(p) for p in stale.value.issues)
    with pytest.raises(ValueError,match='cannot bypass'):acknowledge(approved,stale.value,folder)
    assert not writes


def test_source_document_opener_uses_exact_path_and_rejects_outside_root(tmp_path,monkeypatch):
    import Workflow_Review_Dialog as ui
    folder=tmp_path/'invoices';folder.mkdir();source=folder/'actual invoice.pdf';source.write_bytes(b'offline')
    opened=[]
    if ui.os.name=='nt':monkeypatch.setattr(ui.os,'startfile',lambda p:opened.append(p))
    else:monkeypatch.setattr(ui.subprocess,'Popen',lambda args:opened.append(args[-1]))
    ui.open_source_document({'source':str(source),'root':str(folder)})
    assert opened==[str(source)]
    with pytest.raises(ValueError):ui.open_source_document({'source':str(source),'root':str(folder/'other')})
    source.unlink()
    with pytest.raises(ValueError):ui.open_source_document({'source':str(source),'root':str(folder)})


def test_import_review_change_manifest_preserves_baseline_and_installer_payload():
    import runpy,zipfile
    root=Path(__file__).parents[2]
    change=json.loads((root/'Automation/IMPORT_REVIEW_UX_CHANGE.json').read_text())
    package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    with zipfile.ZipFile(root/change['backup']) as archive:
        for name,entry in change['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==entry['baseline_sha256']
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==entry['authorized_sha256']
            if name.startswith('Automation/'):
                assert package['FILES'][name.removeprefix('Automation/')].encode()==(root/name).read_bytes()

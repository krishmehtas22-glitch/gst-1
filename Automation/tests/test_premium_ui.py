"""Presentation changes retain data, inherited commands and explicit consent."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,runpy,zipfile


def after_boxed_ui(root,name,expected):
    for filename in ('BOXED_UI_CHANGE.json','UNIFIED_UI_CHANGE.json','INVOICE_NUMBER_GUARD_CHANGE.json','LOCAL_GEMMA_CHANGE.json','AI_WORKFLOW_CHANGE.json','IMPORT_REVIEW_UX_CHANGE.json','INVOICE_STRUCTURE_V2_CHANGE.json','OPENROUTER_PROVIDER_CHANGE.json'):
        change=json.loads((root/'Automation'/filename).read_text())
        if name in change['files']:
            entry=change['files'][name];assert entry['baseline_sha256']==expected
            with zipfile.ZipFile(root/change['backup']) as backup:assert hashlib.sha256(backup.read(name)).hexdigest()==expected
            expected=entry['authorized_sha256']
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected


def test_entire_processing_engine_is_identical_to_pre_redesign_baseline():
    root=Path(__file__).parents[2];change=json.loads((root/'Automation/PREMIUM_UI_CHANGE.json').read_text())
    for name,expected in change['processing_sha256'].items():after_boxed_ui(root,name,expected)


def test_presentation_backup_and_installer_include_exact_new_files():
    root=Path(__file__).parents[2];change=json.loads((root/'Automation/PREMIUM_UI_CHANGE.json').read_text())
    with zipfile.ZipFile(root/change['backup']) as backup:
        for name,entry in change['files'].items():
            assert hashlib.sha256(backup.read(name)).hexdigest()==entry['baseline_sha256']
            after_boxed_ui(root,name,entry['authorized_sha256'])
    package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    for name,expected in change['new_files'].items():
        after_boxed_ui(root,name,expected)
        assert package['FILES'][name.removeprefix('Automation/')].encode()==(root/name).read_bytes()


def exercise_premium_ui(root,app,tmp_path,monkeypatch):
    import tkinter as tk
    from tkinter import ttk,messagebox
    import Invoice_Desktop,shutil
    from Common_Rules.desktop import inspect_sources
    from BillSync_Theme import descendants
    folder=tmp_path/'Visual';folder.mkdir()
    source=next((Path(__file__).parent/'fixtures/client23').glob('*.pdf'));shutil.copy2(source,folder/source.name)
    app.refresh_clients();calls=[]
    monkeypatch.setattr(app,'start',lambda:calls.append('list'))
    monkeypatch.setattr(app,'reset',lambda:None)
    app.manage_clients();root.update()
    top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Clients')
    top.client_search.set('Visual');root.update();ids=top.client_table.get_children()
    assert len(ids)==1 and top.client_table.item(ids[0],'values')[0]=='Visual'
    top.client_table.selection_set(ids[0]);next(w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')=='Open workspace').invoke();root.update()
    assert calls==['list'] and app.client_scope.get()=='Folder: Visual'
    preferences=(app.demo.get(),app.auto_units.get(),app.auto.get())
    app.settings();root.update()
    settings=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Settings')
    checks=[w for w in descendants(settings) if isinstance(w,ttk.Checkbutton)]
    assert {str(w.cget('variable')) for w in checks}=={str(app.demo),str(app.auto_units),str(app.auto)}
    assert (app.demo.get(),app.auto_units.get(),app.auto.get())==preferences
    settings_tabs=next(w for w in descendants(settings) if isinstance(w,ttk.Notebook))
    for index in range(2):settings_tabs.select(index);root.update()
    settings.destroy()
    row=inspect_sources(tmp_path,['Visual'],True)[0];baseline=deepcopy(row['invoice'])
    app.records=[row];app.table.delete(*app.table.get_children());app.table.insert('','end',iid='0',values=('Visual',baseline.get('number')));app.table.selection_set('0');app.table.focus('0')
    # Single-click destinations share the visual treatment and remain read-only.
    def popup(title):
        root.update()
        top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()==title)
        assert any(isinstance(w,ttk.Frame) and w.cget('style')=='Header.TFrame' for w in descendants(top))
        return top
    app.show_dashboard();popup('Workspace overview').destroy()
    app.activity_history();history=popup('Activity history and selected invoice details')
    assert all(w.cget('state')=='disabled' for w in descendants(history) if isinstance(w,tk.Text));history.destroy()
    row['tally_master_matching']={'company':'Offline UI test','party':None,'items':[{'index':0,'stock':None,'unit':None}]}
    app.view_master_matches();popup('Tally master assignments').destroy();row.pop('tally_master_matching')
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        folder_xml=Path(directory);contents={name:'<ENVELOPE>'+name+'</ENVELOPE>' for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}
        for name,body in contents.items():(folder_xml/name).write_text(body)
        row['output_path']=str(folder_xml);app.view_xml();xml=popup('Prepared XML — read only')
        tabs=next(w for w in descendants(xml) if isinstance(w,ttk.Notebook))
        for i,(name,body) in enumerate(contents.items()):
            tabs.select(i);root.update();assert tabs.tab(i,'text')==name
            pane=xml.nametowidget(tabs.tabs()[i]);text=next(w for w in descendants(pane) if isinstance(w,tk.Text))
            assert text.cget('state')=='disabled' and text.get('1.0','end').strip()==body
        xml.destroy();row.pop('output_path')
    app.supplier_layout();supplier=popup('Save supplier layout')
    supplier.tk.call(supplier.protocol('WM_DELETE_WINDOW'));root.update()
    monkeypatch.setattr(app,'review',Invoice_Desktop.InvoiceApp.review.__get__(app))
    captures=[];monkeypatch.setattr(app,'save_manual_edits',lambda record,edited:captures.append((record,edited)))
    monkeypatch.setattr(root,'winfo_screenheight',lambda:768)
    app.review();root.update()
    review=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Review invoice against the original PDF')
    save_button=next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Save changes to XML')
    assert save_button.winfo_rooty()+save_button.winfo_height()<=review.winfo_rooty()+review.winfo_height()
    assert len(review.review_summary_cards)==3
    assert set(review.review_fields)==set(Invoice_Desktop.FIELDS)
    assert len(review.review_tabs.tabs())==4 and review.review_fields['number'].winfo_viewable()
    assert not review.review_fields['seller_name'].winfo_viewable()
    number=review.review_fields['number'];number.delete(0,'end');number.insert(0,'MANUAL-2048')
    review.review_tabs.select(1);root.update()
    assert review.review_fields['seller_name'].winfo_viewable() and not number.winfo_viewable()
    buyer=review.review_fields['buyer_name'];buyer.delete(0,'end');buyer.insert(0,'Reviewed buyer')
    assert root.getvar(next(w for w in descendants(review.review_summary_cards[1]) if isinstance(w,tk.Label) and w.cget('textvariable')).cget('textvariable'))=='Reviewed buyer'
    review.review_tabs.select(2);root.update()
    widgets=list(descendants(review));item_frames=[w for w in widgets if isinstance(w,ttk.LabelFrame) and getattr(w,'_presentation_copy',False)]
    count=len(item_frames);assert count==len(baseline['items'])
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Add item').invoke();root.update()
    added=[w for w in descendants(review) if isinstance(w,ttk.LabelFrame) and getattr(w,'_presentation_copy',False)]
    assert len(added)==count+1 and all(getattr(w,'_billsync_item',False) for w in added)
    next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Remove last item').invoke();root.update()
    review.review_tabs.select(3);root.update();assert review.review_fields['exchange_rate'].winfo_viewable()
    next(w for w in descendants(review) if isinstance(w,ttk.Button) and w.cget('text')=='Save changes to XML').invoke();root.update()
    assert len(captures)==1 and not review.winfo_exists()
    edited=captures[0][1];assert edited['number']=='MANUAL-2048' and edited['buyer_name']=='Reviewed buyer'
    for field in Invoice_Desktop.FIELDS:
        if field not in ('number','buyer_name'):assert edited[field]==str(baseline.get(field,'0' if field=='round_off' else '')).strip()
    assert len(edited['items'])==count
    for before,after in zip(baseline['items'],edited['items']):
        for field,value in before.items():assert after[field]==(str(value).strip() if field in Invoice_Desktop.ITEM_FIELDS else value)
    # Closing a styled confirmation is cancellation, never implicit AI approval.
    def click(text):
        for top in root.winfo_children():
            if isinstance(top,tk.Toplevel):
                button=next((w for w in descendants(top) if isinstance(w,ttk.Button) and w.cget('text')==text),None)
                if button:button.invoke();return
        root.after(10,lambda:click(text))
    root.after(20,lambda:click('Cancel'))
    assert messagebox._show('Consent test','No AI should run.',_type='yesno',parent=root)=='no'
    root.after(20,lambda:click('Continue'))
    assert messagebox._show('Consent test','Explicit confirmation test.',_type='yesno',parent=root)=='yes'
    assert calls==['list']

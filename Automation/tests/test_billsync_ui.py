"""Presentation hooks must retain the exact working processing implementation."""
import hashlib,json,os,queue,shutil,time
from pathlib import Path
from copy import deepcopy

import pytest

import Invoice_Desktop
from BillSync_UI import BillSyncApp


@pytest.mark.parametrize('name',['import_tally','analyse_selected','analyse_one_pdf','read_gemini_batch','review','save_manual_edits','revalidate','start','stop_ai'])
def test_working_actions_are_inherited_without_replacement(name):
    assert getattr(BillSyncApp,name) is getattr(Invoice_Desktop.InvoiceApp,name)


def test_engine_matches_backup_except_the_authorized_export_metadata_change():
    import zipfile
    root=Path(__file__).parents[2]
    with zipfile.ZipFile(root/'Backups/Reader_Before_BillSync_UI.zip') as backup:
        manifest=json.loads(backup.read('BACKUP_MANIFEST.json'))
        for name,digest in manifest['files'].items():
            if name.startswith('Automation/Common_Rules/') or name=='Automation/Invoice_Desktop.py':
                matching=json.loads((root/'Automation/TALLY_MASTER_MATCHING_CHANGE.json').read_text())['files']
                fx=json.loads((root/'Automation/FOREIGN_CURRENCY_CHANGE.json').read_text())['files']
                actual=hashlib.sha256((root/name).read_bytes()).hexdigest()
                quantities=json.loads((root/'Automation/QUANTITY_PRECISION_CHANGE.json').read_text())['files']
                duplicates=json.loads((root/'Automation/DUPLICATE_WARNING_CHANGE.json').read_text())['files']
                if name in duplicates:
                    with zipfile.ZipFile(root/'Backups/Before_Duplicate_Warning.zip') as before:
                        assert hashlib.sha256(before.read(name)).hexdigest()==duplicates[name]['baseline_sha256']
                    assert actual==duplicates[name]['authorized_sha256']
                    assert duplicates[name]['baseline_sha256']==quantities[name]['authorized_sha256']
                    continue
                if name in quantities:
                    with zipfile.ZipFile(root/'Backups/Before_Quantity_Precision.zip') as before:
                        assert hashlib.sha256(before.read(name)).hexdigest()==quantities[name]['baseline_sha256']
                    assert actual==quantities[name]['authorized_sha256']
                    assert quantities[name]['baseline_sha256']==fx[name]['authorized_sha256']
                    continue
                if name in fx:
                    with zipfile.ZipFile(root/'Backups/Before_Foreign_Currency.zip') as before:
                        assert hashlib.sha256(before.read(name)).hexdigest()==fx[name]['baseline_sha256']
                    assert actual==fx[name]['authorized_sha256']
                    if name in matching:assert fx[name]['baseline_sha256']==matching[name]['authorized_sha256']
                    else:assert fx[name]['baseline_sha256']==digest
                    continue
                if name in matching:
                    with zipfile.ZipFile(root/'Backups/Before_Tally_Master_Matching.zip') as previous:
                        assert hashlib.sha256(previous.read(name)).hexdigest()==matching[name]['baseline_sha256']
                    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==matching[name]['authorized_sha256']
                    if name=='Automation/Common_Rules/tally_review_export.py':
                        earlier=json.loads((root/'Automation/EXPORT_COUNTRY_REFUND_CHANGE.json').read_text())
                        assert earlier['baseline_sha256']==digest and matching[name]['baseline_sha256']==earlier['authorized_sha256']
                    else:assert matching[name]['baseline_sha256']==digest
                elif name=='Automation/Common_Rules/tally_review_export.py':
                    change=json.loads((root/'Automation/EXPORT_COUNTRY_REFUND_CHANGE.json').read_text())
                    assert change['baseline_sha256']==digest
                    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==change['authorized_sha256']
                else:assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name


@pytest.mark.skipif(not os.environ.get('DISPLAY') and os.name!='nt',reason='Requires a desktop display')
def test_real_window_upload_refresh_filter_and_single_pdf_are_safe(tmp_path,monkeypatch):
    from tkinterdnd2 import TkinterDnD
    from Common_Rules import groq_reader,desktop_ai
    root=TkinterDnD.Tk();root.withdraw();errors=[]
    root.report_callback_exception=lambda *a:errors.append(str(a[1]))
    app=BillSyncApp(root,data_root=tmp_path)
    from Document_Upload import client_folder
    client_folder(tmp_path,'Client',create=True)
    fixture=sorted((Path(__file__).parent/'fixtures/client23').glob('*.pdf'))[:2]
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a,**kw:pytest.fail('Intake/listing must not call AI'))
    try:
        startup=time.monotonic()+5
        while time.monotonic()<startup:
            root.update();time.sleep(.02)
            if not app.busy and app.records==[]:break
        assert not app.busy
        app.client_scope.set('Folder: Client');app.refresh_clients()
        assert app.client_display.get()=='Client'
        app.upload_paths(fixture)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            root.update();time.sleep(.02)
            if len(app.records)==2 and not app.busy:break
        assert len(app.records)==2 and not app.busy and app.drop_supported and not errors
        assert app.summary_accounting.get() is False
        app.table.selection_set('0');app.table.focus('0');app.details()
        calls=[]
        monkeypatch.setattr(Invoice_Desktop.messagebox,'askyesno',lambda *a,**kw:False)
        monkeypatch.setattr(desktop_ai,'analyse_paths',lambda *a,**kw:calls.append(a))
        from BillSync_Controls import ActionButton
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons={widget.text:widget for widget in descendants(root) if isinstance(widget,ActionButton)}
        assert buttons['Import to Tally'].command.__func__ is Invoice_Desktop.InvoiceApp.import_tally
        assert 'Read Tally masters' in buttons and 'New client' in buttons
        buttons['Process this invoice'].invoke();assert not calls
        root.deiconify();root.geometry('1366x900');root.update()
        assert not hasattr(app,'selected_panel')
        assert app.processing_group.winfo_rooty()==app.tally_group.winfo_rooty()
        assert app.table.winfo_width()>app.drop.winfo_width()
        assert app.drop.winfo_height()>=170
        for label in app.count_labels:
            panel=label.master.master;card=panel.master
            assert panel.winfo_y()+panel.winfo_height()<card.winfo_height()-2
            assert panel.winfo_x()>2
        app.process_menu.invoke(1);assert not calls
        assert app.table.cget('displaycolumns')==('invoice','client','seller','export_country','quantity_unit','total','refund_estimate','status')
        assert [app.process_menu.entrycget(i,'label') for i in range(3)]==['Process selected invoices','Process all client invoices','Process this invoice']
        assert app.process_menu.entrycget(1,'command')
        app.table.focus_force();root.update()
        review=[];monkeypatch.setattr(app,'review',lambda:review.append('opened'))
        app.table.event_generate('<Return>');root.update()
        assert review==['opened']
        app.search.set('NO MATCH');root.update()
        assert not app.table.get_children() and not app.table.selection()
        assert len(app.records)==2
        app.start()
        deadline=time.monotonic()+5
        while app.busy and time.monotonic()<deadline:
            root.update();time.sleep(.02)
        assert not errors
        assert not app.busy and not app.table.get_children()
        app.search.set('');root.update()
        assert len(app.table.get_children())==2
        assert not list(tmp_path.rglob('*.xml'))
        from test_tally_master_snapshot import exercise_snapshot_dialog_in_existing_app
        exercise_snapshot_dialog_in_existing_app(root,tmp_path,monkeypatch)
        from test_export_country_refund import exercise_refund_dialog_in_existing_app
        exercise_refund_dialog_in_existing_app(root,app,tmp_path)
        from test_foreign_currency import exercise_currency_dialog
        exercise_currency_dialog(root,app,tmp_path,monkeypatch)
        from test_duplicate_invoice_warning import exercise_duplicate_warning_ui
        exercise_duplicate_warning_ui(root,app,tmp_path)
        assert not errors and not list(tmp_path.rglob('*.xml'))
    finally:root.destroy()

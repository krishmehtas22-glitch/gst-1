"""Exercise real desktop navigation without invoking AI or Tally services."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import argparse,json,sys,time,tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tkinterdnd2 import TkinterDnD
from BillSync_UI import BillSyncApp
from Common_Rules import groq_reader,ai_first,tally_import
from test_app_contracts import invoice_pdf,record


def run():
    checks=[];errors=[];messages=[]
    def forbidden(*args,**kwargs):raise AssertionError('Navigation/intake must not call AI or Tally')
    with TemporaryDirectory(prefix='billsync-ui-audit-') as directory:
        folder=Path(directory);window=TkinterDnD.Tk();window.withdraw()
        window.report_callback_exception=lambda *args:errors.append(str(args[1]))
        with patch('socket.create_connection',forbidden),patch('socket.socket.connect',forbidden),patch.object(groq_reader,'request_invoice',forbidden),patch.object(ai_first,'run_ai_first',forbidden),patch.object(tally_import,'post_xml',forbidden),patch('tkinter.messagebox.showinfo',lambda *args,**kwargs:messages.append(args)),patch('tkinter.messagebox.showerror',lambda *args,**kwargs:messages.append(args)):
            try:
                storage=folder/'app';storage.mkdir()
                app=BillSyncApp(window,data_root=storage)
                def wait():
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        window.update();time.sleep(.03)
                        if not app.busy:return
                    raise AssertionError('Desktop worker did not finish')
                window.update();wait();assert not messages;checks.append('startup lists only')
                with patch('tkinter.simpledialog.askstring',return_value='Audit Client'):app.add_client();wait()
                assert app.client_display.get()=='Audit Client';checks.append('new client and selection')
                source=folder/'invoice.pdf';source.write_bytes(invoice_pdf(record(folder)['invoice'],'stacked'))
                app.upload_paths([source]);wait();assert len(app.records)==1;checks.append('real PDF intake')
                app.table.selection_set('0');app.table.focus('0');window.update()
                for action,title in [(app.show_dashboard,'Dashboard'),(app.manage_clients,'Clients'),(app.settings,'Settings'),(app.activity_history,'Activity history and selected invoice details')]:
                    action();window.update()
                    top=next(w for w in window.winfo_children() if isinstance(w,tk.Toplevel) and w.title()==title)
                    assert top.winfo_exists();top.destroy();checks.append(title)
                app.view_xml();assert messages;checks.append('view XML before generation is explanatory')
                app.view_master_matches();checks.append('view assignments before matching is explanatory')
                for status in ('Awaiting processing','Needs review','XML prepared','All statuses'):
                    app.filter_status.set(status);window.update()
                app.search.set('not-a-real-invoice');window.update();assert not app.table.get_children()
                app.search.set('');window.update();assert len(app.table.get_children())==1;checks.append('search and status filters')
                window.deiconify()
                for size in ('1100x650','1366x768','1600x1000'):
                    window.geometry(size);window.update();assert app.table.winfo_width()>0 and app.drop.winfo_width()>0
                    checks.append('renders at '+size)
                assert not errors and not list((folder/'app').rglob('*.xml'))
                checks.append('no callbacks failed and no XML generated during navigation')
            finally:window.destroy()
    return {'passed':True,'checks':checks,'callback_errors':errors,'live_ai_requests':0,'tally_imports':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run();Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(str(len(result['checks']))+' desktop functional checks passed; no AI/Tally operations.')

"""Windows executable entry; supports an offline frozen-package smoke check."""
from pathlib import Path
import json
import sys
import traceback


def self_test(destination):
    import Invoice_Desktop
    from Common_Rules.desktop import PARSER_REVISION
    from Common_Rules.runtime_paths import default_data_root
    from Common_Rules.ai_providers import ACTIVE_PROVIDERS,reader
    from Common_Rules.tally_import import client_import_groups
    import pypdf,openpyxl,pypdfium2,onnxruntime,rapidocr
    from rapidocr import RapidOCR
    onnxruntime.disable_telemetry_events()
    # Initializing the CPU OCR models catches missing bundled data/DLLs.
    engine=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':2,
                          'EngineConfig.onnxruntime.inter_op_num_threads':1,
                          'Global.log_level':'error'})
    for provider in ACTIVE_PROVIDERS:reader(provider)
    import tempfile
    from tkinterdnd2 import TkinterDnD
    from BillSync_UI import BillSyncApp,UI_VERSION
    from Invoice_Document_Editor import open_document_editor
    from Common_Rules.invoice_document import VERSION,EXTRACTION_SCHEMA,validate
    schema_file=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'schemas'/'invoice-v2.schema.json'
    schema=json.loads(schema_file.read_text(encoding='utf-8'));schema.pop('$schema',None)
    if schema!=EXTRACTION_SCHEMA:raise RuntimeError('Bundled invoice schema does not match the reader')
    validate({'schema_version':VERSION,'invoices':[{'items':[]}]},EXTRACTION_SCHEMA)
    callbacks=[]
    window=TkinterDnD.Tk();window.withdraw()
    window.report_callback_exception=lambda *args:callbacks.append(str(args[1]))
    with tempfile.TemporaryDirectory() as directory:
        app=BillSyncApp(window,data_root=Path(directory))
        window.update()
        ui_initialized=app.drop_supported
        window.destroy()
    if callbacks or not ui_initialized:raise RuntimeError('BillSync UI self-test failed: '+str(callbacks))
    result={'invoice_structure_version':VERSION,'document_editor_available':callable(open_document_editor),'schema_contract_checked':True,'ui_version':UI_VERSION,'ui_initialized':ui_initialized,'drag_drop_available':app.drop_supported,'version':Invoice_Desktop.APP_VERSION,'frozen':bool(getattr(sys,'frozen',False)),
            'data_root':str(default_data_root(Invoice_Desktop.__file__)),
            'parser_revision':PARSER_REVISION,'ocr_initialized':engine is not None,
            'providers':list(ACTIVE_PROVIDERS)}
    Path(destination).write_text(json.dumps(result,indent=2),encoding='utf-8')


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        self_test(sys.argv[2]);return
    from BillSync_UI import launch
    data_root=None
    if len(sys.argv)==3 and sys.argv[1]=='--data-root':
        data_root=Path(sys.argv[2]).resolve()
        if not data_root.is_dir():raise ValueError('Invoice storage folder does not exist')
    launch(data_root=data_root)


if __name__=='__main__':
    try:main()
    except Exception:
        from Common_Rules.runtime_paths import default_data_root
        log=default_data_root(__file__)/'InvoiceReader_Startup_Error.log'
        try:log.write_text(traceback.format_exc(),encoding='utf-8')
        except OSError:pass
        if '--self-test' not in sys.argv:
            import tkinter as tk
            from tkinter import messagebox
            window=tk.Tk();window.withdraw()
            messagebox.showerror('Invoice Reader startup','The app could not start. Details: '+str(log))
            window.destroy()
        raise SystemExit(1)

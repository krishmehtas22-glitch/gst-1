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
    result={'version':Invoice_Desktop.APP_VERSION,'frozen':bool(getattr(sys,'frozen',False)),
            'data_root':str(default_data_root(Invoice_Desktop.__file__)),
            'parser_revision':PARSER_REVISION,'ocr_initialized':engine is not None,
            'providers':list(ACTIVE_PROVIDERS)}
    Path(destination).write_text(json.dumps(result,indent=2),encoding='utf-8')


def main():
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        self_test(sys.argv[2]);return
    import tkinter as tk
    from Invoice_Desktop import InvoiceApp
    window=tk.Tk();InvoiceApp(window);window.mainloop()


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

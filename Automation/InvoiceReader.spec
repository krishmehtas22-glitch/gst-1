# Windows build only. Includes application modules, source revision data and OCR.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all,collect_submodules

root=Path(SPECPATH)
datas=[(str(p),'Common_Rules') for p in sorted((root/'Common_Rules').glob('*.py'))]
binaries=[]
hiddenimports=collect_submodules('Common_Rules')
for package in ('rapidocr','onnxruntime','pypdfium2','pypdfium2_raw','tkinterdnd2'):
    package_data,package_binaries,package_imports=collect_all(package)
    datas+=package_data;binaries+=package_binaries;hiddenimports+=package_imports

a=Analysis([str(root/'Windows_Entry.py')],pathex=[str(root)],binaries=binaries,
           datas=datas,hiddenimports=hiddenimports,hookspath=[],hooksconfig={},
           runtime_hooks=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='InvoiceReader',debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        disable_windowed_traceback=False,argv_emulation=False,target_arch=None,
        codesign_identity=None,entitlements_file=None)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='InvoiceReader')

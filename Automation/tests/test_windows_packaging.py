"""Packaging must preserve the working engine and keep data out of the bundle."""
from pathlib import Path
import ast
import hashlib
import sys
from Common_Rules.runtime_paths import default_data_root


def test_python_mode_keeps_existing_invoice_root(tmp_path,monkeypatch):
    monkeypatch.delattr(sys,'frozen',raising=False)
    assert default_data_root(tmp_path/'Invoice_Desktop.py')==tmp_path


def test_exe_mode_uses_executable_folder_not_temporary_bundle(tmp_path,monkeypatch):
    executable=tmp_path/'Existing invoices'/'InvoiceReader.exe'
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(executable))
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path/'temporary-bundle'),raising=False)
    assert default_data_root(tmp_path/'temporary-bundle'/'Invoice_Desktop.py')==executable.parent


def test_parser_revision_files_are_preserved_and_spec_includes_them():
    from Common_Rules.desktop import PARSER_REVISION
    root=Path(__file__).parents[1]
    names=('extraction.py','document_structure.py','paired_layout.py','section_layout.py','tabular_layout.py','flat_layout.py','goods_layout.py','party_evidence.py','unit_catalog.py','unit_inference.py','tax_treatment.py','country_catalog.py','supplier_layouts.py','ocr.py')
    expected=hashlib.sha256(b''.join((root/'Common_Rules'/name).read_bytes() for name in names)).hexdigest()
    assert PARSER_REVISION==expected
    specification=(root/'InvoiceReader.spec').read_text()
    assert "(root/'Common_Rules').glob('*.py')" in specification
    assert "collect_submodules('Common_Rules')" in specification
    for package in ('rapidocr','onnxruntime','pypdfium2','pypdfium2_raw'):assert package in specification


def test_windows_entry_is_offline_and_never_embeds_keys():
    path=Path(__file__).parents[1]/'Windows_Entry.py'
    tree=ast.parse(path.read_text())
    smoke=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='self_test')
    calls=[ast.unparse(n.func) for n in ast.walk(smoke) if isinstance(n,ast.Call)]
    assert 'RapidOCR' in calls
    assert not any('extract_selected' in call or 'api_json' in call for call in calls)

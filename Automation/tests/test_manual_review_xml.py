"""Desktop human corrections reach all dependent XML without any AI request."""
from copy import deepcopy
from pathlib import Path
import ast
import queue
import xml.etree.ElementTree as ET

import pytest

from test_desktop_selected_xml import sources
from Common_Rules.desktop_ai import selected_to_xml


class Value:
    def __init__(self,value):self.value=value
    def get(self):return self.value


class ImmediateThread:
    def __init__(self,target,**kwargs):self.target=target
    def start(self):self.target()


def test_desktop_manual_save_updates_units_masters_vouchers_without_ai(tmp_path,monkeypatch):
    import Invoice_Desktop as gui
    from Common_Rules import ai_first, groq_reader, gemini_reader, github_models_reader, openrouter_reader
    rows=sources(tmp_path)
    _,rows,_=selected_to_xml(tmp_path,rows[0],'Groq',True,True,False)
    caches={p:p.read_bytes() for p in (tmp_path/'.invoice_app').rglob('*.json') if 'groq' in str(p)}
    assert caches
    other={'client':'Other','path':str(tmp_path/'Other/untouched.pdf'),'invoice':{},'errors':[]}
    def forbidden(*a,**kw):pytest.fail('Manual save must not request AI')
    monkeypatch.setattr(ai_first,'run_ai_first',forbidden)
    for reader in (groq_reader,gemini_reader,github_models_reader,openrouter_reader):
        monkeypatch.setattr(reader,'request_invoice',forbidden)
    monkeypatch.setattr(gui.threading,'Thread',ImmediateThread)
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.root=tmp_path;app.busy=False;app.records=rows+[other];app.events=queue.Queue()
    app.demo=Value(True);app.auto_units=Value(True);app.summary_accounting=Value(False)
    app.client_scope=Value('All clients');app.reset=lambda:None
    edited=deepcopy(rows[0]['invoice'])
    edited['buyer_address']='Manually corrected buyer address'
    edited['items'][0]['unit']='cm'
    app.save_manual_edits(rows[0],edited)
    kind,updated=app.events.get_nowait()
    assert kind=='ok' and other in updated
    row=next(r for r in updated if r.get('digest')==rows[0]['digest'])
    assert row['invoice']['buyer_address']==edited['buyer_address']
    assert row['invoice']['items'][0]['unit']=='CMS'
    output=Path(row['output_path'])
    units=ET.parse(output/'Units.xml');masters=ET.parse(output/'Masters.xml');sales=ET.parse(output/'Sales_Vouchers.xml')
    assert any(n.findtext('NAME')=='CMS' for n in units.findall('.//UNIT'))
    assert any(n.findtext('BASEUNITS')=='CMS' for n in masters.findall('.//STOCKITEM'))
    voucher=next(v for v in sales.findall('.//VOUCHER') if v.findtext('VOUCHERNUMBER')==edited['number'])
    assert any('Manually corrected buyer address' in (n.text or '') for n in voucher.iter())
    assert any((n.text or '').endswith(' CMS') for n in voucher.findall('.//ACTUALQTY'))
    assert all(p.read_bytes()==raw for p,raw in caches.items())


def test_removed_controls_are_absent_and_double_click_still_opens_editor():
    import Invoice_Desktop as gui
    source=Path(gui.__file__).read_text()
    tree=ast.parse(source)
    init=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    labels=[kw.value.value for n in ast.walk(init) if isinstance(n,ast.Call) for kw in n.keywords
            if kw.arg=='text' and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str)]
    assert not any(any(x in label for x in ('Gemini','OpenRouter','GitHub','Accept / change units','Recover processing lock','Confirm test PDF')) for label in labels)
    assert 'Save changes to XML' in source and "'<Double-1>',lambda event:self.review()" in source
    assert "self.ai_primary=tk.StringVar(value='Groq')" in source


def test_double_click_can_load_queued_pdf_for_manual_entry_without_ai(tmp_path,monkeypatch):
    import Invoice_Desktop as gui
    from Common_Rules import ai_first, groq_reader
    from Common_Rules.invoice_queue import list_sources
    original=sources(tmp_path)[0]
    monkeypatch.setattr(ai_first,'run_ai_first',lambda *a,**kw:pytest.fail('Manual opening must not start AI'))
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a,**kw:pytest.fail('Manual opening must not request AI'))
    app=gui.InvoiceApp.__new__(gui.InvoiceApp)
    app.root=tmp_path;app.demo=Value(True);app.auto_units=Value(True)
    app.records=list_sources(tmp_path)
    row=next(r for r in app.records if r['path']==original['path'])
    assert row['listing_only'] and not row.get('digest')
    manual=app.prepare_manual_review(row)
    assert manual['digest']==original['digest'] and manual['invoice']['items']
    assert not manual.get('listing_only')
    assert not list(tmp_path.rglob('Sales_Vouchers.xml'))

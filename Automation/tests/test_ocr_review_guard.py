"""Local OCR ambiguity evidence is never an automatic name/number correction."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,runpy,zipfile
import pytest
from PIL import Image
from Common_Rules import ocr,groq_reader,extraction

BOX=[[10,10],[160,10],[160,35],[10,35]]
def evidence(primary='Penci1',alternate='Pencil'):
    return [{'page':1,'primary':primary,'confidence':.89,'reason':'possible letter/digit confusion',
             'alternatives':[{'method':'local threshold crop','text':alternate}]}]

@pytest.mark.parametrize('word,score',[('Penci1',.99),('Off1ce',.95),('Pencil',.6),('10.00',.5)])
def test_ambiguous_glyphs_or_low_confidence_are_reviewed(word,score):
    assert ocr.suspect(word,score)

@pytest.mark.parametrize('word',['Pencil','SKU01','AB100','27ABCDE1234F1Z0','2.4877','960910','100.00'])
def test_clear_names_uppercase_codes_and_numbers_are_not_glyph_rewritten(word):
    assert not ocr.suspect(word,.99)


def test_second_read_is_bounded_and_primary_text_is_unchanged():
    rows=[(BOX,'Penci1',.89)]*25;before=deepcopy(rows);calls=[]
    def engine(image):
        calls.append(image.shape)
        return SimpleNamespace(boxes=[BOX],txts=['Pencil'],scores=[.999])
    result=ocr.second_read(Image.new('RGB',(300,100),'white'),rows,engine,0)
    assert rows==before and 'Penci1' in ocr.rows_from_boxes(rows)
    assert len(calls)==4 and len(result)==21 and result[0]['alternatives'][0]['text']=='Pencil'
    assert result[4]['retry_status'].startswith('Local retry limit')
    assert all(height<=512 and width<=4096 for height,width,*_ in calls)


def test_retry_failure_preserves_primary_review_evidence():
    def broken(image):raise RuntimeError('bad crop')
    result=ocr.second_read(Image.new('RGB',(300,100)),[(BOX,'Penci1',.89)],broken,2)
    assert result[0]['page']==3 and result[0]['primary']=='Penci1'
    assert result[0]['alternatives']==[] and result[0]['retry_status']


def test_disagreeing_numbers_are_retained_locally_but_withheld_from_ai():
    def engine(image):return SimpleNamespace(boxes=[BOX],txts=['Pencil 500.00'],scores=[.99])
    result=ocr.second_read(Image.new('RGB',(300,100)),[(BOX,'Penci1 100.00',.8)],engine,0)
    assert result[0]['numeric_conflict'] and '500.00' in result[0]['alternatives'][0]['text']
    hints=ocr.evidence_for_payload(result)
    assert hints[0]['alternatives']==[] and '500.00' not in json.dumps(hints)
    assert 'manual review' in hints[0]['reason']


def test_payload_keeps_primary_adds_separate_uncertain_evidence_and_no_extra_api_fields(monkeypatch):
    text=ocr.OCRText('Penci1 Model1 2.4877 KG 100.00',evidence())
    monkeypatch.setattr(extraction,'text_from_pdf',lambda path:text)
    payload=groq_reader.prepare_invoice_payload({'path':'unused'},'offline-model')
    assert payload['messages'][1]['content'].startswith('INVOICE TEXT\n'+str(text))
    assert 'OCR READING EVIDENCE' in payload['messages'][1]['content']
    assert 'Do not blindly replace' in payload['messages'][0]['content']
    assert payload.ocr_evidence==evidence() and deepcopy(payload).ocr_evidence==evidence()
    assert set(json.loads(json.dumps(payload)))=={'model','temperature','max_completion_tokens','response_format','messages'}
    from Common_Rules.tally_master_matching import augment_payload
    monkeypatch.setattr('Common_Rules.tally_master_matching.shortlist',lambda *a:{})
    assert augment_payload(payload,{},{}).ocr_evidence==evidence()


def test_cache_warning_does_not_change_any_ai_values_or_make_a_request(tmp_path,monkeypatch):
    from Common_Rules.engine import write_json
    row={'digest':'a'*64,'invoice':{'ocr_reading_evidence':evidence()}}
    path=groq_reader.cache_path(tmp_path,row)
    invoice={'number':'INV-1','items':[{'name':'Model1','unit':'PCS','quantity':'2.4877','rate':'100.00'}]}
    write_json(path,{'source_sha256':row['digest'],'revision':groq_reader.REVISION,'model':'offline','review_mode':'tally','invoice':invoice})
    before=path.read_bytes()
    monkeypatch.setattr(groq_reader,'request_invoice',lambda *a:pytest.fail('Cached result must not call AI'))
    result=groq_reader.candidate(tmp_path,row)
    assert result['items'][0]['name']=='Model1' and result['items'][0]['quantity']=='2.4877'
    assert result['ocr_reading_evidence']==evidence() and any('OCR ambiguity' in w for w in result['extraction_warnings'])
    assert path.read_bytes()==before


def test_installer_contains_exact_ocr_changes_and_backups():
    root=Path(__file__).parents[2];package=runpy.run_path(str(root/'Install_BillSync_Source.py'))
    for name in ('Common_Rules/ocr.py','Common_Rules/extraction.py','Common_Rules/desktop.py','Common_Rules/groq_reader.py','OCR_Review_Dialog.py','BillSync_UI.py'):
        assert package['FILES'][name].encode()==(root/'Automation'/name).read_bytes()
    change=json.loads((root/'Automation/OCR_REVIEW_GUARD_CHANGE.json').read_text())
    with zipfile.ZipFile(root/change['backup']) as archive:
        for name,hashes in change['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==hashes['baseline_sha256']
            expected=hashes['authorized_sha256']
            premium=json.loads((root/'Automation/PREMIUM_UI_CHANGE.json').read_text())
            if name in premium['files']:
                replacement=premium['files'][name];assert replacement['baseline_sha256']==expected
                with zipfile.ZipFile(root/premium['backup']) as later:assert hashlib.sha256(later.read(name)).hexdigest()==expected
                expected=replacement['authorized_sha256']
            from test_premium_ui import after_boxed_ui
            after_boxed_ui(root,name,expected)


def exercise_ocr_review_ui(root,app,monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    app.records[0]['invoice']['ocr_reading_evidence']=evidence()
    app.table.selection_set('0');app.table.focus('0')
    calls=[];monkeypatch.setattr(app,'review',lambda:calls.append('edit'))
    app.review_ocr_evidence();root.update()
    top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='OCR reading evidence')
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    widgets=list(descendants(top));text=next(w for w in widgets if isinstance(w,tk.Text))
    assert 'Original OCR: Penci1' in text.get('1.0','end') and 'Second read: Pencil' in text.get('1.0','end')
    assert text.cget('state')=='disabled'
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Edit invoice').invoke();root.update()
    assert calls==['edit'] and not top.winfo_exists()

@pytest.mark.parametrize('kind',['png','jpg','jpeg'])
def test_real_scan_local_second_read_cached_ai_xml_and_manual_correction(tmp_path,monkeypatch,kind):
    """Real OCR; explicitly controlled AI response, not measured Groq accuracy."""
    import socket
    import pypdfium2 as pdfium
    import xml.etree.ElementTree as ET
    from audits.test_app_contracts import record,invoice_pdf
    from Document_Upload import upload_documents
    from Common_Rules.ai_first import run_ai_first
    from Common_Rules.desktop import inspect_sources,save_review
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    def blocked(*a,**kw):pytest.fail('No live network in OCR test')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    oracle=record(tmp_path,'AUD-2026-101')['invoice'];raw=invoice_pdf(oracle,'stacked')
    with pdfium.PdfDocument(raw) as pdf:
        page=pdf[0];bitmap=page.render(scale=2)
        try:image=bitmap.to_pil().convert('RGB').copy()
        finally:bitmap.close();page.close()
    source=tmp_path/('scan.'+kind);image.save(source,format='PNG' if kind=='png' else 'JPEG',quality=96)
    original=source.read_bytes();root=tmp_path/'app'
    uploaded=upload_documents(root,'Client',[source]);assert not uploaded['errors']
    path=uploaded['uploaded'][0]['path'];calls=[]
    def controlled_ai(payload,*args):
        calls.append(payload)
        primary=payload['messages'][1]['content'].split('\n\nOCR READING EVIDENCE')[0]
        hints=payload.ocr_evidence
        # Deliberately retains the original misspelling and offers actual
        # threshold OCR evidence; no fixture response is used to prove OCR.
        assert 'Penci1' in primary
        assert any('Penci1' in e.get('primary','') and any('Pencil' in a['text'] for a in e.get('alternatives',[])) for e in hints)
        return {**{k:v for k,v in oracle.items() if k in FIELDS},'items':[{k:v for k,v in i.items() if k in ITEM_FIELDS} for i in oracle['items']]}
    monkeypatch.setenv('GROQ_API_KEY','offline-test-placeholder');monkeypatch.setattr(groq_reader,'request_invoice',controlled_ai)
    rows,summary=run_ai_first(root,False,['Client'],primary='Groq',selected_paths=[path],max_new_requests=1)
    assert summary['new_ai_attempts']==summary['ai_read_invoices']==1 and len(calls)==1
    row=rows[0];assert row['invoice']['ocr_reading_evidence']
    assert any('OCR ambiguity' in w for w in row['invoice']['extraction_warnings'])
    voucher=ET.parse(Path(row['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
    assert voucher.findtext('VOUCHERNUMBER')=='AUD-2026-101'
    assert 'OCR ambiguity' in voucher.findtext('NARRATION')
    report=json.loads((Path(row['output_path'])/'Batch_Report.json').read_text())
    assert report['invoices'][0]['extracted_invoice']['ocr_reading_evidence']
    assert any('OCR ambiguity' in w for w in report['invoices'][0]['warnings'])
    assert [(e.findtext('STOCKITEMNAME'),e.findtext('AMOUNT')) for e in voucher.findall('ALLINVENTORYENTRIES.LIST')]==[('Blue pen','100.00'),('Pencil','100.00')]
    _,again=run_ai_first(root,False,['Client'],primary='Groq',selected_paths=[path],max_new_requests=1)
    assert again['new_ai_attempts']==0 and len(calls)==1
    edited=deepcopy(row['invoice']);edited['items'][1]['name']='Pencil reviewed'
    save_review(root,row,edited)
    refreshed=inspect_sources(root,['Client'],False)[0]
    assert refreshed['invoice']['items'][1]['name']=='Pencil reviewed'
    assert not any('OCR ambiguity' in w for w in refreshed['invoice']['extraction_warnings'])
    assert refreshed['invoice']['ocr_reading_evidence'] and source.read_bytes()==original and len(calls)==1

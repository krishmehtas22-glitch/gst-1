from pathlib import Path
from types import SimpleNamespace
import hashlib,json
import pytest
from Reading_V2.document import read_document,cluster_lines,ocr_words
from Reading_V2.reader import read_invoice,fields_from_document,tables_from_document,decimal,ai_input
from Reading_V2.evaluate import compare,csv_value


def word(text,x,y,width=.10,page=1,index=1):
    return {'id':f'p{page}w{index}','text':text,'box':[x,y,x+width,y+.012],
            'origin':'pdf','ocr_confidence':None}


def document(rows):
    tokens=[]
    for row in rows:
        for text,x,y,width in row:tokens.append(word(text,x,y,width,index=len(tokens)+1))
    lines=cluster_lines(tokens)
    for i,line in enumerate(lines):line.update(id=f'p1l{i+1}',text=' '.join(t['text'] for t in line['tokens']))
    return {'version':'test','source_sha256':'a'*64,'warnings':[],
        'pages':[{'number':1,'width':600,'height':800,'tokens':tokens,'lines':lines}]}


def test_early_pdf_footer_order_is_replaced_by_page_positions():
    path=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    raw=path.read_bytes();d=read_document(path)
    assert d['source_sha256']==hashlib.sha256(raw).hexdigest()
    tokens=d['pages'][0]['tokens'];assert tokens
    assert all(0<=t['box'][0]<=t['box'][2]<=1 and 0<=t['box'][1]<=t['box'][3]<=1 for t in tokens)
    assert len({t['id'] for t in tokens})==len(tokens)
    assert path.read_bytes()==raw


def test_side_by_side_buyer_and_supply_panel_do_not_mix_names():
    d=document([[('BUYER',.05,.1,.09),('SUPPLY',.6,.1,.10),('DETAILS',.71,.1,.11)],
                [('Buyer',.05,.13,.07),('Business',.13,.13,.11),('Seller',.6,.13,.07),('state:',.68,.13,.06),('Maharashtra',.75,.13,.15)],
                [('GSTIN:',.05,.16,.09),('27BBBBB0000B1Z5',.16,.16,.23),('Currency:',.6,.16,.12),('INR',.74,.16,.06)]])
    found=fields_from_document(d)
    assert found['buyer_name'][0]['value']=='Buyer Business'
    assert found['buyer_gstin'][0]['value']=='27BBBBB0000B1Z5'
    assert found['currency'][0]['value']=='INR'


def test_invoice_date_words_in_separate_columns_are_not_one_label():
    d=document([[('Invoice',.05,.1,.08),('Date',.5,.1,.06)],
                [('INV-123',.05,.13,.11),('10/10/2026',.5,.13,.15)]])
    found=fields_from_document(d)
    assert found['number'][0]['value']=='INV-123'
    assert found['date'][0]['value']=='2026-10-10'


def test_generic_table_uses_column_geometry_not_supplier_template():
    d=document([[('Description',.02,.2,.15),('Qty',.3,.2,.04),('Unit',.43,.2,.05),('Rate',.58,.2,.06),('Amount',.78,.2,.10)],
                [('Steel',.02,.24,.06),('tray',.10,.24,.06),('2.375',.3,.24,.07),('KG',.43,.24,.04),('40.00',.58,.24,.07),('95.00',.78,.24,.07)],
                [('Total',.02,.28,.06),('95.00',.78,.28,.07)]])
    tables=tables_from_document(d)
    assert len(tables)==1 and len(tables[0]['rows'])==1
    row=tables[0]['rows'][0]
    assert row['values']=={'name':'Steel tray','quantity':'2.375','unit':'KG','rate':'40.00','value':'95.00'}
    assert row['evidence']['quantity']['token_ids']


def test_gstin_role_uses_latest_buyer_block_in_same_column():
    d=document([[('Seller',.05,.05,.09)], [('Supplier',.05,.08,.12)],
                [('GSTIN:',.05,.11,.09),('27AAAAA0000A1Z5',.16,.11,.23)],
                [('BUYER',.05,.2,.09)],[('Buyer',.05,.23,.07),('Business',.13,.23,.11)],
                [('GSTIN:',.05,.26,.09),('27BBBBB0000B1Z5',.16,.26,.23)]])
    found=fields_from_document(d)
    assert found['seller_gstin'][0]['value']=='27AAAAA0000A1Z5'
    assert found['buyer_gstin'][0]['value']=='27BBBBB0000B1Z5'


def test_decimal_commas_are_not_silently_changed_to_thousands():
    assert decimal('1,234.50')==decimal('1234.50')
    assert decimal('1,23,456.78')==decimal('123456.78')
    assert decimal('1,50') is None


def test_scanned_page_preserves_boxes_and_ocr_confidence():
    closed=[]
    class Bitmap:
        def to_numpy(self):
            import numpy as np
            return np.zeros((300,600,3),dtype='uint8')
        def close(self):closed.append(True)
    class Page:
        def render(self,scale):return Bitmap()
    def engine(image):return SimpleNamespace(boxes=[[[60,30],[180,30],[180,60],[60,60]]],txts=['Buyer'],scores=[.93])
    rows=ocr_words(Page(),0,engine)
    assert rows[0]['box']==[.1,.1,.3,.2]
    assert rows[0]['origin']=='ocr' and rows[0]['ocr_confidence']==.93
    assert closed==[True]


def test_no_ai_input_is_silently_truncated():
    path=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    result=read_invoice(path)
    with pytest.raises(ValueError,match='No content was silently truncated'):ai_input(result,max_characters=10)


def test_report_is_read_only_and_preserves_markup_as_data(tmp_path):
    path=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf';raw=path.read_bytes()
    report=tmp_path/'comparison';result=compare([path],report,progress=lambda _:None)
    assert result['no_ai_requests'] and result['no_tally_imports'] and not result['active_reader_changed']
    assert not result['accuracy_measured']
    assert path.read_bytes()==raw
    assert not list(tmp_path.rglob('Units.xml')) and not list(tmp_path.rglob('Sales_Vouchers.xml'))
    assert (report/'Report.html').exists()
    with pytest.raises(FileExistsError):compare([path],report,progress=lambda _:None)


def test_multiple_invoice_identifiers_cannot_be_sent_as_one_ai_request():
    with pytest.raises(ValueError,match='separate the invoices'):ai_input({'invoice_grouping_required':True})


def test_candidate_never_mutates_supplied_baseline():
    import copy
    path=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    baseline={'number':'Keep-99','buyer_name':'Keep Buyer','items':[{'quantity':'0.12345','rate':'12.345','value':'1.52','unit':'KG'}]}
    snapshot=copy.deepcopy(baseline)
    result=read_invoice(path,baseline)
    assert baseline==snapshot and result['invoice']['number']=='Keep-99'
    assert result['automatic_import_enabled'] is False and result['conflicts']


def test_csv_file_names_cannot_execute_spreadsheet_formulas():
    assert csv_value('=1+1.pdf')=="'=1+1.pdf"
    assert csv_value('normal.pdf')=='normal.pdf'


def test_bad_pdf_is_retained_in_review_report(tmp_path):
    path=tmp_path/'broken.pdf';path.write_bytes(b'not a PDF')
    result=compare([path],tmp_path/'comparison',progress=lambda _:None)
    assert result['failed']==1 and result['documents'][0]['error']
    assert 'read_error' in (tmp_path/'comparison/Report.html').read_text()


def test_invoice_markup_cannot_escape_report_data(tmp_path,monkeypatch):
    from Reading_V2 import evaluate
    path=Path(__file__).parent/'fixtures/client1/TEST-S-001.pdf'
    real=evaluate.read_invoice
    def with_markup(*args,**kwargs):
        result=real(*args,**kwargs)
        result['invoice']['buyer_name']='</script><script>alert("unsafe")</script>'
        return result
    monkeypatch.setattr(evaluate,'read_invoice',with_markup)
    compare([path],tmp_path/'comparison',progress=lambda _:None)
    html=(tmp_path/'comparison/Report.html').read_text()
    assert '</script><script>alert("unsafe")' not in html
    assert '\\u003c/script\\u003e' in html

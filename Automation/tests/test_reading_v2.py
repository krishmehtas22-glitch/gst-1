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


def test_invoice_date_outranks_order_and_due_dates():
    d=document([[('Order',.05,.10,.07),('Date:',.13,.10,.07),('15-10-2025',.22,.10,.14)],
                [('Invoice',.05,.14,.10),('Date:',.16,.14,.07),('20-10-2025',.25,.14,.14)],
                [('Due',.05,.18,.06),('Date:',.12,.18,.07),('30-10-2025',.21,.18,.14)]])
    assert [e['value'] for e in fields_from_document(d)['date']]==['2025-10-20']


def test_adjacent_reference_is_not_another_invoice_identifier():
    d=document([[('Invoice',.05,.10,.10),('INV/2030/001',.16,.10,.20)],
                [('Invoice',.05,.15,.10),('Date:',.16,.15,.06),('Due',.40,.15,.07),('Date:',.48,.15,.06),('Reference:',.70,.15,.15)],
                [('03/20/2030',.05,.18,.16),('04/04/2030',.40,.18,.16),('REF123',.70,.18,.13)]])
    found=fields_from_document(d)
    assert [e['value'] for e in found['number']]==['INV/2030/001']
    assert [e['value'] for e in found['date']]==['2030-03-20']


def test_currency_prefixes_and_regional_commas_require_context():
    assert decimal('$ 279.84')==decimal('279.84')
    assert decimal('Rs 1939')==decimal('1939')
    assert decimal('€ 2.321,00',locale='comma')==decimal('2321.00')
    assert decimal('1,50') is None
    assert decimal('12 34,00',locale='comma') is None
    assert decimal('12 USD 99') is None


def test_english_and_regional_months_are_normalized():
    from Reading_V2.reader import date_value
    assert date_value('August 3 , 2014')=='2014-08-03'
    assert date_value('7. Mai 2014')=='2014-05-07'
    assert date_value('29 maart 2014')=='2014-03-29'
    assert date_value('02 Juillet 2015')=='2015-07-02'
    assert date_value('31/02/2025') is None


def test_currency_item_rows_keep_quantity_units_and_group_subtotals():
    d=document([[('Description',.02,.20,.15),('Qty',.35,.20,.05),('Unit',.55,.20,.05),('Price',.61,.20,.06),('Amount',.85,.20,.10)],
                [('Steel',.02,.24,.06),('2.375',.35,.24,.08),('kg',.44,.24,.04),('$',.55,.24,.02),('40.00',.60,.24,.07),('$',.85,.24,.02),('95.00',.90,.24,.07)],
                [('Subtotal',.75,.28,.08),('$95.00',.90,.28,.07)],
                [('Wood',.02,.32,.06),('1',.35,.32,.03),('PCS',.42,.32,.05),('$',.55,.32,.02),('10.00',.60,.32,.07),('$',.85,.32,.02),('10.00',.90,.32,.07)],
                [('Total',.75,.36,.08),('$105.00',.90,.36,.08)]])
    rows=tables_from_document(d)[0]['rows']
    assert len(rows)==2
    assert rows[0]['values']['quantity']=='2.375' and rows[0]['values']['unit']=='kg'
    assert rows[0]['values']['rate']=='40.00' and rows[0]['values']['value']=='95.00'


def test_attached_french_invoice_number_and_date_keep_source_evidence():
    d=document([[('Facture',.05,.10,.10),('n°12345678',.17,.10,.17),('du',.36,.10,.03),('02',.40,.10,.03),('Juillet',.45,.10,.10),('2015',.57,.10,.06)]])
    found=fields_from_document(d)
    assert found['number'][0]['value']=='12345678'
    assert found['date'][0]['value']=='2015-07-02'
    assert found['number'][0]['evidence']['token_ids']


def test_number_label_with_degree_symbol_is_normalized():
    d=document([[('Facture',.05,.10,.10),('n°',.17,.10,.03),('12345678',.22,.10,.17)]])
    assert fields_from_document(d)['number'][0]['value']=='12345678'


def test_inventory_table_keeps_taxable_and_gross_columns_separate():
    path=Path(__file__).parent/'fixtures/client12/INV05_B2C_inter.pdf'
    result=read_invoice(path)
    rows=[r for t in result['table_candidates'] for r in t['rows']]
    assert len(rows)==2
    assert decimal(rows[0]['values']['value'])==decimal('235500')
    assert decimal(rows[0]['values']['gross_value'])==decimal('277890')


def test_table_does_not_treat_tax_summary_as_another_item():
    d=document([[('Description',.02,.20,.15),('Qty',.35,.20,.05),('Rate',.60,.20,.06),('Amount',.85,.20,.10)],
                [('Steel',.02,.24,.06),('2',.35,.24,.03),('40.00',.60,.24,.07),('80.00',.85,.24,.07)],
                [('Subtotal',.75,.28,.08),('80.00',.85,.28,.07)],
                [('Tax',.02,.32,.05),('15%',.09,.32,.05),('on',.15,.32,.03),('80.00',.35,.32,.07),('12.00',.85,.32,.07)]])
    table=tables_from_document(d)[0]
    assert len(table['rows'])==1 and not table['warnings']


def test_fixture_banner_is_not_a_supplier_name():
    d=document([[('SYNTHETIC',.05,.03,.12),('FIXTURE',.18,.03,.10),('SUPPLIER',.30,.03,.10),('FOR',.42,.03,.05),('SOFTWARE',.48,.03,.12),('TESTING',.62,.03,.10)],
                [('Fictional',.05,.08,.10),('Gulf',.17,.08,.05),('Foods',.24,.08,.07),('LLC',.33,.08,.05)],
                [('Bill',.05,.18,.05),('To:',.11,.18,.04),('Buyer',.16,.18,.06),('Ltd',.23,.18,.04)]])
    assert fields_from_document(d)['seller_name'][0]['value']=='Fictional Gulf Foods LLC'


def test_reporting_currency_does_not_replace_invoice_currency():
    d=document([[('Currency:',.05,.10,.13),('USD',.20,.10,.06)],
                [('Merchant',.05,.14,.11),('store',.17,.14,.07),('currency:',.25,.14,.12),('AED',.40,.14,.06)]])
    assert [e['value'] for e in fields_from_document(d)['currency']]==['USD']


def test_bare_dollar_symbol_does_not_establish_usd():
    d=document([[('Total',.05,.10,.08),('$100.00',.60,.10,.12)]])
    assert 'currency' not in fields_from_document(d)


def test_delivery_date_is_not_an_invoice_date_label():
    d=document([[('Delv.',.05,.10,.07),('Date:',.13,.10,.07),('5/16/2024',.22,.10,.14)]])
    found=fields_from_document(d)
    assert 'date' not in found and found['_other_dates'][0]['value']=='2024-05-16'


def test_ocr_deskew_preserves_real_boxes_and_correct_total_pairing():
    class Bitmap:
        def to_numpy(self):
            import numpy as np
            return np.zeros((300,600,3),dtype='uint8')
        def close(self):pass
    class Page:
        def render(self,scale):return Bitmap()
    def box(x,width,y):
        return [[x,y+.06*x],[x+width,y+.06*(x+width)],
                [x+width,y+10+.06*(x+width)],[x,y+10+.06*x]]
    def engine(_):
        return SimpleNamespace(boxes=[box(20,80,130),box(420,70,130),box(20,50,150),box(420,70,150),box(20,400,220)],
                               txts=['VAT 5%','AED 3.00','Total','AED 63.00','Invoice footer text'],scores=[.99]*5)
    words=ocr_words(Page(),0,engine)
    lines=cluster_lines(words)
    for i,line in enumerate(lines):line.update(id=f'p1l{i+1}',text=' '.join(w['text'] for w in line['tokens']))
    d={'pages':[{'number':1,'tokens':words,'lines':lines}]}
    assert fields_from_document(d)['total'][0]['value']=='63.00'
    assert all(w['box_scope']=='ocr_line_region' for w in words)
    assert words[0]['box'][1] != words[2]['box'][1]

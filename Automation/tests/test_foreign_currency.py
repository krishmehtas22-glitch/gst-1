"""Controlled currency inputs -> actual exporter, no paid AI or Tally writes."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json,zipfile,types
import xml.etree.ElementTree as ET
import pytest
from test_buyer_ledger_guard import assert_after_guard
from Common_Rules.foreign_currency import currency_code,convert,save_settings,for_record,load_settings
from Common_Rules.tally_review_export import export_all
from Export_Refund_Review import summary,save_review,load_review


def row(currency='USD',rate='83.125'):
    return {'client':'Client','path':'invoice.pdf','digest':'a'*64,'errors':[],
        'invoice':{'number':'FX-1','date':'2026-10-17','currency':currency,'exchange_rate':rate,
        'exchange_rate_basis':'INR_per_foreign','buyer_name':'Foreign buyer','seller_name':'Supplier',
        'buyer_country':'United Kingdom','supply':'EXPORT','classification':'export_igst',
        'place_of_supply':'Outside India','seller_gstin':'27ABCDE1234F1Z0','taxable':'200','total':'236',
        'cgst':'0','sgst':'0','igst':'36','cess':'0','round_off':'0',
        'items':[{'name':'Pen','quantity':'2.5','unit':'PCS','rate':'80','value':'200',
                  'cgst_rate':'0','sgst_rate':'0','igst_rate':'18','hsn':'960810'}]}}


@pytest.mark.parametrize('value,expected',[('usd','USD'),('US$','USD'),('USD ($)','USD'),('us dollers','USD'),
    ('€','EUR'),('EUROS','EUR'),('£','GBP'),('₹','INR'),('Rs.','INR'),('د.إ','AED'),
    ('uae dirhams','AED'),('Canadian dollars','CAD'),('Japanese yen','JPY'),('Swiss frnac','CHF'),('SAR','SAR')])
def test_codes_symbols_names_and_safe_typos(value,expected):assert currency_code(value)==expected


@pytest.mark.parametrize('value',['$','¥','dollar','rupee','USD / EUR','XYZ','euro dirham','EUR £','US$ CAD'])
def test_ambiguous_currency_needs_review(value):
    with pytest.raises(ValueError):currency_code(value)


@pytest.mark.parametrize('currency',['USD','AED','EUR','GBP','JPY','CAD','CHF','SAR','SGD'])
def test_decimal_projection_preserves_source_quantity_and_tax_rates(currency):
    source=row(currency)['invoice'];before=deepcopy(source);out=convert(source)
    assert source==before
    assert out['currency']=='INR' and out['taxable']=='16625.00' and out['total']=='19617.50'
    assert out['igst']=='2992.50' and out['items'][0]['rate']=='6650.000'
    assert out['items'][0]['quantity']=='2.5' and out['items'][0]['igst_rate']=='18'
    assert out['currency_conversion']['original_amounts']['total']=='236'
    assert convert(out)==out  # Never multiply a projection twice.


@pytest.mark.parametrize('rate',['',None,'0','-1','NaN','Infinity','1/83','83 or 84','1e3','83,5'])
def test_invalid_rate_keeps_prior_xml(tmp_path,rate):
    good=row();export_all(tmp_path,[good],False)
    folder=Path(good['output_path']);before={n:p.read_bytes() for p in folder.iterdir() if p.is_file() for n in [p.name]}
    bad=row(rate=rate)
    with pytest.raises(ValueError):export_all(tmp_path,[bad],False)
    assert before=={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    assert summary(bad)['estimate'] is None


def test_inverse_rate_and_fractional_precision():
    source=row(rate='.0125')['invoice'];source['exchange_rate_basis']='foreign_per_INR'
    result=convert(source)
    assert Decimal(result['exchange_rate'])==80 and result['total']=='18880.00'
    source['exchange_rate_basis']='unknown'
    with pytest.raises(ValueError,match='direction'):convert(source)


def test_printed_100_unit_quote_is_not_mistaken_for_one_unit():
    source=row('JPY','55')['invoice'];source['exchange_rate_units']='100'
    result=convert(source)
    assert result['total']=='129.80' and result['exchange_rate']=='0.55'
    source['exchange_rate_basis']='foreign_per_INR';source['exchange_rate']='125';source['exchange_rate_units']='100'
    assert convert(source)['total']=='188.80'


def test_manual_override_is_source_and_client_scoped_and_reused(tmp_path):
    record=row(rate=None);before=deepcopy(record)
    save_settings(tmp_path,record,'USD','84.123456')
    assert for_record(tmp_path,record)['total']=='19853.14'
    assert record==before
    other=deepcopy(record);other['client']='Other'
    with pytest.raises(ValueError):for_record(tmp_path,other)
    other=deepcopy(record);other['digest']='b'*64
    assert load_settings(tmp_path,other) is None
    record['invoice']['total']='300'
    with pytest.raises(ValueError,match='amounts changed'):for_record(tmp_path,record)


def test_manual_currency_resolves_symbol_and_inr_basis_avoids_double_conversion(tmp_path):
    record=row('$',None);save_settings(tmp_path,record,'CAD','60')
    assert for_record(tmp_path,record)['total']=='14160.00'
    save_settings(tmp_path,record,'CAD','60','INR')
    assert for_record(tmp_path,record)['total']=='236'


def test_existing_dual_currency_inr_values_stay_unchanged():
    inv=row('INR')['invoice'];inv['foreign_currency']='USD';inv['foreign_invoice_value']='2.839'
    assert convert(inv)==inv


def test_xml_amounts_refund_and_stable_guid(tmp_path):
    record=row();before=deepcopy(record['invoice']);export_all(tmp_path,[record],False)
    folder=Path(record['output_path']);doc=ET.parse(folder/'Sales_Vouchers.xml')
    voucher=doc.find('.//VOUCHER');guid=voucher.findtext('GUID')
    assert voucher.findtext('.//ALLLEDGERENTRIES.LIST/AMOUNT')=='-19617.50'
    assert '1 USD = INR 83.125' in voucher.findtext('NARRATION')
    assert sum(Decimal(e.findtext('AMOUNT')) for e in voucher.findall('ALLLEDGERENTRIES.LIST'))==0
    assert record['invoice']==before
    report=json.loads((folder/'Batch_Report.json').read_text())['invoices'][0]
    assert report['extracted_invoice']['currency_conversion']['original_amounts']['total']=='236'
    assert summary(record,tmp_path)['estimate']=='2992.50'
    save_settings(tmp_path,record,'USD','84');export_all(tmp_path,[record],False)
    assert ET.parse(folder/'Sales_Vouchers.xml').findtext('.//GUID')==guid
    assert summary(record,tmp_path)['estimate']=='3024.00'
    save_review(tmp_path,record,'Claimed','3000','SB-1')
    assert load_review(tmp_path,record)['claim_amount']=='3000.00'
    save_settings(tmp_path,record,'USD','85')
    assert load_review(tmp_path,record) is None


def test_converted_inventory_reuses_existing_master_assignments(tmp_path):
    from test_tally_master_matching import setup,choices
    from Common_Rules.tally_master_matching import save_choices
    record,ctx=setup(tmp_path)
    record['invoice'].update(currency='USD',exchange_rate='83.25',exchange_rate_basis='INR_per_foreign')
    save_choices(tmp_path,record,ctx,record['invoice'],choices())
    original=deepcopy(record['invoice']);export_all(tmp_path,[record],False)
    doc=ET.parse(Path(record['output_path'])/'Sales_Vouchers.xml')
    assert doc.findtext('.//PARTYLEDGERNAME')=='Northstar Hardware Account'
    item=doc.find('.//ALLINVENTORYENTRIES.LIST')
    assert item.findtext('STOCKITEMNAME')=='Rack - Steel' and item.findtext('ACTUALQTY')=='4 Number'
    assert Decimal(item.findtext('AMOUNT'))==Decimal('832500')
    assert Decimal(item.findtext('RATE').split('/')[0])==Decimal('208125')
    assert record['invoice']==original


def test_printed_rate_direction_units_and_currency_invalidate_refund_review(tmp_path):
    for field,value in [('exchange_rate_units','100'),('exchange_rate_basis','foreign_per_INR'),('currency','EUR')]:
        record=row();save_review(tmp_path,record,'Eligibility reviewed',notes='Checked initial currency and rate.')
        assert load_review(tmp_path,record) is not None
        record['invoice'][field]=value
        assert load_review(tmp_path,record) is None


def test_domestic_and_existing_inr_export_xml_byte_identical_to_backup(tmp_path):
    path=Path(__file__).parents[2]/'Backups/Before_Foreign_Currency.zip'
    with zipfile.ZipFile(path) as z:source=z.read('Automation/Common_Rules/tally_review_export.py')
    old=types.ModuleType('Common_Rules._pre_currency');old.__package__='Common_Rules';exec(compile(source,'previous.py','exec'),old.__dict__)
    for supply in ('EXPORT','INTRA'):
        record=row('INR');record['invoice'].update(supply=supply)
        if supply=='INTRA':record['invoice'].update(classification='taxable',place_of_supply='27')
        old.export_all(tmp_path,[record],False);folder=Path(record['output_path'])
        before={n:(folder/n).read_bytes() for n in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}
        export_all(tmp_path,[record],False)
        assert before=={n:(folder/n).read_bytes() for n in before}


def test_ai_currency_fields_are_retained_without_ai_converting():
    from Common_Rules.gemini_reader import normalize_invoice_result
    source=row()['invoice'];fields={'currency','exchange_rate','exchange_rate_basis','total','taxable','cgst','sgst','igst','classification','supply','buyer_country'}
    response={k:v for k,v in source.items() if k in fields};response['items']=[]
    normalized=normalize_invoice_result(response,{'invoice':{}},'Groq')
    assert normalized['currency']=='USD' and normalized['total']=='236' and normalized['exchange_rate']=='83.125'


def test_installer_contains_currency_files_and_historical_hash_chain():
    import runpy,hashlib
    repo=Path(__file__).parents[2];installed=runpy.run_path(str(repo/'Install_BillSync_Source.py'))
    for name in ('Currency_Review_Dialog.py','Common_Rules/foreign_currency.py','Common_Rules/gemini_reader.py','Common_Rules/ai_invoice_rules.py'):
        assert installed['FILES'][name]==(repo/'Automation'/name).read_text()
    change=json.loads((repo/'Automation/FOREIGN_CURRENCY_CHANGE.json').read_text())
    with zipfile.ZipFile(repo/change['backup']) as archive:
        for name,values in change['files'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest()==values['baseline_sha256']
            later=json.loads((repo/'Automation/QUANTITY_PRECISION_CHANGE.json').read_text())['files']
            if name in later:
                assert later[name]['baseline_sha256']==values['authorized_sha256']
                duplicate=json.loads((repo/'Automation/DUPLICATE_WARNING_CHANGE.json').read_text())['files']
                if name in duplicate:
                    assert duplicate[name]['baseline_sha256']==later[name]['authorized_sha256']
                    assert_after_guard(repo,name,duplicate[name]['authorized_sha256'])
                else:assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==later[name]['authorized_sha256']
            else:
                duplicate=json.loads((repo/'Automation/DUPLICATE_WARNING_CHANGE.json').read_text())['files']
                if name in duplicate:
                    assert duplicate[name]['baseline_sha256']==values['authorized_sha256']
                    assert_after_guard(repo,name,duplicate[name]['authorized_sha256'])
                else:assert_after_guard(repo,name,values['authorized_sha256'])


def exercise_currency_dialog(root,app,tmp_path,monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    record=row('$',None);record['listing_only']=False
    app.records[0]=record;app.table.selection_set('0');app.table.focus('0');app.apply_filter();root.update()
    assert app.table.set('0','total')=='Review currency'
    calls=[];monkeypatch.setattr(app,'reset',lambda:calls.append('reset'))
    monkeypatch.setattr(app,'revalidate',lambda **kw:calls.append(kw))
    app.currency_review();root.update()
    top=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Currency / exchange rate')
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    widgets=list(descendants(top))
    combos=[w for w in widgets if isinstance(w,ttk.Combobox)]
    combos[0].set('USD');combos[1].set('foreign')
    entry=next(w for w in widgets if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox));entry.delete(0,'end');entry.insert(0,'84')
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Preview INR').invoke();root.update()
    assert any('19824.00' in w.cget('text') for w in widgets if isinstance(w,ttk.Label))
    assert not load_settings(tmp_path,record) and not calls
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Save rate & prepare XML').invoke();root.update()
    assert calls==['reset',{'client_names':['Client']}]
    assert load_settings(tmp_path,record)['exchange_rate']=='84'
    assert not top.winfo_exists()
    app.apply_filter();root.update()
    assert app.table.set('0','total')=='19,824.00' and '3,024.00' in app.table.set('0','refund_estimate')

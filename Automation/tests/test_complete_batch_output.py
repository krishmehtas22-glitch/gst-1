from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import json,shutil
import xml.etree.ElementTree as ET
import pytest
from Common_Rules import gemini_reader,groq_reader
from Common_Rules.gemini_batch import read_batch,read_with_fallback
from Common_Rules.desktop import inspect_sources,process_sources
from Common_Rules.tally_review_export import enable,export_all


def sources(root):
    shutil.copytree(Path(__file__).parent/'fixtures/client23',root/'Client')
    return inspect_sources(root)


def test_10_primary_4_secondary_and_6_python_all_become_xml(tmp_path,monkeypatch):
    scanned=sources(tmp_path)
    monkeypatch.setenv('GEMINI_API_KEY','private-test-key');monkeypatch.setenv('GROQ_API_KEY','private-test-key')
    monkeypatch.delenv('GEMINI_INVOICE_MODEL',raising=False);monkeypatch.delenv('GROQ_INVOICE_MODEL',raising=False)
    calls={'Gemini':0,'Groq':0}
    def batch(root,records,provider,**kwargs):
        reader=gemini_reader if provider=='Gemini' else groq_reader
        def extract(root,record):
            def transport(*args):
                calls[provider]+=1
                if calls[provider]>(10 if provider=='Gemini' else 4):raise ValueError(provider+' HTTP 429: quota')
                original=record['invoice'];inv={k:original.get(k) for k in gemini_reader.FIELDS}
                inv['items']=[{k:i.get(k) for k in gemini_reader.ITEM_FIELDS} for i in original['items']]
                return inv
            return reader.extract_selected(root,record,transport)
        return read_batch(root,records,provider=provider,extract=extract,wait=lambda _:None,**kwargs)
    results=read_with_fallback(tmp_path,scanned,batch_reader=batch,confirm_test=True)
    assert calls=={'Gemini':11,'Groq':5}
    assert sum(r['status']=='extracted' for r in results)==14
    assert sum(r['provider']=='Python' for r in results)==6
    processed=process_sources(tmp_path)
    assert len(processed)==20 and all(not r['errors'] for r in processed)
    output=Path(processed[0]['output_path']);xml=ET.parse(output/'Sales_Vouchers.xml')
    assert len(xml.findall('.//VOUCHER'))==20
    report=json.loads((output/'Batch_Report.json').read_text())
    assert report['xml_voucher_count']==report['input_count']==20
    assert {x['provider'] for x in report['invoices']}=={'Gemini','Groq','Python'}
    assert len(list(output.glob('*Masters*.xml')))==1
    # A later scan points to a new current run and never asks the APIs again.
    latest=process_sources(tmp_path)
    assert latest[0]['output_path']!=processed[0]['output_path']
    assert len(ET.parse(Path(latest[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==20
    assert calls=={'Gemini':11,'Groq':5}
    import Invoice_Desktop
    app=Invoice_Desktop.InvoiceApp.__new__(Invoice_Desktop.InvoiceApp)
    app.selected=lambda:latest[0]
    opened=[]
    monkeypatch.setattr(Invoice_Desktop.subprocess,'Popen',lambda args:opened.append(args))
    app.open_output()
    assert opened[0][-1]==latest[0]['output_path']


def test_missing_seller_gstin_dates_and_unbalanced_amounts_still_output(tmp_path):
    rows=sources(tmp_path)[:3]
    source_dates={r['digest']:r['invoice']['date'].replace('-','') for r in rows}
    rows[0]['invoice'].update(seller_name='',seller_gstin='INVALID',buyer_gstin='INVALID',total='100.00',taxable='60.00',cgst='5',sgst='5',igst='0')
    rows[1]['invoice']={'number':'MISSING','total':'99.00','cgst':'0','sgst':'0','igst':'0'}
    rows[2]['invoice']={};rows[2]['errors']=['Seller missing','Check GSTIN','Client locked by prior marker']
    exported=export_all(tmp_path,rows,True)
    output=Path(exported[0]['output_path'])
    vouchers=[v for p in output.rglob('Sales_Vouchers.xml') for v in ET.parse(p).findall('.//VOUCHER')]
    assert len(vouchers)==3 and all(not r['errors'] for r in exported)
    for v in vouchers:
        inventory=sum(Decimal(i.findtext('AMOUNT')) for i in v.findall('ALLINVENTORYENTRIES.LIST'))
        ledger=sum(Decimal(i.findtext('AMOUNT')) for i in v.findall('ALLLEDGERENTRIES.LIST'))
        assert inventory+ledger==0
    report=json.loads((output/'Batch_Report.json').read_text())
    # Dates erased from the extraction are now recovered from these real PDFs.
    xml_dates={v.findtext('GUID'):v.findtext('DATE') for v in vouchers}
    assert all(xml_dates[r['voucher_guid']]==source_dates[r['digest']] for r in report['invoices'])
    assert any('date recovered' in ' '.join(r['warnings']) for r in report['invoices'])
    assert any('Unreconciled difference' in ' '.join(r['warnings']) for r in report['invoices'])


def test_conflicting_stock_units_get_distinct_referenced_masters(tmp_path):
    rows=sources(tmp_path)[:2]
    item=deepcopy(rows[0]['invoice']['items'][0])
    for row,unit in zip(rows,['PCS','BOX']):
        row['invoice']['items']=[{**item,'unit':unit}]
        row['invoice']['taxable']=item['value']
    exported=export_all(tmp_path,rows,True);folder=Path(exported[0]['output_path'])
    masters=ET.parse(folder/'Masters.xml');sales=ET.parse(folder/'Sales_Vouchers.xml')
    stocks=masters.findall('.//STOCKITEM')
    assert len(stocks)==2 and len({s.attrib['NAME'] for s in stocks})==2
    assert {s.findtext('BASEUNITS') for s in stocks}=={'PCS','BOX'}
    assert {e.findtext('STOCKITEMNAME') for e in sales.findall('.//ALLINVENTORYENTRIES.LIST')}=={s.attrib['NAME'] for s in stocks}


def test_zero_gst_has_no_tax_posting_and_retained_history_is_unchanged(tmp_path):
    rows=sources(tmp_path)[:1]
    normal=process_sources(tmp_path)
    prior_guids={v.findtext('VOUCHERNUMBER'):v.findtext('GUID') for v in ET.parse(Path(normal[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER')}
    retained={str(p):p.read_bytes() for p in (tmp_path/'.invoice_app/companies').rglob('*') if p.is_file()}
    enable(tmp_path,'Client')
    # Policy selects the separate exporter; it never writes company history.
    processed=process_sources(tmp_path)
    assert all(Path(p).read_bytes()==content for p,content in retained.items())
    new_guids={v.findtext('VOUCHERNUMBER'):v.findtext('GUID') for v in ET.parse(Path(processed[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER')}
    assert prior_guids==new_guids
    rows[0]['invoice'].update(cgst='0',sgst='0',igst='0',cess='0',round_off='0')
    output=export_all(tmp_path,rows,False)
    xml=ET.parse(Path(output[0]['output_path'])/'Sales_Vouchers.xml')
    assert not {'CGST','SGST','IGST','Cess'} & {e.findtext('LEDGERNAME') for e in xml.findall('.//ALLLEDGERENTRIES.LIST')}
    assert rows[0]['invoice']['cgst']=='0'


def test_clients_and_sellers_stay_separate(tmp_path):
    rows=sources(tmp_path)[:3]
    rows[1]['invoice']['seller_name']='Other seller';rows[2]['client']='Other client'
    export_all(tmp_path,rows,True)
    assert rows[0]['output_path']==rows[1]['output_path']
    assert rows[0]['group_output_path']!=rows[1]['group_output_path']
    assert rows[0]['output_path']!=rows[2]['output_path']


@pytest.mark.parametrize('unexpected',[False,True])
def test_all_apis_unavailable_uses_python_for_every_invoice(tmp_path,monkeypatch,unexpected):
    scanned=sources(tmp_path)
    monkeypatch.delenv('GEMINI_API_KEY',raising=False);monkeypatch.delenv('GROQ_API_KEY',raising=False)
    calls=[]
    def batch(root,records,provider,**kwargs):
        calls.append(provider)
        if unexpected:raise RuntimeError('private diagnostic content must not be exposed')
        return [{'status':'failed','error':'No configured key'} for r in records]
    result=read_with_fallback(tmp_path,scanned,batch_reader=batch)
    assert calls==['Gemini'] and all(r['provider']=='Python' for r in result)
    assert 'private diagnostic content' not in json.dumps(result)
    processed=process_sources(tmp_path)
    assert len(ET.parse(Path(processed[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER'))==20

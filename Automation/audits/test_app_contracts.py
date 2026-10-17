"""Independent acceptance audit of the shipped app; failing checks are findings.

Run explicitly: python -m pytest Automation/audits/test_app_contracts.py -q
No runtime code is patched. All documents/masters are synthetic. All network
connections are forbidden; controlled AI/Tally responses are clearly labelled.
"""
from copy import deepcopy
from decimal import Decimal,ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import hashlib,json,random,runpy,socket,sys
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from Document_Upload import upload_documents,image_pdf
from Common_Rules.tally_review_export import export_all,verify_vouchers
from Common_Rules.tally_master_matching import bind_snapshot,context,save_choices,assignments,MARKER
from Common_Rules.tally_import import import_plan,client_import_groups,send_plan
from Tally_Master_Snapshot import parse_collection,save_snapshot
from Export_Refund_Review import summary as refund_summary


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def blocked(*args,**kwargs):raise AssertionError('Audit forbids all live network/API/Tally connections')
    monkeypatch.setattr(socket,'create_connection',blocked)
    monkeypatch.setattr(socket.socket,'connect',blocked)
    for name in ('GROQ_API_KEY','GEMINI_API_KEY','GITHUB_MODELS_TOKEN','OPENROUTER_API_KEY'):
        monkeypatch.delenv(name,raising=False)


def cents(value):return Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def record(root,number='AUD-001'):
    invoice={'number':number,'date':'2026-10-17','seller_name':'Alpha Office Supplies','seller_gstin':'27ABCDE1234F1Z5',
        'buyer_name':'Beta Retail Stores','buyer_gstin':'27PQRSX5678L1ZW','seller_state':'27','buyer_state':'27',
        'seller_address':'1 Office Road, Mumbai','buyer_address':'2 Retail Road, Mumbai',
        'currency':'INR','classification':'taxable','supply':'INTRA','place_of_supply':'27',
        'taxable':'200.00','total':'236.00','cgst':'18.00','sgst':'18.00','igst':'0','cess':'0','round_off':'0',
        'items':[{'name':name,'hsn':hsn,'quantity':qty,'unit':'PCS','rate':rate,'value':'100.00',
                  'cgst_rate':'9','sgst_rate':'9','igst_rate':'0'}
                 for name,hsn,qty,rate in [('Blue pen','960810','10','10.00'),('Pencil','960910','5','20.00')]]}
    invoice['seller_gstin']='27ABCDE1234F1Z0'  # Synthetic, checksum-valid test identity.
    return {'client':'Client','path':str(root/(number+'.pdf')),'digest':hashlib.sha256(number.encode()).hexdigest(),'invoice':invoice,'errors':[]}


def bind(root,row,party='Buyer ledger',unit='Pcs',precision=3,rates=('9','9','18'),uqc='PCS-PIECES'):
    ledger=ET.Element('LEDGER',NAME=party)
    ET.SubElement(ledger,'PARENT').text='Sundry Debtors';ET.SubElement(ledger,'PARTYGSTIN').text=row['invoice']['buyer_gstin']
    stock=ET.Element('STOCKITEM',NAME='Blue pen');ET.SubElement(stock,'BASEUNITS').text=unit
    rule=ET.SubElement(stock,'GSTDETAILS.LIST');ET.SubElement(rule,'HSNCODE').text='960810';ET.SubElement(rule,'TAXABILITY').text='Taxable'
    for head,rate in zip(('Central Tax','State Tax','Integrated Tax'),rates):
        detail=ET.SubElement(rule,'RATEDETAILS.LIST');ET.SubElement(detail,'GSTRATEDUTYHEAD').text=head;ET.SubElement(detail,'GSTRATE').text=rate
    un=ET.Element('UNIT',NAME=unit)
    for tag,value in [('ISSIMPLEUNIT','Yes'),('GSTREPUOM',uqc),('DECIMALPLACES',str(precision))]:ET.SubElement(un,tag).text=value
    snapshot={'company':'Audit Tally Company','mode':'review_only'}
    for kind,node in [('ledgers',ledger),('stock_items',stock),('units',un)]:
        snapshot[kind]=parse_collection(b'<ENVELOPE><COLLECTION>'+ET.tostring(node)+b'</COLLECTION></ENVELOPE>',kind)
    snapshot['counts']={k:len(snapshot[k]) for k in ('ledgers','stock_items','units')}
    bind_snapshot(root,'Client',save_snapshot(root,snapshot));return context(root,row)


def pick(id):return {'id':id,'confidence':.99,'reason':'Explicit controlled AI selection for audit.'}
def choices():return {'party':pick('L0'),'items':[{'index':0,'stock':pick('S0'),'unit':pick('U0')}]}
def docs(root,rows):
    export_all(root,rows,False);folder=Path(rows[0]['output_path'])
    return folder,{name:ET.parse(folder/(name+'.xml')).getroot() for name in ('Units','Masters','Sales_Vouchers')}


@pytest.mark.parametrize('mode',['INTRA','INTER','EXEMPT','EXPORT_LUT','EXPORT_IGST'])
def test_decimal_oracle_100_invoices_per_tax_treatment(tmp_path,mode,record_property):
    """500 controlled invoices; expected amounts are calculated outside the writer."""
    rng=random.Random(1049);rows=[];expected={}
    for index in range(100):
        row=record(tmp_path,f'AUD-{mode}-{index:03}');inv=row['invoice']
        for item in inv['items']:
            item['quantity']=str(Decimal(rng.randint(1,800))/4)
            item['rate']=str(Decimal(rng.randint(1,100000))/100)
            item['value']=str(cents(Decimal(item['quantity'])*Decimal(item['rate'])))
            rates=('9','9','0') if mode=='INTRA' else ('0','0','18') if mode in ('INTER','EXPORT_IGST') else ('0','0','0')
            for tax,rate in zip(('cgst','sgst','igst'),rates):item[tax+'_rate']=rate
        taxable=sum(Decimal(i['value']) for i in inv['items'])
        cgst=cents(taxable*Decimal('.09')) if mode=='INTRA' else Decimal(0)
        sgst=cgst;igst=cents(taxable*Decimal('.18')) if mode in ('INTER','EXPORT_IGST') else Decimal(0)
        rounding=Decimal(rng.choice(['-.49','0','.49']));total=taxable+cgst+sgst+igst+rounding
        inv.update(taxable=str(taxable),cgst=str(cgst),sgst=str(sgst),igst=str(igst),round_off=str(rounding),total=str(total))
        if mode=='INTER':inv.update(supply='INTER',place_of_supply='29')
        if mode=='EXEMPT':inv.update(supply='EXEMPT',classification='exempt')
        if mode.startswith('EXPORT'):
            inv.update(supply='EXPORT',classification='export_lut' if mode=='EXPORT_LUT' else 'export_igst',
                       buyer_country='United Kingdom',place_of_supply='Outside India')
        expected[inv['number']]={'invoice':deepcopy(inv),'total':total,'taxable':taxable,'CGST':cgst,'SGST':sgst,'IGST':igst,'Round Off':rounding}
        rows.append(row)
    _,documents=docs(tmp_path,rows);vouchers=documents['Sales_Vouchers'].findall('.//VOUCHER')
    assert len(vouchers)==100
    for voucher in vouchers:
        oracle=expected[voucher.findtext('VOUCHERNUMBER')]
        entries=voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST')
        party=next(n for n in entries if n.findtext('ISPARTYLEDGER')=='Yes')
        assert Decimal(party.findtext('AMOUNT'))==-oracle['total']
        posted={n.findtext('LEDGERNAME'):Decimal(n.findtext('AMOUNT')) for n in entries if n is not party}
        for tax in ('CGST','SGST','IGST','Round Off'):assert posted.get(tax,Decimal(0))==oracle[tax]
        inventory=voucher.findall('ALLINVENTORYENTRIES.LIST')
        if mode.startswith('EXPORT'):assert not inventory and posted['Sales']==oracle['taxable']
        else:
            assert len(inventory)==2
            for node,item in zip(inventory,oracle['invoice']['items']):
                assert Decimal(node.findtext('AMOUNT'))==Decimal(item['value'])
                assert Decimal(node.findtext('ACTUALQTY').removesuffix(' PCS'))==Decimal(item['quantity'])
                assert Decimal(node.findtext('RATE').removesuffix('/PCS'))==Decimal(item['rate'])
    assert [r['invoice'] for r in rows]==[expected[r['invoice']['number']]['invoice'] for r in rows]
    before=[v.findtext('GUID') for v in vouchers];docs(tmp_path,rows)
    after=ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER')
    assert before==[v.findtext('GUID') for v in after]
    record_property('controlled_invoice_cases',100)


@pytest.mark.parametrize('party',['Sales','CGST','SGST','IGST','Round Off'])
def test_matched_buyer_cannot_take_a_system_ledger_name(tmp_path,party):
    row=record(tmp_path);ctx=bind(tmp_path,row,party=party)
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    _,documents=docs(tmp_path,[row]);voucher=documents['Sales_Vouchers'].find('.//VOUCHER')
    assert voucher.findtext('PARTYLEDGERNAME')!=party,'Buyer reused the reserved '+party+' ledger, so party/sales/tax roles collide.'


@pytest.mark.parametrize('rates',[('8','10','18'),('10','8','18'),('0','18','18')])
def test_equal_total_gst_does_not_hide_conflicting_components(tmp_path,rates):
    row=record(tmp_path);ctx=bind(tmp_path,row,rates=rates)
    save_choices(tmp_path,row,ctx,row['invoice'],choices())
    assert assignments(tmp_path,row,ctx)['items'][0]['stock'] is None,'Invoice requires CGST 9 + SGST 9; imported components are '+str(rates)


def test_external_unit_precision_covers_every_item_not_only_the_ai_matched_item(tmp_path):
    row=record(tmp_path);inv=row['invoice'];inv['items'][1].update(quantity='5.5',value='110.00')
    for item in inv['items']:item['unit']='KG'
    inv.update(taxable='210.00',cgst='18.90',sgst='18.90',total='247.80')
    ctx=bind(tmp_path,row,unit='KG',precision=0,uqc='KGS-KILOGRAMS');raw=choices();raw['items'][0]['stock']=None
    save_choices(tmp_path,row,ctx,inv,raw)
    try:_,documents=docs(tmp_path,[row])
    except ValueError as exc:
        assert 'decimal places' in str(exc) and 'not rounded' in str(exc)
        return  # Holding incompatible XML is safer than rounding a quantity.
    external=json.loads(documents['Units'].get(MARKER))['units']
    definitions={n.findtext('NAME') or n.get('NAME'):int(n.findtext('DECIMALPLACES')) for n in documents['Units'].findall('.//UNIT')}
    for item in documents['Sales_Vouchers'].findall('.//ALLINVENTORYENTRIES.LIST'):
        qty,symbol=item.findtext('ACTUALQTY').rsplit(' ',1)
        precision=definitions.get(symbol,0 if symbol in external else -1)
        required=max(0,-Decimal(qty).normalize().as_tuple().exponent)
        assert precision>=required,'Shared external unit '+symbol+' supports '+str(precision)+' decimals, but '+qty+' needs '+str(required)


def test_duplicate_business_invoice_with_different_source_bytes_requires_review(tmp_path):
    first=record(tmp_path);second=deepcopy(first)
    second.update(path=str(tmp_path/'rescanned.pdf'),digest=hashlib.sha256(b'same printed invoice; different PDF metadata').hexdigest())
    try:folder,documents=docs(tmp_path,[first,second])
    except ValueError:return  # explicit duplicate rejection is also acceptable
    vouchers=documents['Sales_Vouchers'].findall('.//VOUCHER')
    report=json.loads((folder/'Batch_Report.json').read_text())
    warnings=' '.join(w for r in report['invoices'] for w in r['warnings']).casefold()
    assert len(vouchers)==1 or 'duplicate' in warnings,'Same seller/date/invoice number produced two distinct GUIDs without duplicate review.'


@pytest.mark.parametrize('currency',['USD','AED','EUR'])
def test_refund_estimate_is_not_labelled_inr_for_unconverted_foreign_currency(tmp_path,currency):
    row=record(tmp_path);row['invoice'].update(currency=currency,supply='EXPORT',classification='export_igst',buyer_country='United Kingdom',place_of_supply='Outside India',taxable='100',total='118',igst='18',cgst='0',sgst='0')
    assert refund_summary(row)['estimate'] is None,'Foreign-currency IGST was shown as an INR refund reference without conversion evidence.'


def test_source_installer_rolls_back_if_a_write_fails_mid_install(tmp_path,monkeypatch):
    import zipfile
    installer=runpy.run_path(str(Path(__file__).resolve().parents[2]/'Install_BillSync_Source.py'))
    root=tmp_path/'app';root.mkdir()
    with zipfile.ZipFile(Path(__file__).resolve().parents[2]/'Backups/Before_Tally_Master_Matching.zip') as previous:
        for name in installer['ENGINE']:
            source=Path(__file__).resolve().parents[1]/name;target=root/name
            data=previous.read('Automation/'+name) if 'Automation/'+name in previous.namelist() else source.read_bytes()
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        (root/'BillSync_UI.py').write_bytes(previous.read('Automation/BillSync_UI.py'))
    before={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    write=Path.write_bytes
    def fail(path,data):
        if path==root/'BillSync_Controls.py':raise OSError('Injected disk/file-write failure')
        return write(path,data)
    monkeypatch.setattr(Path,'write_bytes',fail)
    with pytest.raises(OSError):installer['install'](root)
    after={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file() and '.invoice_app' not in p.relative_to(root).parts}
    assert before==after,'Installer left a mixture of new and old code after a failed write; backup exists but automatic rollback did not occur.'


def test_bad_pdf_header_is_not_sufficient_proof_of_a_valid_upload(tmp_path):
    source=tmp_path/'broken.pdf';source.write_bytes(b'%PDF-1.7\nnot a PDF object tree or trailer')
    result=upload_documents(tmp_path/'app','Client',[source])
    assert result['errors'] and not result['uploaded'],'A corrupt PDF with a signature was accepted as an uploaded document.'


def invoice_pdf(invoice,layout):
    from reportlab.pdfgen.canvas import Canvas
    output=BytesIO();canvas=Canvas(output,pagesize=(740,1000),invariant=1);canvas.setFont('Courier',10)
    if layout=='paired':
        parties=['SELLER / SUPPLIER                                  BUYER / RECIPIENT',
                 'Alpha Office Supplies                              Beta Retail Stores',
                 'GSTIN: 27ABCDE1234F1Z0                              GSTIN: 27PQRSX5678L1ZW',
                 'State: Maharashtra                                 State: Maharashtra']
    else:
        parties=['SUPPLIER','Alpha Office Supplies','GSTIN: 27ABCDE1234F1Z0','State: Maharashtra',
                 'BILL TO','Beta Retail Stores','GSTIN: 27PQRSX5678L1ZW','State: Maharashtra']
    rows=['SALES INVOICE',*parties,'Invoice Number: '+invoice['number'],'Date: 17/10/2026','Supply: INTRA','Place of Supply: Maharashtra','Currency: INR']
    if layout=='reordered':
        rows+=['HSN | Description | Unit | Quantity | Rate | Taxable Value | GST %',
               '960810 | Blue pen | PCS | 10 | 10.00 | 100.00 | 18',
               '960910 | Pencil | PCS | 5 | 20.00 | 100.00 | 18']
    else:
        rows+=['Description | HSN | Qty | UOM | Rate | Taxable Value | GST %',
               'Blue pen | 960810 | 10 | PCS | 10.00 | 100.00 | 18',
               'Pencil | 960910 | 5 | PCS | 20.00 | 100.00 | 18']
    rows+=['Taxable Value: 200.00','CGST: 18.00','SGST: 18.00','IGST: 0.00','Grand Total: 236.00']
    for index,line in enumerate(rows):canvas.drawString(24,960-index*24,line)
    canvas.showPage();canvas.save();return output.getvalue()


@pytest.mark.parametrize('layout',['stacked','paired','reordered'])
@pytest.mark.parametrize('kind',['pdf','png','jpg','jpeg'])
def test_real_upload_text_ocr_controlled_ai_xml_and_cache_end_to_end(tmp_path,monkeypatch,layout,kind,record_property):
    """Actual upload/OCR/writer; known fixture response, NOT measured AI accuracy."""
    import pypdfium2 as pdfium
    from Common_Rules import groq_reader
    from Common_Rules.ai_first import run_ai_first
    from Common_Rules.gemini_reader import FIELDS,ITEM_FIELDS
    oracle=record(tmp_path,'AUD-2026-101')['invoice'];raw_pdf=invoice_pdf(oracle,layout)
    source=tmp_path/('document.'+kind)
    if kind=='pdf':source.write_bytes(raw_pdf)
    else:
        with pdfium.PdfDocument(raw_pdf) as pdf:
            page=pdf[0];bitmap=page.render(scale=2)
            try:image=bitmap.to_pil().convert('RGB').copy()
            finally:bitmap.close();page.close()
        image.save(source,format='PNG' if kind=='png' else 'JPEG',quality=96)
    original=source.read_bytes();root=tmp_path/'app';uploaded=upload_documents(root,'Client',[source])
    assert not uploaded['errors'] and len(uploaded['uploaded'])==1 and not list(root.rglob('*.xml'))
    path=uploaded['uploaded'][0]['path'];calls=[];missing=[]
    def ai(payload,key,model):
        calls.append(payload);text=payload['messages'][1]['content']
        compact=''.join(c for c in text.casefold() if c.isalnum())
        for token in ('Alpha Office Supplies','Beta Retail Stores','Blue pen','Pencil','236.00','AUD-2026-101'):
            if ''.join(c for c in token.casefold() if c.isalnum()) not in compact:missing.append(token)
        return {**{k:v for k,v in oracle.items() if k in FIELDS},'items':[{k:v for k,v in i.items() if k in ITEM_FIELDS} for i in oracle['items']]}
    monkeypatch.setenv('GROQ_API_KEY','offline-audit-placeholder')
    monkeypatch.setattr(groq_reader,'request_invoice',ai)
    rows,summary=run_ai_first(root,False,['Client'],primary='Groq',selected_paths=[path],max_new_requests=1)
    assert len(calls)==1 and summary['new_ai_attempts']==1 and len(rows)==1
    assert summary['ai_read_invoices']==1,'Controlled AI result must succeed rather than silently testing local fallback.'
    voucher=ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml').find('.//VOUCHER')
    assert voucher.findtext('VOUCHERNUMBER')=='AUD-2026-101' and voucher.findtext('DATE')=='20261017'
    entries=voucher.findall('LEDGERENTRIES.LIST');party=next(n for n in entries if n.findtext('ISPARTYLEDGER')=='Yes')
    assert Decimal(party.findtext('AMOUNT'))==Decimal('-236.00')
    assert [(n.findtext('STOCKITEMNAME'),Decimal(n.findtext('AMOUNT'))) for n in voucher.findall('ALLINVENTORYENTRIES.LIST')]==[('Blue pen',Decimal('100')),('Pencil',Decimal('100'))]
    assert source.read_bytes()==original
    _,again=run_ai_first(root,False,['Client'],primary='Groq',selected_paths=[path],max_new_requests=1)
    assert again['new_ai_attempts']==0 and len(calls)==1
    record_property('ocr_exact_missing_tokens',json.dumps(missing))


@pytest.mark.parametrize('layout',['stacked','paired','reordered'])
@pytest.mark.parametrize('kind',['png','jpg','jpeg'])
def test_raster_input_exact_text_fidelity_before_ai(tmp_path,layout,kind):
    """A strict OCR-input check, deliberately separate from AI/XML transfer."""
    import pypdfium2 as pdfium
    from Common_Rules.groq_reader import prepare_invoice_payload
    raw=invoice_pdf(record(tmp_path,'AUD-2026-101')['invoice'],layout)
    with pdfium.PdfDocument(raw) as pdf:
        page=pdf[0];bitmap=page.render(scale=2)
        try:image=bitmap.to_pil().convert('RGB').copy()
        finally:bitmap.close();page.close()
    source=tmp_path/('scan.'+kind);image.save(source,format='PNG' if kind=='png' else 'JPEG',quality=96)
    root=tmp_path/'app';result=upload_documents(root,'Client',[source]);path=Path(result['uploaded'][0]['path'])
    payload=prepare_invoice_payload({'path':str(path),'digest':hashlib.sha256(path.read_bytes()).hexdigest()},'offline-audit')
    compact=''.join(c for c in payload['messages'][1]['content'].casefold() if c.isalnum())
    required=('Alpha Office Supplies','Beta Retail Stores','Blue pen','Pencil','236.00','AUD-2026-101')
    missing=[token for token in required if ''.join(c for c in token.casefold() if c.isalnum()) not in compact]
    assert not missing,'OCR exact-text loss before any AI response: '+str(missing)


@pytest.mark.parametrize('stage',['Units.xml','Masters.xml','Sales_Vouchers.xml'])
def test_connection_loss_at_each_import_stage_never_retries_or_rewrites_xml(tmp_path,stage):
    row=record(tmp_path);folder,documents=docs(tmp_path,[row]);plan=import_plan(folder)
    before={name:(folder/name).read_bytes() for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}
    requests=[];failed=[False]
    def transport(data):
        doc=ET.fromstring(data)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':return b'<ENVELOPE><COLLECTION><COMPANY NAME="Audit Company"/></COLLECTION></ENVELOPE>'
        name='Sales_Vouchers.xml' if doc.findall('.//VOUCHER') else 'Units.xml' if doc.findall('.//UNIT') else 'Masters.xml'
        requests.append(name)
        if name==stage:
            assert not failed[0],'Ambiguous import request was retried'
            failed[0]=True;raise OSError('Injected lost connection after '+name+' request')
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS><EXCEPTIONS>0</EXCEPTIONS></RESPONSE>'
    results=send_plan(plan,'Audit Company',transport,submit_all=True)
    assert failed[0] and requests[-1]==stage and results[-1]['status']=='unknown'
    assert before=={name:(folder/name).read_bytes() for name in before}


def test_failed_export_publication_restores_previous_current_xml(tmp_path,monkeypatch):
    row=record(tmp_path);folder,_=docs(tmp_path,[row]);before={p.name:p.read_bytes() for p in folder.glob('*.xml')}
    original=Path.rename
    def fail(path,target):
        if path.name.startswith('.staging-') and Path(target).name=='current':raise OSError('Injected publication failure')
        return original(path,target)
    monkeypatch.setattr(Path,'rename',fail)
    row['invoice']['number']='UPDATED'
    with pytest.raises(OSError):export_all(tmp_path,[row],False)
    assert folder.is_dir() and before=={p.name:p.read_bytes() for p in folder.glob('*.xml')}


@pytest.mark.parametrize('currency',['USD','AED','EUR'])
def test_unconverted_foreign_invoice_does_not_silently_post_as_base_currency(tmp_path,currency):
    row=record(tmp_path);row['invoice'].update(currency=currency,supply='EXPORT',classification='export_igst',
        buyer_country='United Kingdom',place_of_supply='Outside India',cgst='0',sgst='0',igst='36')
    for item in row['invoice']['items']:item.update(cgst_rate='0',sgst_rate='0',igst_rate='18')
    try:folder,documents=docs(tmp_path,[row])
    except ValueError:return
    report=json.loads((folder/'Batch_Report.json').read_text())
    warnings=' '.join(w for entry in report['invoices'] for w in entry['warnings']).casefold()
    assert any(word in warnings for word in ('currency','exchange','conversion')),'Non-INR invoice values posted as unqualified numeric amounts with no conversion evidence or currency warning.'


def test_oversized_input_is_rejected_before_reading_payload(tmp_path,monkeypatch):
    source=tmp_path/'large.pdf'
    with source.open('wb') as file:file.truncate(100*1024*1024+1)
    original=Path.read_bytes
    def read(path):
        assert path!=source,'Oversized input payload was read into memory'
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    result=upload_documents(tmp_path/'app','Client',[source])
    assert len(result['errors'])==1 and not result['uploaded'] and '100 MB' in result['errors'][0]['error']


def test_multi_frame_png_is_rejected_without_losing_other_valid_file(tmp_path):
    from PIL import Image
    source=tmp_path/'animated.png';Image.new('RGB',(40,40),'red').save(source,save_all=True,append_images=[Image.new('RGB',(40,40),'blue')])
    good=tmp_path/'valid.pdf';good.write_bytes(invoice_pdf(record(tmp_path)['invoice'],'stacked'))
    result=upload_documents(tmp_path/'app','Client',[source,good])
    assert len(result['errors'])==1 and len(result['uploaded'])==1


def test_linked_upload_directory_cannot_write_outside_app_storage(tmp_path):
    from Document_Upload import client_folder
    from Common_Rules.engine import INBOX
    root=tmp_path/'app';folder=client_folder(root,'Client');folder.mkdir(parents=True)
    outside=tmp_path/'outside';outside.mkdir();(folder/INBOX).symlink_to(outside,target_is_directory=True)
    source=tmp_path/'valid.pdf';source.write_bytes(invoice_pdf(record(tmp_path)['invoice'],'stacked'))
    result=upload_documents(root,'Client',[source])
    assert result['errors'] and not result['uploaded'] and not list(outside.iterdir())


def test_xml_escapes_special_characters_without_changing_financial_values(tmp_path):
    row=record(tmp_path);row['invoice']['buyer_name']='Buyer & Sons <West>'
    row['invoice']['items'][0]['name']='Pen <Blue> & Black'
    _,documents=docs(tmp_path,[row]);voucher=documents['Sales_Vouchers'].find('.//VOUCHER')
    assert voucher.findtext('BASICBUYERNAME')=='Buyer & Sons <West>'
    assert voucher.findtext('.//STOCKITEMNAME')=='Pen <Blue> & Black'
    assert Decimal(voucher.findtext('.//ALLINVENTORYENTRIES.LIST/AMOUNT'))==Decimal('100')

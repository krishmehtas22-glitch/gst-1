from datetime import datetime, timezone
import hashlib
from pathlib import Path
from reportlab.pdfgen import canvas
from openpyxl import Workbook

from Common_Rules.engine import init_client, read_json, write_json


def gstin(code='27', pan='ABCDE1234F'):
    base = code + pan + '1Z'
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for i, char in enumerate(base):
        value = alphabet.index(char) * (1 if i % 2 == 0 else 2)
        total += value // 36 + value % 36
    return base + alphabet[(36 - total % 36) % 36]


def client(root, name='Client 1', mode='new'):
    root.mkdir(exist_ok=True)
    return init_client(root,name,name + ' Company',gstin(),mode)


def invoice(number='INV-001', kind='intra', name=None):
    interstate = kind == 'inter'
    exempt = kind == 'exempt'
    buyer_code = '29' if interstate else '27'
    return {'number':number,'date':'2026-04-01','seller_name':'Dummy Seller', 'seller_gstin':gstin(),
            'buyer_name':'Dummy Customer ' + buyer_code, 'buyer_gstin':gstin(buyer_code, 'PQRSX5678L'),
            'buyer_registration':'Regular','buyer_state':buyer_code,'place_of_supply':buyer_code,
            'classification':'exempt' if exempt else 'taxable','taxable':'2000','total':'2000' if exempt else '2360',
            'cgst':'180' if kind == 'intra' else '0','sgst':'180' if kind == 'intra' else '0','igst':'360' if interstate else '0',
            'items':[{'name':name or ('Product ' + kind),'hsn':'8418','quantity':'2','unit':'Nos','rate':'1000','value':'2000',
                      'cgst_rate':'9' if kind == 'intra' else '0','sgst_rate':'9' if kind == 'intra' else '0','igst_rate':'18' if interstate else '0'}]}


def pdf(path, inv):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = canvas.Canvas(str(path))
    lines = [f'Invoice No: {inv["number"]}',f'Invoice Date: {inv["date"]}',f'Seller: {inv["seller_name"]}',
             f'Seller GSTIN: {inv["seller_gstin"]}',f'Buyer: {inv["buyer_name"]}',f'Buyer GSTIN: {inv["buyer_gstin"]}',
             f'Buyer Registration: {inv["buyer_registration"]}',f'Buyer State: {inv["buyer_state"]}',
             f'Place of Supply: {inv["place_of_supply"]}',f'Tax Treatment: {inv["classification"]}',
             f'Taxable Value: {inv["taxable"]}',f'CGST: {inv["cgst"]}',f'SGST: {inv["sgst"]}',
             f'IGST: {inv["igst"]}',f'Grand Total: {inv["total"]}',
             'Item | HSN | Qty | Unit | Rate | Value | CGST % | SGST % | IGST %']
    if 'round_off' in inv:
        lines.insert(-1,f'Round Off: {inv["round_off"]}')
    for item in inv['items']:
        lines.append(' | '.join(item[field] for field in ('name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate')))
    out.setFont('Helvetica', 8)
    for n, line in enumerate(lines):
        out.drawString(25, 810 - n * 16, line)
    out.save()


def write_snapshot(path, config, vouchers=None, masters=None):
    write_json(path, {'company_id':config['company_id'],'seller_gstin':config['seller_gstin'],
                     'exported_at':datetime.now(timezone.utc).isoformat(),'complete':True,
                     'vouchers':vouchers or [],'masters':masters or []})


def fake_templates(root):
    """SYNTHETIC fixtures, created in temp tests only; not official Tally sources."""
    for path in root.glob('*/client.json'):
        config = read_json(path)
        config['output_format'] = 'excel'
        write_json(path,config)
    folder = root / 'Common_Rules' / 'templates'
    folder.mkdir(parents=True)
    reg = {}
    for kind in ('unit','ledger','stock_item','stock_group','sales'):
        book = Workbook()
        sheet = book.active
        sheet.title = 'Synthetic Data'
        sheet.append(['Test Identifier','Test Value'])
        sheet.append(['sample','erase this'])
        sheet.append(['sample 2','erase this also'])
        readme = book.create_sheet('ReadMe')
        readme['A1'] = 'SYNTHETIC TEST FIXTURE. NOT A TALLY TEMPLATE.'
        source = folder / f'{kind}.xlsx'
        book.save(source)
        mapping = folder / f'{kind}.xml'
        mapping.write_text('<synthetic-test-only />')
        reg[kind] = {'file':source.name,'source_url':'https://help.tallysolutions.com/synthetic-test-fixture',
             'sha256':hashlib.sha256(source.read_bytes()).hexdigest(), 'mapping_file':mapping.name,
             'mapping_sha256':hashlib.sha256(mapping.read_bytes()).hexdigest(),
             'verified':True,'reviewed_by':'Automated synthetic adapter test; no Tally certification',
             'blocks':[{'sheet':'Synthetic Data','header_row':1,'headers':['Test Identifier','Test Value'],
                        'data_start_row':2,'sample_end_row':3,'mandatory_headers':['Test Identifier'],
                        'stream':'invoices' if kind == 'sales' else 'masters',
                        'columns':{'Test Identifier':'number' if kind == 'sales' else 'name',
                                   'Test Value':'total' if kind == 'sales' else 'kind'}}]}
    write_json(folder / 'registry.json', reg)
    return folder, reg

from pathlib import Path
from decimal import Decimal
import shutil
import xml.etree.ElementTree as ET
from pypdf import PdfReader
from Common_Rules.desktop import process_sources
from Common_Rules.accounting import money

FIXTURES=Path(__file__).parent/'fixtures/client24'


def test_four_layouts_read_all_source_rows_and_taxes(tmp_path):
    shutil.copytree(FIXTURES,tmp_path/'New20');rows=process_sources(tmp_path)
    assert len(rows)==20 and all(not r['errors'] for r in rows),[r['errors'] for r in rows]
    assert sum(len(r['invoice']['items']) for r in rows)==38
    sources={}
    for r in rows:
        lines=[s.strip() for s in PdfReader(r['path']).pages[0].extract_text().splitlines() if s.strip()]
        inv=r['invoice'];assert inv['seller_name']==lines[1]
        assert inv['seller_gstin']=='27ABCDE1234F1Z5'
        assert inv['number'] in lines or any(inv['number'] in line for line in lines)
        for label,offset in [('BILL TO',1),('CUSTOMER / SHIP TO',2),('CUSTOMER NAME',1),('CUSTOMER',1)]:
            if label in lines:
                assert inv['buyer_name']==lines[lines.index(label)+offset];break
        else:raise AssertionError('No buyer anchor')
        start=next(i for i,line in enumerate(lines) if line in ('Amount (INR)','Net amount','Line value','Amount'))+1
        end=next(i for i,line in enumerate(lines) if line in ('Sub-total / supply value','Amount before tax'))
        stride=7 if 'S.No' in lines else 6;cells=lines[start:end];assert len(cells)%stride==0
        items=[cells[i:i+stride] for i in range(0,len(cells),stride)]
        assert len(items)==len(inv['items'])
        for expected,actual in zip(items,inv['items']):
            if stride==7:expected=expected[1:]
            if lines[0]=='INVOICE / SALES':expected=[expected[1],expected[0],*expected[2:]]
            assert actual['name']==expected[0] and actual['hsn']==expected[1]
            for key,value in zip(('quantity','rate','gst_rate','value'),expected[2:]):assert money(actual[key])==money(value.rstrip('%*'))
        labels={'taxable':('Sub-total / supply value','Amount before tax'),'cgst':('Central GST (CGST)','CGST amount'),'sgst':('State GST (SGST)','SGST amount'),'igst':('Integrated GST (IGST)','IGST amount'),'total':('INVOICE TOTAL (INR)','TOTAL PAYABLE')}
        amounts={key:money(lines[next(lines.index(label) for label in candidates if label in lines)+1]) for key,candidates in labels.items()}
        for key,value in amounts.items():assert money(inv[key])==value
        sources[inv['number']]=amounts
    vouchers=ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml').findall('.//VOUCHER');assert len(vouchers)==20
    for v in vouchers:
        amounts=sources[v.findtext('VOUCHERNUMBER')];entries=v.findall('ALLLEDGERENTRIES.LIST')+v.findall('LEDGERENTRIES.LIST')
        assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')==v.findtext('PARTYLEDGERNAME'))==-amounts['total']
        for tax in ('cgst','sgst','igst'):assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')=='Output '+tax.upper())==amounts[tax]
        assert sum(money(e.findtext('AMOUNT')) for e in entries+v.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST'))==Decimal(0)

"""Actual colon-free invoice forms, including conflicting fictional buyers."""
from pathlib import Path
from decimal import Decimal
import shutil
import xml.etree.ElementTree as ET
from pypdf import PdfReader
from Common_Rules.desktop import process_sources
from Common_Rules.accounting import money
from Common_Rules.extraction import parse_text
from Common_Rules.masters import bind_demo_party_ledgers, plan_masters

FIXTURES=Path(__file__).parent/'fixtures/client23'


def printed(path):
    lines=[line.strip() for line in PdfReader(path).pages[0].extract_text().splitlines() if line.strip()]
    start=lines.index('Value (INR)')+1;end=lines.index('Taxable / exempt value')
    cells=lines[start:end];assert len(cells)%6==0
    items=[dict(zip(('name','hsn','quantity','rate','gst_rate','value'),cells[i:i+6])) for i in range(0,len(cells),6)]
    amounts={key:lines[lines.index(label)+1] for key,label in [('taxable','Taxable / exempt value'),('cgst','CGST'),('sgst','SGST'),('igst','IGST'),('total','GRAND TOTAL')]}
    return lines[lines.index('Invoice number')+1],lines[lines.index('Buyer')+1],items,amounts


def test_twenty_column_forms_generate_all_vouchers_and_exact_source_taxes(tmp_path):
    shutil.copytree(FIXTURES,tmp_path/'New20')
    rows=process_sources(tmp_path)
    assert len(rows)==20 and all(not r['errors'] for r in rows),[r['errors'] for r in rows]
    assert sum(len(r['invoice']['items']) for r in rows)==46
    sources={}
    for record in rows:
        inv=record['invoice'];number,buyer,items,amounts=printed(record['path'])
        assert inv['number']==number and inv['buyer_name']==buyer
        assert inv['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED'
        assert inv['currency']=='INR' and inv['dummy_document']
        assert len(inv['items'])==len(items)
        for actual,expected in zip(inv['items'],items):
            assert actual['name']==expected['name'] and actual['hsn']==expected['hsn']
            for field in ('quantity','rate','value'):assert money(actual[field])==money(expected[field])
            assert money(actual['gst_rate'])==money(expected['gst_rate'].rstrip('*'))
            assert actual['unit'] and actual['unit_auto']
        for field,value in amounts.items():assert money(inv[field])==money(value)
        assert not inv.get('tax_accounting_basis')
        sources[number]=(buyer,amounts)
    output=Path(rows[0]['output_path'])
    vouchers=ET.parse(output/'Sales_Vouchers.xml').findall('.//VOUCHER')
    assert len(vouchers)==20
    masters=ET.parse(output/'Required_Masters.xml').findall('.//LEDGER')
    master_names={m.get('NAME') for m in masters}
    for voucher in vouchers:
        buyer,amounts=sources[voucher.findtext('VOUCHERNUMBER')]
        assert voucher.findtext('PARTYNAME')==buyer
        ledger=voucher.findtext('PARTYLEDGERNAME')
        assert ledger in master_names and '[DEMO ' in ledger
        entries=voucher.findall('ALLLEDGERENTRIES.LIST')+voucher.findall('LEDGERENTRIES.LIST')
        assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')==ledger)==-money(amounts['total'])
        for tax in ('cgst','sgst','igst'):
            assert sum(money(e.findtext('AMOUNT')) for e in entries if e.findtext('LEDGERNAME')=='Output '+tax.upper())==money(amounts[tax])
        assert sum(money(e.findtext('AMOUNT')) for e in entries)+sum(money(e.findtext('AMOUNT')) for e in voucher.findall('ALLINVENTORYENTRIES.LIST/ACCOUNTINGALLOCATIONS.LIST'))==Decimal(0)
    first={v.findtext('VOUCHERNUMBER'):(v.findtext('GUID'),v.findtext('PARTYLEDGERNAME')) for v in vouchers}
    assert all(not r['errors'] for r in process_sources(tmp_path))
    assert first=={v.findtext('VOUCHERNUMBER'):(v.findtext('GUID'),v.findtext('PARTYLEDGERNAME')) for v in ET.parse(output/'Sales_Vouchers.xml').findall('.//VOUCHER')}


def test_footnote_rates_preserve_evidence_and_prose_does_not_become_supply():
    text=PdfReader(FIXTURES/'Sales_Invoice_139_EXPORT_LUT.pdf').pages[0].extract_text(extraction_mode='layout')
    inv=parse_text(text)
    assert inv['classification']=='export_lut' and inv['export_mode']=='LUT_without_payment'
    assert all(item['printed_gst_rate']=='0*' and item['gst_rate']=='0' for item in inv['items'])
    assert not inv['extraction_warnings']
    text=PdfReader(FIXTURES/'Sales_Invoice_126_INTRA.pdf').pages[0].extract_text(extraction_mode='layout')
    inv=parse_text(text)
    assert inv['supply']=='INTRA' and inv['classification']=='taxable'
    assert inv['buyer_name']=='Metro Retail LLP'
    assert not inv['extraction_warnings']


def test_fictional_ledger_binding_does_not_bypass_real_identity_conflicts(tmp_path):
    from Common_Rules.engine import read_json
    shutil.copytree(FIXTURES,tmp_path/'New20');rows=process_sources(tmp_path)
    company=Path(rows[0]['company_path']);config=read_json(company/'client.json')
    validated=read_json(company/'reports/validated_invoices.json')
    invoices={row['invoice_key']:{k:v for k,v in row['invoice'].items() if k!='buyer_ledger_name'} for row in validated}
    bound,mapping=bind_demo_party_ledgers(invoices,{**config,'demo_only':False},[],{})
    assert bound==invoices and not mapping
    _,errors=plan_masters(bound,config,[])
    assert len(errors)==20
    # New batches must retain previously generated ledger references.
    prior=read_json(company/'.automation/demo_party_ledgers.json')
    small={key:inv for key,inv in list(invoices.items())[:1]}
    rebound,updated=bind_demo_party_ledgers(small,config,[],prior)
    key=next(iter(small));sig=next(sig for sig,b in prior.items() if b['ledger']==validated[0]['invoice']['buyer_ledger_name'])
    assert rebound[key]['buyer_ledger_name']==prior[sig]['ledger']
    assert updated==prior

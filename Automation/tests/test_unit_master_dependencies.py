from copy import deepcopy
from pathlib import Path
from decimal import Decimal
import xml.etree.ElementTree as ET
from Common_Rules.tally_review_export import export_all


def records(root):
    inv={'number':'TEST-1','date':'2026-10-13','seller_name':'Western Trade Supplies','seller_gstin':'INVALID','buyer_name':'Buyer',
         'classification':'taxable','supply':'INTRA','taxable':'100','total':'118','cgst':'9','sgst':'9','igst':'0','round_off':'0','cess':'0'}
    items=[{'name':name,'unit':unit,'quantity':quantity,'rate':rate,'value':value,'hsn':'1234','cgst_rate':'9','sgst_rate':'9','igst_rate':'0'}
           for name,unit,quantity,rate,value in [('Cable clips','Nos','4','5','20'),('Fresh potatoes','KG','0.125','160','20'),('Steel utensils','SET','1','20','20'),('Packing tape','ROLL','2','10','20'),('Electrical switch','Nos','0.004','5000','20')]]
    inv['items']=items
    return [{'client':'Client','path':str(root/'invoice.pdf'),'digest':'a'*64,'invoice':inv,'errors':[]}]


def test_units_are_imported_separately_before_stock_and_vouchers(tmp_path):
    rows=records(tmp_path);export_all(tmp_path,rows,True)
    folder=Path(rows[0]['output_path'])
    units=ET.parse(folder/'Units.xml');masters=ET.parse(folder/'Masters.xml');sales=ET.parse(folder/'Sales_Vouchers.xml')
    defined={u.attrib['NAME']:u for u in units.findall('.//UNIT')}
    assert set(defined)=={'Nos','KG','SET','ROLL'}
    assert not units.findall('.//STOCKITEM') and not units.findall('.//LEDGER')
    assert not masters.findall('.//UNIT')
    assert defined['Nos'].findtext('ORIGINALNAME')=='Nos'
    assert defined['Nos'].findtext('ADDITIONALNAME')=='Numbers'
    assert defined['KG'].findtext('GSTREPUOM')=='KGS-KILOGRAMS'
    assert defined['ROLL'].findtext('GSTREPUOM')=='ROL-ROLLS'
    assert int(defined['Nos'].findtext('DECIMALPLACES'))>=3
    stocks={s.attrib['NAME']:s for s in masters.findall('.//STOCKITEM')}
    assert len(stocks)==5
    seen=set()
    for message in units.findall('.//TALLYMESSAGE'):
        seen.add(message.find('UNIT').attrib['NAME'])
    for message in masters.findall('.//TALLYMESSAGE'):
        stock=message.find('STOCKITEM')
        if stock is not None:assert stock.findtext('BASEUNITS') in seen
    for entry in sales.findall('.//ALLINVENTORYENTRIES.LIST'):
        stock=stocks[entry.findtext('STOCKITEMNAME')]
        unit=stock.findtext('BASEUNITS')
        assert entry.findtext('ACTUALQTY').endswith(' '+unit)
        assert entry.findtext('BILLEDQTY').endswith(' '+unit)
    notes=(folder/'Import_Instructions.txt').read_text()
    assert notes.index('1. Units.xml')<notes.index('2. Masters.xml')<notes.index('3. Sales_Vouchers.xml')


def test_fractional_quantities_and_high_precision_rates_are_not_rounded(tmp_path):
    rows=records(tmp_path)
    item=rows[0]['invoice']['items'][1]
    item.update(quantity='0.000125',rate='160000',value='20')
    export_all(tmp_path,rows,True)
    sales=ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml')
    entries=sales.findall('.//ALLINVENTORYENTRIES.LIST')
    mass=next(e for e in entries if e.findtext('STOCKITEMNAME').startswith('Fresh potatoes'))
    assert mass.findtext('ACTUALQTY')=='0.000125 KG' and mass.findtext('RATE')=='160000/KG'
    assert mass.findtext('AMOUNT')=='20.00'
    rate_item=rows[0]['invoice']['items'][0]
    rate_item.update(quantity='100000',rate='0.0002')
    export_all(tmp_path,rows,True)
    sales=ET.parse(Path(rows[0]['output_path'])/'Sales_Vouchers.xml')
    count=next(e for e in sales.findall('.//ALLINVENTORYENTRIES.LIST') if e.findtext('STOCKITEMNAME').startswith('Cable clips'))
    assert count.findtext('RATE')=='0.0002/Nos' and count.findtext('ACTUALQTY')=='100000 Nos'


def test_repair_run_preserves_source_quantities_stock_names_and_guids(tmp_path):
    rows=records(tmp_path);before=deepcopy(rows[0]['invoice'])
    export_all(tmp_path,rows,True)
    path=Path(rows[0]['output_path']);old=ET.parse(path/'Sales_Vouchers.xml')
    names=[n.text for n in old.findall('.//STOCKITEMNAME')];guid=old.findtext('.//GUID')
    export_all(tmp_path,rows,True)
    latest=Path(rows[0]['output_path']);new=ET.parse(latest/'Sales_Vouchers.xml')
    assert latest==path
    assert (latest.parent/'previous'/'Sales_Vouchers.xml').is_file()
    assert new.findtext('.//GUID')==guid and [n.text for n in new.findall('.//STOCKITEMNAME')]==names
    assert rows[0]['invoice']==before
    assert (latest/'Units.xml').exists() and len(new.findall('.//VOUCHER'))==1

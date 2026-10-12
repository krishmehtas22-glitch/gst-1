"""Tally native XML: dependency-ordered Create masters and item-invoice Sales.

Envelope, unit/master and inventory/ledger sign conventions are based on
https://help.tallysolutions.com/sample-xml/ . GST tags follow Tally's native
master fields; target-release GST report behavior needs a dummy-company import.
No Excel mapping or external template is used by this exporter.
"""
from decimal import Decimal
import uuid
import xml.etree.ElementTree as ET

from .accounting import STATES, TAXES, export_notice, accounting_entries, cents, money, sales_ledger
from .masters import identity, required_masters

HEADS = {'cgst':'Central Tax','sgst':'State Tax','igst':'Integrated Tax'}
TAXABILITY = {'taxable':'Taxable','exempt':'Exempt','nil_rated':'Nil Rated','non_gst':'Non-GST'}
UQC = {'NOS':'NOS-NUMBERS','PCS':'PCS-PIECES','KGS':'KGS-KILOGRAMS','GMS':'GMS-GRAMMES',
       'LTR':'LTR-LITRES','MTR':'MTR-METERS','BOX':'BOX-BOX','SET':'SET-SETS',
       'UNT':'UNT-UNITS','OTH':'OTH-OTHERS'}


def text(parent, name, value):
    value = str(value)
    # XML 1.0 forbids these characters, even when encoded as numeric entities.
    if any(not (char in '\t\n\r' or '\u0020' <= char <= '\ud7ff' or '\ue000' <= char <= '\ufffd' or '\U00010000' <= char <= '\U0010ffff') for char in value):
        raise ValueError(f'Invalid XML control character in {name}')
    child = ET.SubElement(parent, name)
    child.text = value
    return child


def envelope(company, report):
    root = ET.Element('ENVELOPE')
    header = ET.SubElement(root,'HEADER')
    text(header,'TALLYREQUEST','Import Data')
    body = ET.SubElement(root,'BODY')
    import_data = ET.SubElement(body,'IMPORTDATA')
    request_desc = ET.SubElement(import_data,'REQUESTDESC')
    text(request_desc,'REPORTNAME',report)
    variables = ET.SubElement(request_desc,'STATICVARIABLES')
    text(variables,'SVCURRENTCOMPANY',company)
    data = ET.SubElement(import_data,'REQUESTDATA')
    return root, data


def message(data):
    return ET.SubElement(data,'TALLYMESSAGE',{'xmlns:UDF':'TallyUDF'})


def display_name(master, name):
    text(master,'NAME',name)
    names = ET.SubElement(master,'LANGUAGENAME.LIST')
    name_list = ET.SubElement(names,'NAME.LIST',{'TYPE':'String'})
    text(name_list,'NAME',name)
    text(names,'LANGUAGEID','1033')


def gst_details(stock, master, effective_date):
    details = ET.SubElement(stock,'GSTDETAILS.LIST')
    text(details,'APPLICABLEFROM',effective_date)
    text(details,'CALCULATIONTYPE','On Value')
    text(details,'HSNCODE',master['hsn'])
    text(details,'TAXABILITY',TAXABILITY[master['classification']])
    text(details,'ISREVERSECHARGEAPPLICABLE','No')
    text(details,'ISNONGSTGOODS','Yes' if master['classification'] == 'non_gst' else 'No')
    states = ET.SubElement(details,'STATEWISEDETAILS.LIST')
    text(states,'STATENAME','Any')
    for tax in TAXES:
        rate = ET.SubElement(states,'RATEDETAILS.LIST')
        text(rate,'GSTRATEDUTYHEAD',HEADS[tax])
        text(rate,'GSTRATEVALUATIONTYPE','Based on Value')
        text(rate,'GSTRATE',master[f'{tax}_rate'])


def masters_document(config, masters, invoices):
    root, data = envelope(config['company_name'],'All Masters')
    if config.get('demo_only'):
        root.insert(0,ET.Comment(' DEMO ONLY: synthetic GSTINs and assumed fields; never use for filing. '))
    priority = {'unit':0,'stock_group':1,'ledger':2,'stock_item':3}
    for master in sorted(masters,key=lambda m:(priority[m['kind']],m['name'].casefold())):
        kind = master['kind']
        tag = {'unit':'UNIT','stock_group':'STOCKGROUP','ledger':'LEDGER','stock_item':'STOCKITEM'}[kind]
        node = ET.SubElement(message(data),tag,{'NAME':master['name'],'ACTION':'Create'})
        if kind == 'unit':
            text(node,'NAME',master['name'])
            text(node,'ISSIMPLEUNIT','Yes')
            text(node,'ORIGINALNAME',master['formal_name'])
            text(node,'DECIMALPLACES',master['decimal_places'])
            uqc = master.get('tally_uqc') or UQC.get(master['uqc'].upper())
            if not uqc:
                raise ValueError(f"Unit {master['name']} needs its exact Tally UQC label as tally_uqc in client.json")
            text(node,'GSTREPUOM',uqc)
        elif kind == 'stock_group':
            display_name(node,master['name'])
            if master['parent'] != 'Primary':
                text(node,'PARENT',master['parent'])
            text(node,'ISADDABLE','No')
        elif kind == 'ledger':
            display_name(node,master['name'])
            text(node,'PARENT',master['group'])
            text(node,'OPENINGBALANCE','0')
            if master['group'] == 'Sundry Debtors':
                text(node,'ISBILLWISEON','Yes')
                text(node,'COUNTRYNAME',master['country'])
                text(node,'LEDSTATENAME',master['state'])
                text(node,'GSTREGISTRATIONTYPE',master['registration'])
                if master['gstin']:
                    text(node,'PARTYGSTIN',master['gstin'])
            elif master['group'] == 'Sales Accounts':
                text(node,'ISBILLWISEON','No')
                text(node,'AFFECTSSTOCK','Yes')
                text(node,'GSTAPPLICABLE','Not Applicable' if master['classification'] == 'non_gst' else 'Applicable')
                text(node,'GSTTYPEOFSUPPLY','Goods')
            elif master['group'] == 'Duties & Taxes':
                text(node,'TAXTYPE','GST')
                text(node,'GSTDUTYHEAD',HEADS[master['duty_head'].lower()])
        else:
            display_name(node,master['name'])
            if master['group'] != 'Primary':
                text(node,'PARENT',master['group'])
            text(node,'BASEUNITS',master['unit'])
            text(node,'GSTAPPLICABLE','Applicable')
            text(node,'GSTTYPEOFSUPPLY','Goods')
            dates = [inv['date'] for inv in invoices.values() if any(item['name'].strip().casefold() == master['name'].strip().casefold() for item in inv['items'])]
            if not dates:
                raise ValueError('Stock master has no dependent invoice')
            gst_details(node,master,min(dates).replace('-',''))
    return root


def allocation(parent, entry, number, party=False, entries_tag='LEDGERENTRIES.LIST'):
    node = ET.SubElement(parent,entries_tag)
    amount = cents(money(entry['credit']) - money(entry['debit']))
    text(node,'LEDGERNAME',entry['ledger'])
    text(node,'ISDEEMEDPOSITIVE','Yes' if amount < 0 else 'No')
    text(node,'ISPARTYLEDGER','Yes' if party else 'No')
    text(node,'ISLASTDEEMEDPOSITIVE','Yes' if amount < 0 else 'No')
    text(node,'AMOUNT',format(amount,'f'))
    if party:
        bill = ET.SubElement(node,'BILLALLOCATIONS.LIST')
        text(bill,'NAME',number)
        text(bill,'BILLTYPE','New Ref')
        text(bill,'AMOUNT',format(amount,'f'))


def sales_document(config, invoices):
    root, data = envelope(config['company_name'],'Vouchers')
    if config.get('demo_only'):
        root.insert(0,ET.Comment(' DEMO ONLY: synthetic GSTINs and assumed fields; never use for filing. '))
    for key, inv in sorted(invoices.items(),key=lambda entry:(entry[1]['date'],entry[0])):
        is_export = inv['classification'] == 'export_lut'
        view = 'Accounting Voucher View' if is_export else 'Invoice Voucher View'
        remote_id = str(uuid.uuid5(uuid.NAMESPACE_URL,config['company_id'] + '|' + key))
        voucher = ET.SubElement(message(data),'VOUCHER',{'REMOTEID':remote_id,'VCHTYPE':'Sales','ACTION':'Create','OBJVIEW':view})
        for name,value in {
            'DATE':inv['date'].replace('-',''),'EFFECTIVEDATE':inv['date'].replace('-',''),
            'GUID':remote_id,'VOUCHERTYPENAME':'Sales','VOUCHERNUMBER':inv['number'],
            'REFERENCE':inv['number'],'REFERENCEDATE':inv['date'].replace('-',''),
            'PARTYLEDGERNAME':inv['buyer_name'],'PARTYNAME':inv['buyer_name'],
            'BASICBUYERNAME':inv['buyer_name'],'PERSISTEDVIEW':view,
            'ISINVOICE':'No' if is_export else 'Yes','ISOPTIONAL':'No','ISCANCELLED':'No',
            'GSTREGISTRATIONTYPE':inv['buyer_registration'],
            'PLACEOFSUPPLY':'Outside India' if is_export else STATES[inv['place_of_supply']],
            'STATENAME':'Not Applicable' if is_export else STATES[inv['buyer_state']],
            'COUNTRYOFRESIDENCE':inv['buyer_country'] if is_export else 'India',
            'NARRATION':('DEMO ONLY; synthetic GSTINs and assumed fields. ' if config.get('demo_only') else '') + f"Sales invoice {inv['number']}; source {inv['source']}",
        }.items():
            text(voucher,name,value)
        if inv.get('buyer_address'):
            address = ET.SubElement(voucher,'BASICBUYERADDRESS.LIST',{'TYPE':'String'})
            text(address,'BASICBUYERADDRESS',inv['buyer_address'])
        if is_export:
            narration = voucher.find('NARRATION')
            narration.text += ('; EXPORT UNDER LUT WITHOUT PAYMENT OF IGST; country '+inv['buyer_country']+
                               '; shipping bill/port '+str(inv.get('shipping_bill_port','not provided'))+
                               '; '+export_notice(config))
        if inv['buyer_gstin']:
            text(voucher,'PARTYGSTIN',inv['buyer_gstin'])
        entries = accounting_entries(inv,config)
        # The sales credit is in each inventory item's accounting allocation.
        # Adding a second standalone sales credit would double-post it.
        allocation(voucher,entries[0],inv['number'],party=True,
                   entries_tag='ALLLEDGERENTRIES.LIST' if is_export else 'LEDGERENTRIES.LIST')
        if is_export:
            for entry in entries[1:]:
                allocation(voucher,entry,inv['number'],entries_tag='ALLLEDGERENTRIES.LIST')
            continue
        for entry in entries[2:]:
            allocation(voucher,entry,inv['number'])
        for item in inv['items']:
            inventory = ET.SubElement(voucher,'ALLINVENTORYENTRIES.LIST')
            amount = format(cents(item['value']),'f')
            quantity = f"{item['quantity']} {item['unit']}"
            for name,value in {'STOCKITEMNAME':item['name'],'ISDEEMEDPOSITIVE':'No',
                               'ISLASTDEEMEDPOSITIVE':'No','RATE':f"{item['rate']}/{item['unit']}",
                               'AMOUNT':amount,'ACTUALQTY':quantity,'BILLEDQTY':quantity}.items():
                text(inventory,name,value)
            batch = ET.SubElement(inventory,'BATCHALLOCATIONS.LIST')
            for name,value in {'GODOWNNAME':'Main Location','BATCHNAME':'Primary Batch',
                               'DESTINATIONGODOWNNAME':'Main Location','AMOUNT':amount,
                               'ACTUALQTY':quantity,'BILLEDQTY':quantity}.items():
                text(batch,name,value)
            account = ET.SubElement(inventory,'ACCOUNTINGALLOCATIONS.LIST')
            text(account,'LEDGERNAME',sales_ledger(inv,config))
            text(account,'ISDEEMEDPOSITIVE','No')
            text(account,'AMOUNT',amount)
    verify_sales(root,invoices,config)
    return root


def verify_sales(root, invoices, config):
    """Check actual serialized allocation data, not just input accounting totals."""
    vouchers = root.findall('./BODY/IMPORTDATA/REQUESTDATA/TALLYMESSAGE/VOUCHER')
    if len(vouchers) != len(invoices):
        raise ValueError('XML voucher count does not match validated invoices')
    expected = {str(uuid.uuid5(uuid.NAMESPACE_URL,config['company_id']+'|'+key)):inv for key,inv in invoices.items()}
    for voucher in vouchers:
        if voucher.get('ACTION') != 'Create' or voucher.findtext('VOUCHERTYPENAME') != 'Sales':
            raise ValueError('Only Create Sales vouchers may be generated')
        entries = voucher.findall('LEDGERENTRIES.LIST')+voucher.findall('ALLLEDGERENTRIES.LIST')
        items = voucher.findall('ALLINVENTORYENTRIES.LIST')
        credits = sum(money(e.findtext('AMOUNT')) for e in entries)
        credits += sum(money(a.findtext('AMOUNT')) for i in items for a in i.findall('ACCOUNTINGALLOCATIONS.LIST'))
        if credits != Decimal('0'):
            raise ValueError('XML inventory and ledger allocations do not balance exactly')
        inv = expected.get(voucher.get('REMOTEID'))
        if inv is None:
            raise ValueError('XML voucher does not match its input invoice identity')
        is_export = inv['classification'] == 'export_lut'
        if is_export:
            if items or voucher.findall('LEDGERENTRIES.LIST') or voucher.get('OBJVIEW') != 'Accounting Voucher View' or voucher.findtext('ISINVOICE') != 'No':
                raise ValueError('LUT export must use accounting view with no inventory movement')
            actual = [(e.findtext('LEDGERNAME'),cents(e.findtext('AMOUNT'))) for e in entries]
            desired = [(e['ledger'],cents(money(e['credit'])-money(e['debit']))) for e in accounting_entries(inv,config)]
            if actual != desired:
                raise ValueError('Export XML ledger allocations do not match the validated accounting entry')
        if not is_export and any(e.findtext('LEDGERNAME') in {config['ledgers'][k] for k in TAXABILITY} for e in entries):
            raise ValueError('Sales ledger was posted outside inventory accounting allocation')
        for item in items:
            if sum(money(a.findtext('AMOUNT')) for a in item.findall('ACCOUNTINGALLOCATIONS.LIST')) != money(item.findtext('AMOUNT')):
                raise ValueError('Inventory value does not reconcile to sales allocations')


def verify_references(config, invoices, available_masters):
    known = {identity(m):m for m in available_masters}
    for inv in invoices.values():
        for required in required_masters(inv,config):
            found = known.get(identity(required))
            if not found or any(found.get(key) != value for key,value in required.items() if key not in ('kind','name')):
                raise ValueError(f"Missing or conflicting master reference: {required['kind']} {required['name']}")


def save_document(root, path):
    # Round-trip before writing so malformed values never become import output.
    encoded = ET.tostring(root,encoding='utf-8',xml_declaration=True)
    ET.fromstring(encoded)
    ET.indent(root,space='  ')
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)

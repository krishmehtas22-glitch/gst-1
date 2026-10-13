"""Mandatory complete batch XML output, with uncertainties retained for Tally review.

This does not approve invoices, mutate financial history, or claim Tally import.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib,json,re,uuid
from pathlib import Path
import xml.etree.ElementTree as ET
from .engine import read_json,write_json
from .accounting import money,cents,STATES,gstin_valid,invoice_key
from .tally_xml import envelope,message,text,display_name,allocation,save_document,HEADS,UQC,gst_details
from .processing_lock import guard
from .unit_catalog import UNITS


def policy_path(root,client):
    return Path(root)/'.invoice_app'/'batch_output_policy'/(hashlib.sha256(client.encode()).hexdigest()+'.json')


def enable(root,client):
    write_json(policy_path(root,client),{'client':client,'output_all':True,'review_in':'Tally'})


def enabled(root,client):
    path=policy_path(root,client)
    return path.exists() and read_json(path).get('output_all') is True


def clean(value):
    return ''.join(c for c in str(value or '') if c in '\t\n\r' or '\u0020'<=c<='\ud7ff' or '\ue000'<=c<='\ufffd' or '\U00010000'<=c<='\U0010ffff')


def number(value):
    try:return cents(value)
    except (ValueError,TypeError,ArithmeticError):return None


def precise(value):
    """Quantities/rates are not currency totals and must not round to paise."""
    try:return money(value)
    except (ValueError,TypeError,ArithmeticError):return None


def export_all(root,records,demo):
    clients=defaultdict(list)
    for record in records:clients[record['client']].append(record)
    for client,group in clients.items():
        base=Path(root)/'.invoice_app'/'batch_xml'/((re.sub(r'[^A-Za-z0-9_-]+','_',client)[:40] or 'Client')+'_'+hashlib.sha256(client.encode()).hexdigest()[:10])
        # This separate exporter does not touch strict company run.lock/history.
        # OS guard still protects simultaneous writers; stale old markers cannot block it.
        with guard(base):
            run=base/'runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:8]);run.mkdir(parents=True)
            sellers=defaultdict(list)
            for record in group:
                inv=record.get('invoice') or {}
                seller=clean(inv.get('seller_name') or inv.get('seller_name_candidate')) or 'Seller unresolved - '+client
                sellers[(seller,clean(inv.get('seller_gstin')))].append(record)
            report=[]
            for index,((seller,seller_gstin),rows) in enumerate(sellers.items(),1):
                folder=run if len(sellers)==1 else run/(f'{index:02d}_'+(re.sub(r'[^A-Za-z0-9_-]+','_',seller)[:45] or 'Seller'))
                folder.mkdir(exist_ok=True)
                # Import into the company selected in Tally; seller is recorded in
                # manifest/narration. Different sellers have separate file pairs.
                masters,md=envelope('', 'All Masters');vouchers,vd=envelope('', 'Vouchers')
                masters.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(masters.find('.//SVCURRENTCOMPANY'))
                vouchers.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(vouchers.find('.//SVCURRENTCOMPANY'))
                known={}
                def ledger(name,parent,**extra):
                    key=('ledger',name)
                    if key in known:return name
                    known[key]=True
                    node=ET.SubElement(message(md),'LEDGER',{'NAME':name,'ACTION':'Create'});display_name(node,name)
                    text(node,'PARENT',parent);text(node,'OPENINGBALANCE','0')
                    for tag,value in extra.items():text(node,tag,clean(value))
                    return name
                ledger('Sales','Sales Accounts',AFFECTSSTOCK='Yes')
                ledger('Invoice differences - review','Indirect Expenses')
                for record in rows:
                    inv=record.get('invoice') or {};notes=list(record.get('errors',[]))+list(inv.get('extraction_warnings',[]))
                    for i,item in enumerate(inv.get('items',[]),1):
                        if item.get('unit_auto'):notes.append('Item '+str(i)+' unit '+str(item.get('unit','Units'))+' assumed: '+str(item.get('unit_evidence','Product-context reasoning')))
                    source=record.get('source_path',record['path']);identity=record.get('digest') or hashlib.sha256(str(source).encode()).hexdigest()
                    no=clean(inv.get('number')) or 'UNREAD-'+identity[:12]
                    if not inv.get('number'):notes.append('Invoice number missing; explicit UNREAD reference used')
                    buyer=clean(inv.get('buyer_name')) or 'Buyer unresolved - '+identity[:10]
                    gstin=clean(inv.get('buyer_gstin'))
                    # Distinct GST/address variants do not rewrite existing party masters.
                    party_sig=hashlib.sha256(json.dumps([gstin,inv.get('buyer_state'),inv.get('buyer_address')],sort_keys=True).encode()).hexdigest()[:8]
                    party=buyer+' [batch '+party_sig+']'
                    ledger(party,'Sundry Debtors',ISBILLWISEON='Yes',**({'PARTYGSTIN':gstin} if gstin else {}))
                    if not inv.get('seller_name'):notes.append('Seller unresolved or candidate only; seller not invented')
                    if not seller_gstin or not gstin_valid(seller_gstin):notes.append('Seller GSTIN missing/invalid; retained for Tally review')
                    amounts={k:number(inv.get(k)) for k in ('taxable','total','cgst','sgst','igst','cess','round_off')}
                    for k in ('cgst','sgst','igst','cess','round_off'):
                        if amounts[k] is None:
                            notes.append(k+' missing/invalid; no numeric posting available (not an extracted zero)')
                            amounts[k]=Decimal('0')
                    tax=sum(amounts[k] for k in ('cgst','sgst','igst','cess','round_off'))
                    if amounts['taxable'] is None:
                        values=[number(i.get('value')) for i in inv.get('items',[])]
                        amounts['taxable']=sum(values,Decimal('0')) if values and all(v is not None for v in values) else (amounts['total']-tax if amounts['total'] is not None else Decimal('0'))
                        notes.append('Taxable amount derived from available amounts; see retained extraction')
                    if amounts['total'] is None:
                        amounts['total']=amounts['taxable']+tax;notes.append('Invoice total derived; printed total missing/invalid')
                    items=inv.get('items') or []
                    inventory=bool(items) and inv.get('supply')!='EXPORT' and all(number(i.get('value')) is not None and precise(i.get('quantity',1)) is not None and precise(i.get('quantity',1))>0 for i in items)
                    if inventory and (inv.get('classification') not in ('taxable','exempt','nil_rated','non_gst') or any(precise(i.get(t+'_rate')) is None for i in items for t in ('cgst','sgst','igst'))):inventory=False
                    if inventory and all(amounts[t]==0 for t in ('cgst','sgst','igst')) and any(precise(i.get(t+'_rate'))!=0 for i in items for t in ('cgst','sgst','igst')):
                        inventory=False;notes.append('Zero invoice GST conflicts with item rates; no tax posted, accounting voucher used')
                    if inventory and sum(number(i['value']) for i in items)!=amounts['taxable']:inventory=False
                    if not inventory:notes.append('Accounting voucher: item inventory not posted; all extracted items retained in manifest')
                    remote=str(uuid.uuid5(uuid.NAMESPACE_URL,client+'|'+identity+'|'+no))
                    binding=Path(root)/'.invoice_app'/'routing'/(identity+'.json')
                    if binding.exists():
                        try:
                            company=read_json(binding)['company']
                            config=read_json(Path(root)/'.invoice_app'/'companies'/company/'client.json')
                            remote=str(uuid.uuid5(uuid.NAMESPACE_URL,config['company_id']+'|'+invoice_key({**inv,'seller_gstin':config['seller_gstin']})))
                        except (ValueError,OSError,KeyError,TypeError):notes.append('Prior voucher identity could not be recovered; source-based stable GUID used')
                    view='Invoice Voucher View' if inventory else 'Accounting Voucher View'
                    voucher=ET.SubElement(message(vd),'VOUCHER',{'REMOTEID':remote,'VCHTYPE':'Sales','ACTION':'Create','OBJVIEW':view})
                    date=clean(inv.get('date')).replace('-','')
                    if not re.fullmatch(r'\d{8}',date):date='';notes.append('Date missing/invalid; Tally may reject this voucher')
                    for tag,value in {'DATE':date,'EFFECTIVEDATE':date,'GUID':remote,'VOUCHERTYPENAME':'Sales','VOUCHERNUMBER':no,'REFERENCE':no,'PARTYLEDGERNAME':party,'PARTYNAME':buyer,'PERSISTEDVIEW':view,'ISINVOICE':'Yes' if inventory else 'No','ISOPTIONAL':'No','ISCANCELLED':'No'}.items():text(voucher,tag,value)
                    if gstin:text(voucher,'PARTYGSTIN',gstin)
                    pos=clean(inv.get('place_of_supply'))
                    if pos:text(voucher,'PLACEOFSUPPLY',STATES.get(pos,pos))
                    allocation(voucher,{'ledger':party,'debit':amounts['total'],'credit':0},no,True,entries_tag='ALLLEDGERENTRIES.LIST')
                    if inventory:
                        for item in items:
                            unit=clean(item.get('unit')) or 'Units';quantity=precise(item.get('quantity',1));value=number(item['value'])
                            rate=precise(item.get('rate'))
                            if rate is None:rate=(value/quantity).quantize(Decimal('.000001'));notes.append('Item rate derived from value/quantity')
                            if cents(rate*quantity)!=value:notes.append('Item quantity/rate/value mismatch retained for Tally review')
                            sig=hashlib.sha256(json.dumps([unit,item.get('hsn'),*[item.get(t+'_rate') for t in ('cgst','sgst','igst')],inv.get('classification')],sort_keys=True).encode()).hexdigest()[:10]
                            name=(clean(item.get('name')) or 'Item unresolved')+' [batch '+sig+']'
                            if ('unit',unit) not in known:
                                un=ET.SubElement(message(md),'UNIT',{'NAME':unit,'ACTION':'Create'})
                                known[('unit',unit)]=un
                                definition=UNITS.get(unit,{})
                                uqc=definition.get('tally_uqc') or UQC.get(definition.get('uqc',unit).upper(),'OTH-OTHERS')
                                decimals=max(int(definition.get('decimal_places',3)),max(0,-quantity.normalize().as_tuple().exponent))
                                for tag,val in {'NAME':unit,'ISSIMPLEUNIT':'Yes','ORIGINALNAME':definition.get('formal_name',unit),'DECIMALPLACES':str(decimals),'GSTREPUOM':uqc}.items():text(un,tag,val)
                            else:
                                un=known[('unit',unit)]
                                decimals=max(int(un.findtext('DECIMALPLACES')),max(0,-quantity.normalize().as_tuple().exponent))
                                un.find('DECIMALPLACES').text=str(decimals)
                            if ('stock',name) not in known:
                                known[('stock',name)]=True
                                stock=ET.SubElement(message(md),'STOCKITEM',{'NAME':name,'ACTION':'Create'});display_name(stock,name);text(stock,'BASEUNITS',unit)
                                text(stock,'GSTAPPLICABLE','Applicable');text(stock,'GSTTYPEOFSUPPLY','Goods')
                                gst_details(stock,{'hsn':clean(item.get('hsn')),'classification':inv['classification'],**{t+'_rate':str(precise(item[t+'_rate'])) for t in ('cgst','sgst','igst')}},date)
                            node=ET.SubElement(voucher,'ALLINVENTORYENTRIES.LIST')
                            for tag,val in {'STOCKITEMNAME':name,'ISDEEMEDPOSITIVE':'No','ACTUALQTY':str(quantity)+' '+unit,'BILLEDQTY':str(quantity)+' '+unit,'AMOUNT':str(value),'RATE':str(rate)+'/'+unit}.items():text(node,tag,val)
                            allocation(node,{'ledger':'Sales','debit':0,'credit':value},no,entries_tag='ACCOUNTINGALLOCATIONS.LIST')
                    else:allocation(voucher,{'ledger':'Sales','debit':0,'credit':amounts['taxable']},no,entries_tag='ALLLEDGERENTRIES.LIST')
                    for kind in ('cgst','sgst','igst','cess','round_off'):
                        if not amounts[kind]:continue
                        name={'cgst':'CGST','sgst':'SGST','igst':'IGST','cess':'Cess','round_off':'Round Off'}[kind]
                        extra={'TAXTYPE':'GST','GSTDUTYHEAD':HEADS.get(kind,'Cess')} if kind!='round_off' else {}
                        ledger(name,'Duties & Taxes' if kind!='round_off' else 'Indirect Expenses',**extra)
                        allocation(voucher,{'ledger':name,'debit':0,'credit':amounts[kind]},no,entries_tag='ALLLEDGERENTRIES.LIST')
                    delta=amounts['total']-amounts['taxable']-tax
                    if delta:
                        allocation(voucher,{'ledger':'Invoice differences - review','debit':0,'credit':delta},no,entries_tag='ALLLEDGERENTRIES.LIST')
                        notes.append('Unreconciled difference '+str(delta)+' posted to Invoice differences - review; printed amounts retained')
                    text(voucher,'NARRATION',clean(('TEST DATA; ' if demo else '')+'Review in Tally; seller '+seller+'; seller GSTIN '+seller_gstin+'; source '+str(source)+'; '+ '; '.join(dict.fromkeys(notes))))
                    record.update(errors=[],output_path=str(run),group_output_path=str(folder),batch_voucher_count=len(group),display_status='XML prepared; review in Tally',tally_review_warnings=list(dict.fromkeys(notes)))
                    record.setdefault('notices',[]).extend(record['tally_review_warnings'])
                    report.append({'client':client,'source':str(source),'digest':identity,'invoice_number':no,'provider':inv.get('api_provider','Python'),'seller':seller,'buyer':buyer,'buyer_ledger':party,'xml_folder':str(folder),'voucher_guid':remote,'inventory_posted':inventory,'warnings':record['tally_review_warnings'],'extracted_invoice':inv})
                referenced={node.text for node in vouchers.findall('.//LEDGERNAME')}
                declared={node.attrib['NAME'] for node in masters.findall('.//LEDGER')}
                if not referenced.issubset(declared):raise ValueError('Internal batch error: voucher ledger reference has no exported master')
                # Units are a separate prerequisite import, never interleaved
                # with dependent stock items in the All Masters request.
                units,ud=envelope('', 'All Masters')
                units.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(units.find('.//SVCURRENTCOMPANY'))
                for msg in list(md):
                    if msg.find('UNIT') is not None:md.remove(msg);ud.append(msg)
                declared_units={node.attrib['NAME'] for node in units.findall('.//UNIT')}
                stocks={node.attrib['NAME']:node for node in masters.findall('.//STOCKITEM')}
                if any(stock.findtext('BASEUNITS') not in declared_units for stock in stocks.values()):
                    raise ValueError('Internal batch error: stock base unit has no exported unit definition')
                for item in vouchers.findall('.//ALLINVENTORYENTRIES.LIST'):
                    stock=stocks.get(item.findtext('STOCKITEMNAME'))
                    if stock is None:raise ValueError('Internal batch error: inventory stock item has no exported master')
                    unit=stock.findtext('BASEUNITS')
                    if any(not item.findtext(tag,'').endswith(' '+unit) for tag in ('ACTUALQTY','BILLEDQTY')):
                        raise ValueError('Internal batch error: quantity unit differs from stock base unit')
                # Ledger masters precede stock masters; units are already imported.
                md[:]=sorted(md,key=lambda msg:0 if msg.find('LEDGER') is not None else 1)
                save_document(units,folder/'Units.xml')
                save_document(masters,folder/'Masters.xml');save_document(vouchers,folder/'Sales_Vouchers.xml')
                assert len(vouchers.findall('.//VOUCHER'))==len(rows)
            write_json(run/'Batch_Report.json',{'client':client,'input_count':len(group),'xml_voucher_count':len(report),'invoices':report})
            (run/'Import_Instructions.txt').write_text('Import into the SAME matching selected Tally company in this order:\n1. Units.xml (unit symbols and definitions)\n2. Masters.xml (buyer/sales/tax ledgers and stock items)\n3. Sales_Vouchers.xml (vouchers)\nIgnore duplicate existing masters. Check the unit import result before importing stock masters. Each seller has a separate set if needed. Batch_Report.json retains all warnings and extracted items. To repair missing-unit/stock exceptions: import Units.xml, import Masters.xml again, then retry the rejected vouchers only. Stable voucher GUIDs are retained; check duplicate handling in Tally. XML preparation is not confirmation of import.\n')
            write_json(base/'latest.json',{'output_path':str(run),'count':len(report)})
    return records

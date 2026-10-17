"""Mandatory complete batch XML output, with uncertainties retained for Tally review.

This does not approve invoices, mutate financial history, or claim Tally import.
"""
from collections import defaultdict
from decimal import Decimal
import hashlib,json,re,uuid,tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
from .engine import read_json,write_json
from .accounting import money,cents,STATES,gstin_valid,invoice_key
from .tally_xml import envelope,message,text,display_name,allocation,save_document,HEADS,UQC,gst_details
from .processing_lock import guard
from .unit_catalog import UNITS,unit_formal_name
from .tally_units import simple_unit,unit_symbol
from .export_metadata import is_export,export_country,party_country_fields,voucher_country_fields


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
    # Validate export metadata before staging or changing any current output.
    for record in records:
        if is_export(record.get('invoice') or {}):export_country(record['invoice'])
    clients=defaultdict(list)
    for record in records:clients[record['client']].append(record)
    for client,group in clients.items():
        base=Path(root)/'.invoice_app'/'batch_xml'/((re.sub(r'[^A-Za-z0-9_-]+','_',client)[:40] or 'Client')+'_'+hashlib.sha256(client.encode()).hexdigest()[:10])
        # This separate exporter does not touch strict company run.lock/history.
        # OS guard still protects simultaneous writers; stale old markers cannot block it.
        with guard(base):
            from .client_xml_output import seller_groups,consolidate,publish,LAYOUT
            generation=uuid.uuid4().hex
            staging=tempfile.TemporaryDirectory(prefix='.staging-',dir=base)
            with staging:
                run=Path(staging.name)
                current=base/'current'
                sellers=seller_groups(group,client)
                from .plain_master_names import PlainMasterNames
                names=PlainMasterNames(group,clean)
                report=[];documents=[]
                for index,(seller,seller_gstin,rows) in enumerate(sellers,1):
                    # Import into the company selected in Tally; seller is recorded in
                    # manifest/narration. Different sellers retain explicit import destinations.
                    masters,md=envelope('', 'All Masters');vouchers,vd=envelope('', 'Vouchers')
                    masters.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(masters.find('.//SVCURRENTCOMPANY'))
                    vouchers.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(vouchers.find('.//SVCURRENTCOMPANY'))
                    known={}
                    def ledger(name,parent,**extra):
                        key=('ledger',name)
                        definition=(parent,{tag:clean(value) for tag,value in extra.items()})
                        if key in known:
                            if known[key]!=definition:
                                raise ValueError('Conflicting party/ledger details for '+name+'; review the names before export. Existing current XML retained.')
                            return name
                        known[key]=definition
                        node=ET.SubElement(message(md),'LEDGER',{'NAME':name,'ACTION':'Create'});display_name(node,name)
                        text(node,'PARENT',parent);text(node,'OPENINGBALANCE','0')
                        for tag,value in extra.items():text(node,tag,clean(value))
                        return name
                    ledger('Sales','Sales Accounts',AFFECTSSTOCK='Yes')
                    ledger('Invoice differences - review','Indirect Expenses')
                    for record in rows:
                        from .invoice_dates import recover_date
                        normalized_date=recover_date(root,record)
                        inv=record.get('invoice') or {};notes=list(record.get('errors',[]))+list(inv.get('extraction_warnings',[]))
                        if inv.get('date_evidence'):notes.append(inv['date_evidence'])
                        for i,item in enumerate(inv.get('items',[]),1):
                            if item.get('unit_auto'):notes.append('Item '+str(i)+' unit '+str(item.get('unit','Units'))+' assumed: '+str(item.get('unit_evidence','Product-context reasoning')))
                        source=record.get('source_path',record['path']);identity=record.get('digest') or hashlib.sha256(str(source).encode()).hexdigest()
                        no=clean(inv.get('number')) or 'UNREAD-'+identity[:12]
                        if not inv.get('number'):notes.append('Invoice number missing; explicit UNREAD reference used')
                        buyer=clean(inv.get('buyer_name')) or 'Buyer unresolved - '+identity[:10]
                        gstin=clean(inv.get('buyer_gstin'))
                        # Master and voucher references use the same printed party name.
                        party=names.party(buyer,gstin,inv)
                        ledger(party,'Sundry Debtors',ISBILLWISEON='Yes',**({'PARTYGSTIN':gstin} if gstin else {}),**party_country_fields(inv))
                        row_seller=clean(inv.get('seller_name') or inv.get('seller_name_candidate')) or 'Seller unresolved - '+client
                        row_seller_gstin=clean(inv.get('seller_gstin'))
                        if not inv.get('seller_name'):notes.append('Seller unresolved or candidate only; seller not invented')
                        if not row_seller_gstin or not gstin_valid(row_seller_gstin):notes.append('Seller GSTIN missing/invalid; retained for Tally review')
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
                        date=normalized_date.replace('-','') if normalized_date else ''
                        if not date:notes.append('Date missing/invalid; no verified source date could be recovered; Tally may reject this voucher')
                        for tag,value in {'DATE':date,'EFFECTIVEDATE':date,'GUID':remote,'VOUCHERTYPENAME':'Sales','VOUCHERNUMBER':no,'REFERENCE':no,'PARTYLEDGERNAME':party,'PARTYNAME':buyer,'BASICBUYERNAME':buyer,'PERSISTEDVIEW':view,'ISINVOICE':'Yes' if inventory else 'No','ISOPTIONAL':'No','ISCANCELLED':'No'}.items():text(voucher,tag,value)
                        if inv.get('buyer_address'):
                            address=ET.SubElement(voucher,'BASICBUYERADDRESS.LIST',{'TYPE':'String'})
                            text(address,'BASICBUYERADDRESS',clean(inv['buyer_address']))
                        if gstin:text(voucher,'PARTYGSTIN',gstin)
                        pos=clean(inv.get('place_of_supply'))
                        if is_export(inv):
                            for tag,value in voucher_country_fields(inv).items():text(voucher,tag,value)
                            notes.append('Export country supplied; verify export GST nature/GSTR-1 treatment in Tally. Refund eligibility is not established by this XML.')
                        elif pos:text(voucher,'PLACEOFSUPPLY',STATES.get(pos,pos))
                        entries_tag='LEDGERENTRIES.LIST' if inventory else 'ALLLEDGERENTRIES.LIST'
                        allocation(voucher,{'ledger':party,'debit':amounts['total'],'credit':0},no,True,entries_tag=entries_tag)
                        if inventory:
                            for item in items:
                                unit=clean(item.get('unit')) or 'Units';quantity=precise(item.get('quantity',1));value=number(item['value'])
                                rate=precise(item.get('rate'))
                                if rate is None:rate=(value/quantity).quantize(Decimal('.000001'));notes.append('Item rate derived from value/quantity')
                                if cents(rate*quantity)!=value:notes.append('Item quantity/rate/value mismatch retained for Tally review')
                                sig=names.stock_identity(item,inv)
                                name=names.stock(item,inv)
                                if ('stock',name) in known and known[('stock',name)]!=sig:
                                    raise ValueError('Conflicting stock details for '+name+'; review its unit/HSN/GST before export. Existing current XML retained.')
                                if ('unit',unit) not in known:
                                    definition=UNITS.get(unit,{})
                                    uqc=definition.get('tally_uqc') or UQC.get(definition.get('uqc',unit).upper(),'OTH-OTHERS')
                                    decimals=max(int(definition.get('decimal_places',3)),max(0,-quantity.normalize().as_tuple().exponent))
                                    formal=unit_formal_name(unit,definition.get('formal_name'))
                                    un=simple_unit(unit,formal,decimals,uqc)
                                    message(md).append(un)
                                    known[('unit',unit)]=un
                                else:
                                    un=known[('unit',unit)]
                                    decimals=max(int(un.findtext('DECIMALPLACES')),max(0,-quantity.normalize().as_tuple().exponent))
                                    un.find('DECIMALPLACES').text=str(decimals)
                                if ('stock',name) not in known:
                                    known[('stock',name)]=sig
                                    stock=ET.SubElement(message(md),'STOCKITEM',{'NAME':name,'ACTION':'Create'});display_name(stock,name);text(stock,'BASEUNITS',unit)
                                    text(stock,'GSTAPPLICABLE','Applicable');text(stock,'GSTTYPEOFSUPPLY','Goods')
                                    gst_details(stock,{'hsn':clean(item.get('hsn')),'classification':inv['classification'],**{t+'_rate':str(precise(item[t+'_rate'])) for t in ('cgst','sgst','igst')}},date)
                                node=ET.SubElement(voucher,'ALLINVENTORYENTRIES.LIST')
                                for tag,val in {'STOCKITEMNAME':name,'ISDEEMEDPOSITIVE':'No','ISLASTDEEMEDPOSITIVE':'No','ACTUALQTY':str(quantity)+' '+unit,'BILLEDQTY':str(quantity)+' '+unit,'AMOUNT':str(value),'RATE':str(rate)+'/'+unit}.items():text(node,tag,val)
                                batch=ET.SubElement(node,'BATCHALLOCATIONS.LIST')
                                for tag,val in {'GODOWNNAME':'Main Location','BATCHNAME':'Primary Batch','DESTINATIONGODOWNNAME':'Main Location','AMOUNT':str(value),'ACTUALQTY':str(quantity)+' '+unit,'BILLEDQTY':str(quantity)+' '+unit}.items():text(batch,tag,val)
                                account=ET.SubElement(node,'ACCOUNTINGALLOCATIONS.LIST')
                                for tag,val in {'LEDGERNAME':'Sales','ISDEEMEDPOSITIVE':'No','AMOUNT':str(value)}.items():text(account,tag,val)
                        else:allocation(voucher,{'ledger':'Sales','debit':0,'credit':amounts['taxable']},no,entries_tag=entries_tag)
                        for kind in ('cgst','sgst','igst','cess','round_off'):
                            if not amounts[kind]:continue
                            name={'cgst':'CGST','sgst':'SGST','igst':'IGST','cess':'Cess','round_off':'Round Off'}[kind]
                            extra={'TAXTYPE':'GST','GSTDUTYHEAD':HEADS.get(kind,'Cess')} if kind!='round_off' else {}
                            ledger(name,'Duties & Taxes' if kind!='round_off' else 'Indirect Expenses',**extra)
                            allocation(voucher,{'ledger':name,'debit':0,'credit':amounts[kind]},no,entries_tag=entries_tag)
                        delta=amounts['total']-amounts['taxable']-tax
                        if delta:
                            allocation(voucher,{'ledger':'Invoice differences - review','debit':0,'credit':delta},no,entries_tag=entries_tag)
                            notes.append('Unreconciled difference '+str(delta)+' posted to Invoice differences - review; printed amounts retained')
                        text(voucher,'NARRATION',clean(('TEST DATA; ' if demo else '')+'Review in Tally; seller '+row_seller+'; seller GSTIN '+row_seller_gstin+'; source '+str(source)+'; '+ '; '.join(dict.fromkeys(notes))))
                        record.update(errors=[],output_path=str(current),group_output_path=str(current),output_generation=generation,output_seller_group=index,batch_voucher_count=len(group),display_status='XML prepared; review in Tally',tally_review_warnings=list(dict.fromkeys(notes)))
                        record.setdefault('notices',[]).extend(record['tally_review_warnings'])
                        report.append({'client':client,'source':str(source),'digest':identity,'invoice_number':no,'provider':inv.get('api_provider','Python'),'seller':row_seller,'seller_group':index,'seller_group_label':seller,'seller_group_gstin':seller_gstin,'buyer':buyer,'buyer_ledger':party,'xml_folder':str(current),'voucher_guid':remote,'inventory_posted':inventory,'warnings':record['tally_review_warnings'],'extracted_invoice':inv})
                    referenced={node.text for node in vouchers.findall('.//LEDGERNAME')}
                    declared={node.attrib['NAME'] for node in masters.findall('.//LEDGER')}
                    if not referenced.issubset(declared):raise ValueError('Internal batch error: voucher ledger reference has no exported master')
                    # Units are a separate prerequisite import, never interleaved
                    # with dependent stock items in the All Masters request.
                    units,ud=envelope('', 'All Masters')
                    units.find('./BODY/IMPORTDATA/REQUESTDESC/STATICVARIABLES').remove(units.find('.//SVCURRENTCOMPANY'))
                    for msg in list(md):
                        if msg.find('UNIT') is not None:md.remove(msg);ud.append(msg)
                    declared_units={unit_symbol(node) for node in units.findall('.//UNIT')}
                    stocks={node.attrib['NAME']:node for node in masters.findall('.//STOCKITEM')}
                    if any(stock.findtext('BASEUNITS') not in declared_units for stock in stocks.values()):
                        raise ValueError('Internal batch error: stock base unit has no exported unit definition')
                    for item in vouchers.findall('.//ALLINVENTORYENTRIES.LIST'):
                        stock=stocks.get(item.findtext('STOCKITEMNAME'))
                        if stock is None:raise ValueError('Internal batch error: inventory stock item has no exported master')
                        unit=stock.findtext('BASEUNITS')
                        if any(not item.findtext(tag,'').endswith(' '+unit) for tag in ('ACTUALQTY','BILLEDQTY')):
                            raise ValueError('Internal batch error: quantity unit differs from stock base unit')
                    verify_vouchers(vouchers)
                    # Ledger masters precede stock masters; units are already imported.
                    md[:]=sorted(md,key=lambda msg:0 if msg.find('LEDGER') is not None else 1)
                    documents.append((units,masters,vouchers))
                    assert len(vouchers.findall('.//VOUCHER'))==len(rows)
                units,masters,vouchers=consolidate(documents)
                from .tally_master_xml import apply_matches
                ordered=[row for _,_,part in sellers for row in part]
                apply_matches(root,ordered,report,units,masters,vouchers)
                verify_vouchers(vouchers)
                if len(vouchers.findall('.//VOUCHER'))!=len(group):raise ValueError('Consolidated voucher count differs from source count')
                save_document(units,run/'Units.xml');save_document(masters,run/'Masters.xml');save_document(vouchers,run/'Sales_Vouchers.xml')
                write_json(run/'Batch_Report.json',{'layout':LAYOUT,'generation':generation,'client':client,'input_count':len(group),'xml_voucher_count':len(report),'invoices':report})
                (run/'Import_Instructions.txt').write_text('Current complete client XML: 1. Units.xml → 2. Masters.xml → 3. Sales_Vouchers.xml. Use Import to Tally for explicit company selection and existing-unit reuse. Distinct sellers are routed separately in memory. Review warnings in Batch_Report.json; do not reimport already accepted vouchers. One internal previous-output backup is retained. XML creation is not import confirmation.\n',encoding='utf-8')
                publish(base,run)
                write_json(base/'latest.json',{'output_path':str(current),'count':len(report),'generation':generation})
    return records


def verify_vouchers(document):
    """Validate serialized Tally view, party debit and exactly one sales credit."""
    for voucher in document.findall('.//VOUCHER'):
        inventory=voucher.findall('ALLINVENTORYENTRIES.LIST')
        expected='LEDGERENTRIES.LIST' if inventory else 'ALLLEDGERENTRIES.LIST'
        wrong='ALLLEDGERENTRIES.LIST' if inventory else 'LEDGERENTRIES.LIST'
        if voucher.findall(wrong):raise ValueError('Internal XML error: ledger list does not match voucher view')
        entries=voucher.findall(expected)
        parties=[entry for entry in entries if entry.findtext('ISPARTYLEDGER')=='Yes']
        if len(parties)!=1 or parties[0].findtext('LEDGERNAME')!=voucher.findtext('PARTYLEDGERNAME'):
            raise ValueError('Internal XML error: buyer ledger does not match the party debit')
        total=sum(money(entry.findtext('AMOUNT')) for entry in entries)
        for item in inventory:
            accounts=item.findall('ACCOUNTINGALLOCATIONS.LIST')
            batches=item.findall('BATCHALLOCATIONS.LIST')
            value=money(item.findtext('AMOUNT'))
            if sum(money(account.findtext('AMOUNT')) for account in accounts)!=value:
                raise ValueError('Internal XML error: item sales allocation does not match value')
            if not batches or sum(money(batch.findtext('AMOUNT')) for batch in batches)!=value:
                raise ValueError('Internal XML error: item godown allocation does not match value')
            total+=sum(money(account.findtext('AMOUNT')) for account in accounts)
        if total!=0:raise ValueError('Internal XML error: serialized debit/credit entries do not balance')

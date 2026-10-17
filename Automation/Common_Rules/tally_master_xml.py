"""Apply validated references after the unchanged invoice accounting writer."""
from copy import deepcopy
import json
import xml.etree.ElementTree as ET
from .tally_master_matching import context,assignments,details,norm,MARKER
from .tally_units import unit_symbol


def dependencies(document):
    raw=document.get(MARKER)
    return json.loads(raw) if raw else {'ledgers':[],'stocks':[],'units':[]}


def check_company(plan,company):
    owners={dependencies(ET.fromstring(data)).get('company') for _,data in plan}
    owners.discard(None)
    if owners and owners!={company}:
        raise ValueError('These XML references use masters from '+', '.join(sorted(owners))+'. Choose that exact Tally company or regenerate with its masters. No import sent.')


def apply_matches(root,records,report,units,masters,vouchers):
    if not records:return
    ctx=context(root,records[0])
    if not ctx:return
    catalog=details(ctx);existing={kind:{norm(e['name']) for e in catalog.values() if e['kind']==kind} for kind in ('ledgers','stock_items','units')}
    source_masters={ (n.tag,n.get('NAME')):msg for msg in masters.find('.//REQUESTDATA') for n in msg }
    source_units={unit_symbol(msg.find('UNIT')):msg for msg in units.find('.//REQUESTDATA')}
    output={};output_units={};external={'company':ctx['company'],'ledgers':set(),'stocks':set(),'units':set()}
    allocated={};occupied={kind:set(value) for kind,value in existing.items()}
    def fresh(kind,name,description):
        key=(kind,name,description)
        if key in allocated:return allocated[key]
        value=name
        if norm(value) in occupied[kind]:
            base=name+' (invoice '+description+')';value=base;index=2
            while norm(value) in occupied[kind]:value=base+' '+str(index);index+=1
        occupied[kind].add(norm(value));allocated[key]=value;return value
    def clone_master(kind,old,new):
        msg=deepcopy(source_masters[kind,old]);node=msg.find(kind);node.set('NAME',new)
        display=node.find('.//NAME')
        if display is not None:display.text=new
        return msg
    def keep(msg):
        node=next(iter(msg));key=(node.tag,node.get('NAME'))
        signature=ET.canonicalize(ET.tostring(msg,encoding='unicode'),strip_text=True)
        if key in output and ET.canonicalize(ET.tostring(output[key],encoding='unicode'),strip_text=True)!=signature:
            raise ValueError('Conflicting mapped master '+str(key)+'; review before import.')
        output[key]=msg
    def unit_definition(old,new):
        if new not in output_units:
            msg=deepcopy(source_units[old]);node=msg.find('UNIT')
            if node.get('NAME') is not None:node.set('NAME',new)
            child=node.find('NAME')
            if child is not None:child.text=new
            output_units[new]=msg
    for voucher,row,entry in zip(vouchers.findall('.//VOUCHER'),records,report):
        inv=row.get('invoice') or {};match=assignments(root,row,ctx)
        old=voucher.findtext('PARTYLEDGERNAME');party=match['party']
        target=party['name'] if party else fresh('ledgers',old,'party '+str(inv.get('buyer_gstin') or inv.get('buyer_address') or 'review'))
        if party:external['ledgers'].add(target)
        else:keep(clone_master('LEDGER',old,target))
        voucher.find('PARTYLEDGERNAME').text=target
        for ledger in voucher.findall('.//LEDGERNAME'):
            if ledger.text==old:ledger.text=target
        audit={'company':ctx['company'],'snapshot_sha256':ctx['sha256'],'party':target if party else None,'items':[]}
        for index,node in enumerate(voucher.findall('ALLINVENTORYENTRIES.LIST')):
            item=inv['items'][index];choice=match['items'][index];oldstock=node.findtext('STOCKITEMNAME')
            oldunit=source_masters['STOCKITEM',oldstock].findtext('STOCKITEM/BASEUNITS')
            unit=choice['unit']['name'] if choice['unit'] else oldunit
            if choice['unit']:external['units'].add(unit)
            else:unit_definition(oldunit,unit)
            stock=choice['stock'];name=stock['name'] if stock else fresh('stock_items',oldstock,'unit '+unit+'; HSN '+str(item.get('hsn') or 'review'))
            if stock:external['stocks'].add(name)
            else:
                msg=clone_master('STOCKITEM',oldstock,name);msg.find('STOCKITEM/BASEUNITS').text=unit;keep(msg)
            node.find('STOCKITEMNAME').text=name
            for qty in node.iter():
                if qty.tag in ('ACTUALQTY','BILLEDQTY'):
                    suffix=' '+oldunit
                    if not (qty.text or '').endswith(suffix):raise ValueError('Unexpected quantity unit in mapped XML.')
                    qty.text=qty.text[:-len(suffix)]+' '+unit
                elif qty.tag=='RATE':
                    suffix='/'+oldunit
                    if not (qty.text or '').endswith(suffix):raise ValueError('Unexpected rate unit in mapped XML.')
                    qty.text=qty.text[:-len(suffix)]+'/'+unit
            audit['items'].append({'index':index,'stock':name if stock else None,'unit':unit if choice['unit'] else None})
        entry['buyer_ledger']=target;entry['tally_master_matching']=audit
        row['tally_master_matching']=audit
        if party or any(i['stock'] or i['unit'] for i in audit['items']):
            notice='Existing Tally masters assigned from '+ctx['company']+'; invoice values unchanged.'
            row.setdefault('notices',[]).append(notice)
    # Keep original system ledgers only when actually referenced.
    needed={n.text for n in vouchers.iter('LEDGERNAME')}
    for (kind,name),msg in source_masters.items():
        if kind=='LEDGER' and name in needed and ('LEDGER',name) not in output and name not in external['ledgers']:keep(deepcopy(msg))
    for name in list(output_units):
        if name in external['units']:del output_units[name]
    # Exact symbol reuse without an AI assignment still follows the original
    # unit transport path; only explicit AI-approved unit aliases are removed.
    masters.find('.//REQUESTDATA')[:]=list(output.values())
    units.find('.//REQUESTDATA')[:]=list(output_units.values())
    metadata={k:sorted(v) if isinstance(v,set) else v for k,v in external.items()}
    for document in (units,masters,vouchers):document.set(MARKER,json.dumps(metadata,ensure_ascii=False))
    declared={n.get('NAME') for n in masters.findall('.//LEDGER')}|set(metadata['ledgers'])
    if not needed<=declared:raise ValueError('Mapped voucher ledger dependency missing.')
    stock_names={n.get('NAME') for n in masters.findall('.//STOCKITEM')}|set(metadata['stocks'])
    if not {n.text for n in vouchers.iter('STOCKITEMNAME')}<=stock_names:raise ValueError('Mapped inventory dependency missing.')

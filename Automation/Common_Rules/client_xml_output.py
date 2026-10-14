"""One current XML set per client; preserve invoices and bounded rollback output."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from .engine import read_json
from .tally_xml import envelope

LAYOUT='client-current-v1'


def seller_groups(records,client):
    by_name=defaultdict(list)
    for row in records:
        inv=row.get('invoice') or {}
        name=str(inv.get('seller_name') or inv.get('seller_name_candidate') or ('Seller unresolved - '+client)).strip()
        by_name[' '.join(name.split()).casefold()].append(row)
    groups=[]
    for normalized,rows in by_name.items():
        known={str((r.get('invoice') or {}).get('seller_gstin') or '').strip().upper() for r in rows}
        known.discard('')
        partitions=defaultdict(list)
        for row in rows:
            gstin=str((row.get('invoice') or {}).get('seller_gstin') or '').strip().upper()
            # Group membership only: never fill an invoice's missing GSTIN.
            owner=gstin or (next(iter(known)) if len(known)==1 else '')
            partitions[owner].append(row)
        for owner,part in partitions.items():
            inv=part[0].get('invoice') or {}
            label=str(inv.get('seller_name') or inv.get('seller_name_candidate') or ('Seller unresolved - '+client)).strip()
            groups.append((label,owner,part))
    return groups


def signature(node,exclude=()):
    clone=deepcopy(node)
    for child in list(clone):
        if child.tag in exclude:clone.remove(child)
    return ET.canonicalize(ET.tostring(clone,encoding='unicode'),strip_text=True)


def consolidate(documents):
    result=[]
    for index,report in enumerate(('All Masters','All Masters','Vouchers')):
        output,data=envelope('',report)
        variables=output.find('.//STATICVARIABLES')
        variables.remove(variables.find('SVCURRENTCOMPANY'))
        known={}
        for group in documents:
            for msg in group[index].find('.//REQUESTDATA'):
                node=next(iter(msg));identity=(node.tag,node.get('NAME'))
                if index==2:
                    data.append(deepcopy(msg));continue
                if identity not in known:
                    copied=deepcopy(msg);data.append(copied);known[identity]=next(iter(copied));continue
                prior=known[identity]
                if signature(prior)==signature(node):continue
                if node.tag=='UNIT' and signature(prior,('DECIMALPLACES',))==signature(node,('DECIMALPLACES',)):
                    prior.find('DECIMALPLACES').text=str(max(int(prior.findtext('DECIMALPLACES','0')),int(node.findtext('DECIMALPLACES','0'))));continue
                if node.tag=='STOCKITEM' and signature(prior,('GSTDETAILS.LIST',))==signature(node,('GSTDETAILS.LIST',)):
                    rules={signature(rule) for rule in prior.findall('GSTDETAILS.LIST')}
                    for rule in node.findall('GSTDETAILS.LIST'):
                        if signature(rule) not in rules:prior.append(deepcopy(rule));rules.add(signature(rule))
                    continue
                raise ValueError('Conflicting master definitions for '+str(identity)+'; existing current output retained')
        if index==1:data[:]=sorted(data,key=lambda msg:0 if msg.find('LEDGER') is not None else 1)
        result.append(output)
    return result


def publish(base,staging):
    base=Path(base);staging=Path(staging);current=base/'current';previous=base/'previous'
    for folder in (current,previous):
        if folder.exists():
            report=folder/'Batch_Report.json'
            if not report.is_file() or read_json(report).get('layout')!=LAYOUT:
                raise ValueError('Unmanaged files in '+str(folder)+'; refusing to overwrite')
    if previous.exists():shutil.rmtree(previous)
    if current.exists():current.rename(previous)
    try:staging.rename(current)
    except OSError:
        if previous.exists() and not current.exists():previous.rename(current)
        raise
    return current

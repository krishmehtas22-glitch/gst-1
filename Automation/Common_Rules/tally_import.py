"""Send existing XML to local Tally; never regenerate financial output."""
from pathlib import Path
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from .unit_catalog import unit_formal_name
from .tally_units import unit_symbol,prepare_unit_create
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import URLError

ENDPOINT='http://127.0.0.1:9000'


def post_xml(payload,timeout=90):
    # Never route financial XML through an HTTP proxy or a remote server.
    request=Request(ENDPOINT,data=payload,headers={'Content-Type':'text/xml; charset=utf-8'},method='POST')
    try:
        with build_opener(ProxyHandler({})).open(request,timeout=timeout) as response:
            data=response.read(4*1024*1024+1)
    except (URLError,OSError) as exc:
        raise ValueError('Cannot reach Tally on localhost:9000. Open Tally and enable its HTTP/XML server on port 9000 in advanced connectivity settings. If this happened during import, check Tally before retrying; the request may have been applied.') from exc
    if len(data)>4*1024*1024:raise ValueError('Tally response is too large; check the import result in Tally.')
    return data


def response_xml(data):
    try:return ET.fromstring(data)
    except (ET.ParseError,ValueError):raise ValueError('Tally returned an unreadable result. Check Tally before retrying; import status is unknown.') from None


def loaded_companies(transport=post_xml):
    payload=b'''<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>InvoiceReaderCompanies</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="InvoiceReaderCompanies" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>Name</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>'''
    result=response_xml(transport(payload))
    errors=[n.text for n in result.iter('LINEERROR') if n.text]
    if errors:raise ValueError('; '.join(errors))
    names=[]
    for company in result.iter('COMPANY'):
        name=company.get('NAME') or company.findtext('NAME')
        if name and name not in names:names.append(name)
    return names


def import_plan(folder):
    """Snapshot one selected seller's current output, before any external write."""
    folder=Path(folder)
    files=[folder/name for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml')]
    if not files[1].is_file() or not files[2].is_file():
        raise ValueError('Select an invoice with a current XML output set. Multiple sellers must be imported separately into their matching companies.')
    plan=[]
    for file in files:
        if not file.exists():continue  # legacy exports embed units in masters
        data=file.read_bytes();document=response_xml(data)
        report=document.findtext('./BODY/IMPORTDATA/REQUESTDESC/REPORTNAME')
        if document.findtext('./HEADER/TALLYREQUEST')!='Import Data' or report!=('Vouchers' if file.name=='Sales_Vouchers.xml' else 'All Masters'):
            raise ValueError('Unexpected Tally XML envelope in '+file.name)
        plan.append((file.name,data))
    return plan


def seller_identity(row):
    """Letter case/extra spaces do not identify a different seller; GSTIN does."""
    invoice=row.get('extracted_invoice') or {}
    name=row.get('seller') or invoice.get('seller_name') or ''
    gstin=invoice.get('seller_gstin') or row.get('seller_gstin') or ''
    return (' '.join(str(name).split()).casefold(),str(gstin).strip().upper())


def seller_import_plan(run_folder,selected_folder):
    """Combine matching seller sets in memory, leaving all generated files intact."""
    run=Path(run_folder).resolve();selected=Path(selected_folder).resolve()
    original=import_plan(selected)
    report=run/'Batch_Report.json'
    if not report.exists():return original,[selected]
    rows=json.loads(report.read_text(encoding='utf-8')).get('invoices',[])
    by_folder={}
    for row in rows:
        folder=Path(row.get('xml_folder','')).resolve()
        if not folder.is_relative_to(run):raise ValueError('Batch report references XML outside the current run')
        by_folder.setdefault(folder,set()).add(seller_identity(row))
    identity=by_folder.get(selected)
    if not identity or len(identity)!=1:return original,[selected]
    folders=[folder for folder,keys in by_folder.items() if keys==identity]
    if len(folders)<2:return original,[selected]
    plans=[import_plan(folder) for folder in folders]
    combined=[]
    for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml'):
        sources=[data for plan in plans for filename,data in plan if filename==name]
        if not sources:continue
        document=response_xml(sources[0]);destination=document.find('.//REQUESTDATA')
        if destination is None:raise ValueError('XML request data is missing')
        destination[:]=[];seen=set()
        for data in sources:
            source=response_xml(data).find('.//REQUESTDATA')
            if source is None:raise ValueError('XML request data is missing')
            for message in source:
                # Only deduplicate identical prerequisite definitions. Never drop
                # vouchers or resolve differing master definitions by guessing.
                signature=ET.canonicalize(ET.tostring(message,encoding='unicode'),strip_text=True)
                if name!='Sales_Vouchers.xml' and signature in seen:continue
                seen.add(signature);destination.append(message)
        combined.append((name,ET.tostring(document,encoding='utf-8',xml_declaration=True)))
    return combined,folders


def client_import_groups(run_folder,selected_folder):
    """Every manifest XML folder is included, with distinct seller destinations."""
    run=Path(run_folder).resolve();selected=Path(selected_folder).resolve()
    path=run/'Batch_Report.json'
    if not path.exists():
        return [{'label':'Selected XML set','plan':import_plan(selected),'folders':[selected]}]
    manifest=json.loads(path.read_text(encoding='utf-8'))
    rows=manifest.get('invoices',[])
    if manifest.get('layout')=='client-current-v1':
        return consolidated_import_groups(run,selected,manifest)
    identities={};folders=set()
    for row in rows:
        folder=Path(row.get('xml_folder','')).resolve()
        if not folder.is_relative_to(run):raise ValueError('Batch report references XML outside the current run')
        folders.add(folder)
        identity=seller_identity(row)
        identities.setdefault(identity,{'folder':folder,'label':row.get('seller') or 'Seller unresolved'})
    if selected not in folders:raise ValueError('Selected XML folder is not part of the current run')
    groups=[];covered=set()
    for (name,gstin),info in identities.items():
        plan,group_folders=seller_import_plan(run,info['folder'])
        if covered.intersection(group_folders):raise ValueError('Ambiguous seller identity in current XML folders')
        covered.update(group_folders)
        groups.append({'label':info['label']+(' — '+gstin if gstin else ' — GSTIN not supplied'),
                       'plan':plan,'folders':group_folders})
    if covered!=folders:raise ValueError('Not all current XML folders are covered by the import plan')
    return groups


def consolidated_import_groups(run,selected,manifest):
    """Route a single complete client set without altering voucher contents."""
    from copy import deepcopy
    if selected!=run:raise ValueError('Select the current client XML folder')
    plan=import_plan(run)
    if json.loads((run/'Batch_Report.json').read_text(encoding='utf-8')).get('generation')!=manifest.get('generation'):
        raise ValueError('Client XML was updated while reading; reopen Import to Tally')
    documents={name:response_xml(data) for name,data in plan}
    vouchers=documents['Sales_Vouchers.xml'].findall('.//VOUCHER')
    guids=[v.findtext('GUID') for v in vouchers]
    rows=manifest['invoices'];expected=[row['voucher_guid'] for row in rows]
    if len(set(guids))!=len(guids) or len(set(expected))!=len(expected) or set(guids)!=set(expected):
        raise ValueError('Client report and voucher identities do not match')
    if len(rows)!=manifest.get('input_count') or len(rows)!=manifest.get('xml_voucher_count'):
        raise ValueError('Client batch count is incomplete')
    partitions={}
    for row in rows:
        if Path(row['xml_folder']).resolve()!=run:raise ValueError('Report references another client XML folder')
        partitions.setdefault(row['seller_group'],[]).append(row)
    groups=[]
    for identity,part in partitions.items():
        wanted={row['voucher_guid'] for row in part}
        selected_vouchers=[v for v in vouchers if v.findtext('GUID') in wanted]
        ledgers={n.text for v in selected_vouchers for n in v.iter('LEDGERNAME')}
        stocks={n.text for v in selected_vouchers for n in v.iter('STOCKITEMNAME')}
        master_nodes=documents['Masters.xml'].find('.//REQUESTDATA')
        chosen=[msg for msg in master_nodes if any((n.tag=='LEDGER' and n.get('NAME') in ledgers) or
                    (n.tag=='STOCKITEM' and n.get('NAME') in stocks) for n in msg)]
        declared_ledgers={n.get('NAME') for msg in chosen for n in msg if n.tag=='LEDGER'}
        declared_stocks={n.get('NAME') for msg in chosen for n in msg if n.tag=='STOCKITEM'}
        if not ledgers<=declared_ledgers or not stocks<=declared_stocks:
            raise ValueError('Client vouchers reference missing prerequisite masters')
        units={n.findtext('BASEUNITS') for msg in chosen for n in msg if n.tag=='STOCKITEM'}
        chosen_units=[msg for msg in documents['Units.xml'].find('.//REQUESTDATA') if unit_symbol(msg.find('UNIT')) in units]
        if units!={unit_symbol(msg.find('UNIT')) for msg in chosen_units}:
            raise ValueError('Client stock masters reference missing units')
        filtered=[]
        for filename in ('Units.xml','Masters.xml','Sales_Vouchers.xml'):
            doc=deepcopy(documents[filename]);dest=doc.find('.//REQUESTDATA')
            if filename=='Sales_Vouchers.xml':
                dest[:]=[msg for msg in dest if msg.findtext('VOUCHER/GUID') in wanted]
            else:dest[:]=deepcopy(chosen_units if filename=='Units.xml' else chosen)
            filtered.append((filename,ET.tostring(doc,encoding='utf-8',xml_declaration=True)))
        first=part[0];gstin=first['seller_group_gstin']
        groups.append({'group_id':identity,'generation':manifest['generation'],'label':first['seller_group_label']+(' — '+gstin if gstin else ' — GSTIN not supplied'),
                       'plan':plan if len(partitions)==1 else filtered,'folders':[run]})
    return groups


def voucher_count(plan):
    return sum(len(response_xml(data).findall('.//VOUCHER')) for name,data in plan if name=='Sales_Vouchers.xml')


def company_payload(data,company):
    """Only set the transport destination; retain every exported business element."""
    if not company or not company.strip():raise ValueError('Select the destination Tally company.')
    document=response_xml(data)
    desc=document.find('./BODY/IMPORTDATA/REQUESTDESC')
    if desc is None:raise ValueError('XML import descriptor is missing')
    variables=desc.find('STATICVARIABLES')
    if variables is None:variables=ET.SubElement(desc,'STATICVARIABLES')
    for node in list(variables):
        if node.tag=='SVCURRENTCOMPANY':variables.remove(node)
    ET.SubElement(variables,'SVCURRENTCOMPANY').text=company
    return ET.tostring(document,encoding='utf-8',xml_declaration=True)


def loaded_units(company,transport=post_xml):
    document=ET.fromstring('''<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>InvoiceReaderUnits</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="InvoiceReaderUnits" ISMODIFY="No"><TYPE>Unit</TYPE><FETCH>Name,OriginalName,MailingName,DecimalPlaces,IsSimpleUnit,GSTRepUOM</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''')
    ET.SubElement(document.find('.//STATICVARIABLES'),'SVCURRENTCOMPANY').text=company
    response=response_xml(transport(ET.tostring(document,encoding='utf-8')))
    errors=[n.text for n in response.iter('LINEERROR') if n.text]
    if errors or response.findtext('.//STATUS')=='0':raise ValueError('Cannot verify existing Tally units: '+ '; '.join(errors))
    # Tally also emits a scalar <UNIT>count</UNIT>; it is not a unit master.
    masters=[n for n in response.iter('UNIT') if n.get('NAME') or n.findtext('NAME')]
    if response.find('.//COLLECTION') is None and not masters:
        raise ValueError('Tally returned no unit collection; import stopped before changing masters')
    return masters


def prepare_units(data,existing):
    """Merge symbol duplicates, reuse existing units, disambiguate formal names."""
    from copy import deepcopy
    document=response_xml(data);destination=document.find('.//REQUESTDATA')
    if destination is None:raise ValueError('Unit request data is missing')
    by_name={};messages={}
    def key(name):return ' '.join(str(name or '').split()).casefold()
    def decimals(node):
        value=int(node.findtext('DECIMALPLACES','0'))
        if not 0<=value<=6:raise ValueError('Unit decimal precision is invalid')
        return value
    for message in list(destination):
        for unit in message:
            if unit.tag!='UNIT':raise ValueError('Unexpected master in Units.xml')
            name=unit_symbol(unit);identity=key(name)
            if not identity:raise ValueError('Unit symbol is missing')
            if identity in by_name:
                prior=by_name[identity]
                if any(key(prior.findtext(tag))!=key(unit.findtext(tag)) for tag in ('ISSIMPLEUNIT','GSTREPUOM')):
                    raise ValueError('Conflicting unit definitions for '+name)
                precision=max(decimals(prior),decimals(unit))
                node=prior.find('DECIMALPLACES')
                if node is None:node=ET.SubElement(prior,'DECIMALPLACES')
                node.text=str(precision)
            else:
                by_name[identity]=deepcopy(unit)
                single=deepcopy(message);single[:]=[deepcopy(unit)];messages[identity]=single
    existing_by_name={key(unit_symbol(n)):n for n in existing}
    reserved=set(by_name)
    for present in existing:
        reserved.update(key(value) for value in (present.get('NAME'),present.findtext('NAME'),
                        present.findtext('ORIGINALNAME'),present.findtext('MAILINGNAME')) if value)
    destination[:]=[];reused=[];renamed=[]
    for identity,unit in by_name.items():
        name=unit_symbol(unit);present=existing_by_name.get(identity)
        if present is not None:
            if key(present.findtext('ISSIMPLEUNIT','Yes'))!=key(unit.findtext('ISSIMPLEUNIT','Yes')):
                raise ValueError('Existing unit '+name+' has a different simple/compound type')
            if decimals(present)<decimals(unit):
                raise ValueError('Existing unit '+name+' needs decimal precision '+str(decimals(unit))+'; increase it in Tally before importing. Quantities were not rounded.')
            reused.append(name);continue
        # Verified against the user's native Tally unit export: NAME is the
        # symbol, ORIGINALNAME/MAILINGNAME carry the formal description.
        original=unit.findtext('ORIGINALNAME') or name
        formal=unit.findtext('ADDITIONALNAME') or unit.findtext('MAILINGNAME') or (original if key(original)!=identity else '')
        old_mailing=unit.findtext('MAILINGNAME')
        legacy_additional=unit.find('ADDITIONALNAME') is not None
        # Tally names must not repeat the symbol, another unit's symbol or
        # formal name. Change only the descriptive field on the transport copy.
        formal=unit_formal_name(name,formal)
        if key(formal) in reserved:
            base=formal+' [unit '+name+']';formal=base;index=2
            while key(formal) in reserved:
                formal=base+' '+str(index);index+=1
        if formal:reserved.add(key(formal))
        prepare_unit_create(unit,name,formal)
        if original!=formal or old_mailing!=formal or legacy_additional:
            renamed.append({'unit':name,'original_name':formal,'formal_name':formal})
        message=messages[identity];message[:]=[unit];destination.append(message)
    return ET.tostring(document,encoding='utf-8',xml_declaration=True),reused,renamed


def import_reply(raw):
    response=response_xml(raw)
    counts={tag:int(response.findtext('.//'+tag,'0')) for tag in ('CREATED','ALTERED','IGNORED','ERRORS','CANCELLED','DELETED','EXCEPTIONS')}
    errors=[n.text for n in response.iter('LINEERROR') if n.text]
    if response.findtext('.//STATUS')=='0':errors.append('Tally returned failure status')
    if not any(response.find('.//'+tag) is not None for tag in counts):
        errors.append('No import counters returned; status unknown. Check Tally before retrying.')
    return counts,errors


def reply_status(raw):
    """Counters distinguish a reported rejection from an unknown import result."""
    doc=response_xml(raw)
    return 'reported' if any(doc.find('.//'+tag) is not None for tag in
                            ('CREATED','ALTERED','IGNORED','ERRORS','CANCELLED','DELETED','EXCEPTIONS')) else 'unknown'


def send_plan(plan,company,transport=post_xml,progress=lambda text:None,*,units_already_available=False,submit_all=False):
    """Submit once; ALL mode retains reported errors and attempts later stages.

    An unknown response still stops dispatch: no ambiguous import is retried.
    """
    if company not in loaded_companies(transport):raise ValueError('The selected company is no longer available in Tally. Open it in Tally and refresh the company list.')
    results=[]
    for name,data in plan:
        if name=='Units.xml' and units_already_available:
            results.append({'file':name,'company':company,'errors':[],'counts':{},'skipped':True,
                            'reason':'Explicit masters-and-vouchers-only import; user indicates units already available'})
            continue
        progress('Importing '+name+' into '+company+'…')
        try:
            reused=[];renamed=[];attempted_units=[];unit_definitions=None;counts={};unit_results=[];existing_definitions=[];request=None;attempted=False;raw_response=None
            if name=='Units.xml':
                existing=loaded_units(company,transport)
                existing_definitions=[ET.tostring(node,encoding='unicode') for node in existing]
                data,reused,renamed=prepare_units(data,existing)
                pending_units=[unit_symbol(n) for n in response_xml(data).findall('.//UNIT')]
                unit_definitions=data.decode('utf-8')
                if not pending_units:
                    results.append({'file':name,'company':company,'errors':[],'counts':{},'existing_units_reused':reused,'existing_unit_definitions':existing_definitions,'skipped':True})
                    continue
            if name=='Units.xml':
                from copy import deepcopy
                template=response_xml(data);counts={};errors=[];unit_results=[]
                for message in template.find('.//REQUESTDATA'):
                    single=deepcopy(template);destination=single.find('.//REQUESTDATA')
                    destination[:]=[deepcopy(message)]
                    symbol=unit_symbol(message.find('UNIT'))
                    progress('Creating unit '+symbol+' in '+company+'…')
                    request=company_payload(ET.tostring(single,encoding='utf-8'),company);attempted=True
                    attempted_units.append(symbol)
                    raw_response=None
                    raw_response=transport(request)
                    reported,issues=import_reply(raw_response)
                    status=reply_status(raw_response)
                    unit_results.append({'unit':symbol,'counts':reported,'errors':issues,'status':status,'request_xml':request.decode('utf-8'),
                                         'response_xml':raw_response.decode('utf-8',errors='replace')})
                    for tag,value in reported.items():counts[tag]=counts.get(tag,0)+value
                    errors.extend('Unit '+symbol+': '+issue for issue in issues)
                    if status=='unknown' or (not submit_all and (issues or any(reported.get(tag,0) for tag in ('ERRORS','CANCELLED','EXCEPTIONS')))):break
                entry={'file':name,'company':company,'counts':counts,'errors':errors,
                       'attempted_units':attempted_units,
                       'unit_request_xml':unit_definitions,'unit_results':unit_results,'existing_unit_definitions':existing_definitions,
                       'status':'unknown' if any(r['status']=='unknown' for r in unit_results) else 'reported','request_attempted':attempted}
            else:
                request=company_payload(data,company);attempted=True
                raw_response=None
                raw_response=transport(request)
                counts,errors=import_reply(raw_response)
                entry={'file':name,'company':company,'counts':counts,'errors':errors,'status':reply_status(raw_response),
                       'request_attempted':True,'request_xml':request.decode('utf-8'),
                       'response_xml':raw_response.decode('utf-8',errors='replace')}
                if name=='Sales_Vouchers.xml':entry['requested_vouchers']=len(response_xml(data).findall('.//VOUCHER'))
            if reused:entry['existing_units_reused']=reused
            if renamed:entry['unit_original_names_adjusted']=renamed
        except (ValueError,OSError) as exc:
            entry={'file':name,'company':company,'errors':[str(exc)],'status':'unknown','request_attempted':attempted}
            if request is not None:entry['request_xml']=request.decode('utf-8')
            if raw_response is not None:entry['response_xml']=raw_response.decode('utf-8',errors='replace')
            if name=='Sales_Vouchers.xml':entry['requested_vouchers']=len(response_xml(data).findall('.//VOUCHER'))
            if name=='Units.xml':
                entry.update(counts=counts,unit_results=unit_results,attempted_units=attempted_units,unit_request_xml=unit_definitions,existing_unit_definitions=existing_definitions)
                if reused:entry['existing_units_reused']=reused
        results.append(entry)
        failed=entry.get('errors') or any(entry.get('counts',{}).get(tag,0) for tag in ('ERRORS','CANCELLED','EXCEPTIONS'))
        if entry.get('status')=='unknown' or (failed and not submit_all):break
        if failed and name!='Sales_Vouchers.xml':entry['continued_after_reported_error']=True
    return results


def tally_executable(root):
    settings=Path(root)/'.invoice_app'/'tally_connection.json'
    try:
        saved=json.loads(settings.read_text(encoding='utf-8')).get('executable')
        if saved and Path(saved).is_file():return Path(saved)
    except (OSError,ValueError):pass
    for base in (os.environ.get('ProgramFiles','C:/Program Files'),os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'), 'C:/TallyPrime','C:/Tally.ERP9'):
        for suffix in ('TallyPrime/tally.exe','Tally.ERP9/tally.exe','tally.exe'):
            candidate=Path(base)/suffix
            if candidate.is_file():return candidate
    return None


def launch_tally(path):
    path=Path(path)
    if os.name!='nt':raise ValueError('Automatic Tally launch requires Windows.')
    if not path.is_file() or path.suffix.lower()!='.exe':raise ValueError('Choose your installed Tally executable.')
    subprocess.Popen([str(path)],cwd=str(path.parent))

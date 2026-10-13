"""Send existing XML to local Tally; never regenerate financial output."""
from pathlib import Path
import json
import os
import subprocess
import xml.etree.ElementTree as ET
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
    rows=json.loads(path.read_text(encoding='utf-8')).get('invoices',[])
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


def send_plan(plan,company,transport=post_xml,progress=lambda text:None):
    """No automatic retry: a lost response may follow a committed Tally import."""
    if company not in loaded_companies(transport):raise ValueError('The selected company is no longer available in Tally. Open it in Tally and refresh the company list.')
    results=[]
    for name,data in plan:
        progress('Importing '+name+' into '+company+'…')
        try:
            response=response_xml(transport(company_payload(data,company)))
            counts={tag:int(response.findtext('.//'+tag,'0')) for tag in ('CREATED','ALTERED','IGNORED','ERRORS','CANCELLED','DELETED')}
            errors=[n.text for n in response.iter('LINEERROR') if n.text]
            if response.findtext('.//STATUS')=='0':errors.append('Tally returned failure status')
            if not any(response.find('.//'+tag) is not None for tag in counts):
                errors.append('No import counters returned; status unknown. Check Tally before retrying.')
            entry={'file':name,'company':company,'counts':counts,'errors':errors}
        except (ValueError,OSError) as exc:
            entry={'file':name,'company':company,'errors':[str(exc)],'status':'unknown'}
        results.append(entry)
        if entry.get('errors') or any(entry.get('counts',{}).get(tag,0) for tag in ('ERRORS','CANCELLED')):break
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

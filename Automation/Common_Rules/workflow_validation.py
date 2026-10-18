"""AI-first output checks and explicit, exact-output conflict acknowledgements."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,re
import xml.etree.ElementTree as ET
from .accounting import STATES,state_code,gstin_valid
from .invoice_dates import normalize_date
from .export_metadata import is_export
from .engine import read_json,write_json

MARKER='BILLSYNCREVIEW'


def enable(root):
    path=Path(root)/'.invoice_app'/'workflow_policy.json'
    if not path.exists():write_json(path,{'version':1,'ai_first_validation':True})


def enabled(root):
    path=Path(root)/'.invoice_app'/'workflow_policy.json'
    return path.exists() and read_json(path).get('ai_first_validation') is True


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def issue(number,field,invoice,master,reason,blocking=False):
    return {'invoice_number':number or '(missing)','field':field,'invoice':str(invoice or ''),
            'master':str(master or ''),'reason':reason,'blocking':blocking}


def choice_id(value):return value.get('id') if isinstance(value,dict) else None


def state(value,gstin=''):
    if value:
        try:return STATES[state_code(value)]
        except ValueError:return ''
    if gstin_valid(str(gstin or '').upper()):return STATES.get(gstin[:2],'')
    return ''


def checks(inv):
    no=inv.get('number');result=[];export=is_export(inv)
    def add(field,value,reason,blocking=False,master=''):
        result.append(issue(no,field,value,master,reason,blocking))
    if not str(no or '').strip() or str(no).startswith('UNREAD-'):add('Invoice number',no,'Enter the printed invoice number.',True)
    if not normalize_date(inv.get('date')):add('Invoice date',inv.get('date'),'Enter the printed invoice date.',True)
    if not str(inv.get('buyer_name') or '').strip():add('Buyer name','','Enter the printed buyer name.',True)
    if not str(inv.get('seller_name') or '').strip():add('Seller name','','Enter the printed supplier name.',True)
    for role in ('seller','buyer'):
        gstin=str(inv.get(role+'_gstin') or '').strip().upper();printed=inv.get(role+'_state')
        if gstin and not gstin_valid(gstin):add(role.title()+' GSTIN',gstin,'GSTIN fails format/checksum validation; printed value is retained.')
        if role=='seller' and not gstin:add('Seller GSTIN','','Seller GSTIN is missing; verify the supplier registration.')
        if role=='buyer' and export:continue
        resolved=state(printed,gstin)
        if not resolved:add(role.title()+' state',printed,'Provide a valid Indian state; no state was guessed.',True)
        elif printed and gstin_valid(gstin) and state('',gstin)!=resolved:
            add(role.title()+' state',printed,'Printed state differs from GSTIN state.',master=state('',gstin))
    if not export and not state(inv.get('place_of_supply')):
        add('Place of supply',inv.get('place_of_supply'),'Enter the invoice place of supply separately from buyer state.',True)
    for index,item in enumerate(inv.get('items') or [],1):
        if not str(item.get('name') or '').strip():add('Item '+str(index)+' name','','Complete the printed product/service name.',True)
        if not str(item.get('unit') or '').strip():add('Item '+str(index)+' unit','','Complete the printed or AI-inferred selling unit.',True)
        from decimal import Decimal,InvalidOperation
        try:
            quantity=Decimal(str(item.get('quantity','')))
            if not quantity.is_finite() or quantity<=0:raise ValueError()
        except (ValueError,InvalidOperation):add('Item '+str(index)+' quantity',item.get('quantity'),'Enter a positive exact quantity.',True)
    from .accounting import cents,money
    try:
        total=cents(inv['total']);taxable=cents(inv['taxable'])
        tax=sum(cents(inv.get(t) or '0') for t in ('cgst','sgst','igst','cess','round_off'))
        if total!=taxable+tax:add('Invoice totals',str(total),'Printed total differs from taxable value plus taxes/round-off; values are not changed.',master=str(taxable+tax))
        values=[cents(i['value']) for i in inv.get('items') or []]
        if values and sum(values)!=taxable:add('Item totals',str(sum(values)),'Item values do not match the taxable total; review the source.',master=str(taxable))
        items=inv.get('items') or []
        if inv.get('classification') in ('taxable','export_igst') and items:
            for head in ('cgst','sgst','igst'):
                if all(i.get(head+'_rate') not in (None,'') for i in items):
                    expected=sum(cents(money(i['value'])*money(i[head+'_rate'])/100) for i in items)
                    actual=cents(inv.get(head) or '0')
                    if abs(expected-actual)>money('.01')*len(items):add(head.upper()+' reconciliation',str(actual),'Printed invoice tax differs from its item tax components; values are preserved.',master=str(expected))
    except (ValueError,KeyError,TypeError,ArithmeticError):add('Invoice amounts','','Provide valid taxable, total and item amounts.',True)
    if inv.get('ocr_reading_evidence'):add('OCR evidence','Uncertain characters','Compare unclear text with the source before import.')
    if export:
        expected={'export_lut':'LUT_without_payment','export_igst':'with_payment_of_IGST'}.get(inv.get('classification'))
        if not expected or inv.get('export_mode')!=expected:add('Export mode',inv.get('export_mode'),'Confirm the printed LUT/IGST export treatment.',True)
        if not inv.get('items'):add('Export inventory','','Export stock movement requires item rows.',True)
        for index,item in enumerate(inv.get('items') or [],1):
            try:
                rates=[money(item[t+'_rate']) for t in ('cgst','sgst','igst')]
                if any(r<0 for r in rates):raise ValueError()
            except (KeyError,ValueError,ArithmeticError,TypeError):add('Item '+str(index)+' GST rate','','Complete item GST rates for export inventory; no rate is guessed.',True)
        add('Export GST reporting',inv.get('export_mode'),'Items and stock movement are included. Confirm the destination Sales ledger/export GST nature in Tally; printed tax amounts and LUT/IGST mode are retained.')
    return result


def voucher_hash(voucher):
    return hashlib.sha256(ET.canonicalize(ET.tostring(voucher,encoding='unicode'),strip_text=True).encode()).hexdigest()


def input_state(root,record):
    """A later manual correction/cache/matching/rate edit invalidates old XML."""
    from .ai_providers import PROVIDERS,reader
    from .tally_master_matching import match_path
    from .foreign_currency import settings_path
    base=Path(root)/'.invoice_app';identity=record['digest']+'.json'
    paths=[base/'reviews'/identity,base/'api_selection'/identity,match_path(root,record),settings_path(root,record)]
    paths.extend(reader(provider).cache_path(root,record) for provider in PROVIDERS)
    return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else '' for p in paths}


def attach(root,records,report,masters,vouchers):
    """Add domestic state metadata and review facts after master references apply."""
    if not enabled(root):return
    from .tally_master_matching import context,details,loaded_choices,norm
    from .foreign_currency import for_record
    entries=[]
    for record,row,voucher in zip(records,report,vouchers.findall('.//VOUCHER')):
        inv=for_record(root,record);no=inv.get('number') or '';problems=checks(inv)
        from .tally_review_export import clean
        # Supplier registration is a company field; never put it in PARTYGSTIN.
        supplier_gstin=clean(inv.get('seller_gstin')).strip().upper()
        for tag,value in [('CMPGSTIN',supplier_gstin),('CMPGSTSTATE',state(inv.get('seller_state'),supplier_gstin))]:
            if value:
                node=voucher.find(tag)
                if node is None:node=ET.SubElement(voucher,tag)
                node.text=value
        gstin=clean(inv.get('buyer_gstin')).strip().upper()
        if gstin:
            node=voucher.find('PARTYGSTIN')
            if node is not None:node.text=gstin
            for ledger in masters.iter('LEDGER'):
                if ledger.get('NAME')==voucher.findtext('PARTYLEDGERNAME'):
                    node=ledger.find('PARTYGSTIN')
                    if node is not None:node.text=gstin
        if is_export(inv) and not voucher.findall('ALLINVENTORYENTRIES.LIST'):
            problems.append(issue(no,'Export inventory','','','Complete/reconcile item quantities, values and rates before export stock movement.',True))
        # A placeholder must never masquerade as an actual invoice number.
        if not no:
            voucher.find('VOUCHERNUMBER').text='';voucher.find('REFERENCE').text=''
            row['invoice_number']=''
        if not is_export(inv):
            buyer_state=state(inv.get('buyer_state'),inv.get('buyer_gstin'))
            for tag,value in [('STATENAME',buyer_state),('COUNTRYOFRESIDENCE','India')]:
                if value:
                    node=voucher.find(tag)
                    if node is None:node=ET.SubElement(voucher,tag)
                    node.text=value
            party=voucher.findtext('PARTYLEDGERNAME')
            for ledger in masters.iter('LEDGER'):
                if ledger.get('NAME')==party:
                    for tag,value in [('LEDSTATENAME',buyer_state),('COUNTRYNAME','India')]:
                        if value:
                            node=ledger.find(tag)
                            if node is None:node=ET.SubElement(ledger,tag)
                            node.text=value
            pos=state(inv.get('place_of_supply'))
            if pos:
                node=voucher.find('PLACEOFSUPPLY')
                if node is None:node=ET.SubElement(voucher,'PLACEOFSUPPLY')
                node.text=pos
        ctx=context(root,record);snapshot=ctx['sha256'] if ctx else ''
        if ctx:
            catalog=details(ctx);raw=loaded_choices(root,record,ctx) or {}
            proposed=catalog.get(choice_id(raw.get('party')))
            # Even an AI null choice must not hide a same-name/different-ID party.
            nearby=[e for e in catalog.values() if e['kind']=='ledgers' and norm(e['name'])==norm(inv.get('buyer_name'))]
            candidates=([proposed] if proposed and proposed.get('kind')=='ledgers' else [])+nearby
            seen=set()
            for existing in candidates:
                if existing['id'] in seen:continue
                seen.add(existing['id'])
                if norm(inv.get('buyer_gstin'))!=norm(existing['gstin']):
                    problems.append(issue(no,'Buyer GSTIN',inv.get('buyer_gstin'),existing['gstin'],
                        'Existing ledger '+existing['name']+' has a different GSTIN. The invoice party is kept separate; no existing GSTIN is overwritten.'))
                actual=state(inv.get('buyer_state'),inv.get('buyer_gstin'));known=state(existing.get('state'),existing.get('gstin'))
                if actual and known and actual!=known:
                    problems.append(issue(no,'Buyer state',actual,known,'Existing ledger '+existing['name']+' has a different state; review its identity.'))
                if existing['address'] and inv.get('buyer_address') and existing['address']!=norm(inv['buyer_address']):
                    problems.append(issue(no,'Buyer address',inv['buyer_address'],existing['address'],'Existing ledger '+existing['name']+' has a different address; printed invoice details are retained.'))
                if existing['country'] and inv.get('buyer_country') and norm(existing['country'])!=norm(inv['buyer_country']):
                    problems.append(issue(no,'Buyer country',inv['buyer_country'],existing['country'],'Existing ledger '+existing['name']+' has a different country.'))
            matched=row.get('tally_master_matching',{}).get('items',[])
            reported=set()
            for item_choice in raw.get('items',[]) if isinstance(raw.get('items'),list) else []:
                if not isinstance(item_choice,dict):continue
                index=item_choice.get('index')
                if type(index) is not int or not 0<=index<len(inv.get('items',[])):continue
                proposed_stock=catalog.get(choice_id(item_choice.get('stock')))
                reused=next((i.get('stock') for i in matched if i['index']==index),None)
                if proposed_stock and proposed_stock['kind']=='stock_items' and not reused:
                    reported.add(index)
                    problems.append(issue(no,'Item '+str(index+1)+' master',inv['items'][index].get('name'),proposed_stock['name'],
                        'Proposed stock was incompatible or ambiguous (HSN, GST components, unit, precision or variant). Current new-master creation is used.'))
                proposed_unit=catalog.get(choice_id(item_choice.get('unit')))
                reused_unit=next((i.get('unit') for i in matched if i['index']==index),None)
                if proposed_unit and proposed_unit['kind']=='units' and not reused_unit:
                    problems.append(issue(no,'Item '+str(index+1)+' unit',inv['items'][index].get('unit'),proposed_unit['name'],
                        'Proposed unit was incompatible or ambiguous. The original selling measure and exact quantity are retained.'))
            for index,item in enumerate(inv.get('items') or []):
                reused=next((i.get('stock') for i in matched if i['index']==index),None)
                same=[e for e in catalog.values() if e['kind']=='stock_items' and norm(e['name'])==norm(item.get('name'))]
                if same and not reused and index not in reported:
                    problems.append(issue(no,'Item '+str(index+1)+' master',item.get('name'),', '.join(e['name'] for e in same),
                        'Same-name stock exists but its HSN/GST/unit/variant could not be reused. Review before creating a separate master.'))
        status=record.get('ai_first_status')
        if status and status not in ('extracted','approved_review'):
            problems.append(issue(no,'AI extraction',status,'','This invoice has not completed AI extraction or a human review.',True))
        source=Path(record.get('source_path') or record['path'])
        from .source_documents import verify_source
        try:verify_source(Path(root),record)
        except (ValueError,OSError):problems.append(issue(no,'Source invoice',str(source),'','Source is missing, changed or outside the invoice folder; re-process it.',True))
        source_hash=record.get('source_sha256',record.get('digest',''))
        data={'guid':voucher.findtext('GUID'),'invoice':deepcopy(inv),'issues':problems,
              'client':record['client'],'root':str(Path(root).resolve()),'snapshot_sha256':snapshot,
              'source':str(source.resolve()),'source_sha256':source_hash,'read_path':str(Path(record['path']).resolve()),
              'read_sha256':record.get('digest',''),'input_state':input_state(root,record),'voucher_sha256':voucher_hash(voucher)}
        entries.append(data);record['workflow_issues']=problems;row['workflow_issues']=problems
        record['workflow_ready']=not problems;row['workflow_ready']=not problems
        if problems:record['display_status']='Correction required' if any(p['blocking'] for p in problems) else 'Review conflicts before import'
    vouchers.set(MARKER,json.dumps({'version':1,'entries':entries},ensure_ascii=False))


def cannot_override(problem):
    """Data disagreements are reviewable; stale/unverified inputs are not."""
    return problem.get('blocking',False) and problem.get('field') in {
        'Source invoice','Saved invoice review','Tally snapshot','AI extraction'}


def link_source(problem,entry):
    return {**problem,'source':entry['source'],'read_path':entry['read_path'],
            'read_sha256':entry['read_sha256'],'root':entry['root'],'guid':entry['guid']}


class WorkflowReviewRequired(ValueError):
    def __init__(self,issues,token,company):
        self.issues=issues;self.token=token;self.company=company
        super().__init__('Invoice workflow review required. No import sent. '+ '; '.join(p['invoice_number']+': '+p['field']+' — '+p['reason'] for p in issues))


def company_facts(company,transport):
    from .tally_import import response_xml
    doc=ET.fromstring('''<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>BillSyncWorkflowCompany</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="BillSyncWorkflowCompany" ISMODIFY="No"><TYPE>Company</TYPE><FETCH>Name,StateName,GSTIN,GSTRegistrationDetails</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>''')
    ET.SubElement(doc.find('.//STATICVARIABLES'),'SVCURRENTCOMPANY').text=company
    raw=transport(ET.tostring(doc,encoding='utf-8'))
    if isinstance(raw,bytes):
        encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-16-le' if raw.startswith(b'<\x00') else 'utf-16-be' if raw.startswith(b'\x00<') else 'utf-8-sig'
        try:raw=raw.decode(encoding)
        except UnicodeError:raise ValueError('Unreadable company registration response; no import sent.') from None
    def control(match):
        value=int(match[1][1:],16) if match[1].startswith(('x','X')) else int(match[1])
        return '' if value<32 and value not in (9,10,13) else match[0]
    raw=re.sub(r'&#(x[0-9a-fA-F]+|X[0-9a-fA-F]+|[0-9]+);',control,raw)
    raw=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',raw)
    raw=re.sub(r'^\s*<\?xml[^?]*\?>','',raw)
    result=response_xml(raw)
    if result.find('.//LINEERROR') is not None or result.findtext('.//STATUS')=='0':raise ValueError('Cannot verify destination company registration; no import sent. Refresh/open the company in Tally.')
    nodes=[n for n in result.iter('COMPANY') if (n.get('NAME') or n.findtext('NAME'))==company]
    if len(nodes)!=1:raise ValueError('Destination company was not returned unambiguously; no import sent.')
    gstins=sorted({str(n.text or '').strip().upper() for n in nodes[0].iter() if n.tag in ('GSTIN','GSTREGISTRATIONNUMBER') and str(n.text or '').strip()})
    states=sorted({str(n.text or '').strip() for n in nodes[0].iter() if n.tag in ('STATENAME','LEDSTATENAME') and str(n.text or '').strip()})
    return {'company':company,'gstins':gstins,'states':states}


def require_plan(plan,company,transport):
    from .tally_import import response_xml
    problems=[];entries=[];approvals=[]
    for name,data in plan:
        if name!='Sales_Vouchers.xml':continue
        doc=response_xml(data);raw=doc.get(MARKER)
        if not raw:continue  # Legacy entry points retain their existing behavior.
        metadata=json.loads(raw)
        if metadata.get('version')!=1:raise ValueError('Unsupported invoice workflow metadata; re-process invoices.')
        by_guid={entry['guid']:entry for entry in metadata['entries']}
        approvals.append(metadata.get('acknowledgement'))
        for voucher in doc.findall('.//VOUCHER'):
            entry=by_guid.get(voucher.findtext('GUID'))
            if not entry or entry['voucher_sha256']!=voucher_hash(voucher):raise ValueError('Invoice XML changed after validation; re-process before import. No import sent.')
            entries.append(entry);problems.extend(link_source(p,entry) for p in entry['issues'])
            start=len(problems)
            source=Path(entry['source'])
            for path,sha in ((source,entry['source_sha256']),(Path(entry['read_path']),entry['read_sha256'])):
                if not sha or path.is_symlink() or not path.resolve().is_relative_to(Path(entry['root']).resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
                    problems.append(issue(entry['invoice'].get('number'),'Source invoice',str(path),'','Source is missing or changed; re-process it.',True))
            for path,expected in entry['input_state'].items():
                file=Path(path)
                if not file.resolve().is_relative_to(Path(entry['root']).resolve()):raise ValueError('Invalid workflow input path; no import sent.')
                actual=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else ''
                if actual!=expected:
                    problems.append(issue(entry['invoice'].get('number'),'Saved invoice review','','','Review, AI read, currency rate or master choice changed after XML creation; prepare XML again.',True));break
            from .tally_master_matching import context
            ctx=context(entry['root'],{'client':entry['client']})
            if (ctx['sha256'] if ctx else '')!=entry['snapshot_sha256']:
                problems.append(issue(entry['invoice'].get('number'),'Tally snapshot','','','Selected masters changed; re-process invoices.',True))
            problems[start:]=[link_source(p,entry) for p in problems[start:]]
    if not entries:return
    facts=None
    if not any(cannot_override(p) for p in problems):
        facts=company_facts(company,transport)
        for entry in entries:
            start=len(problems)
            inv=entry['invoice'];gstin=str(inv.get('seller_gstin') or '').strip().upper()
            if not facts['gstins']:
                problems.append(issue(inv.get('number'),'Destination GSTIN',gstin,'Not returned by Tally','Company registration could not be verified. Confirm the chosen company before proceeding.'))
            elif gstin not in facts['gstins']:
                problems.append(issue(inv.get('number'),'Destination GSTIN',gstin,', '.join(facts['gstins']),'Supplier GSTIN differs from the selected Tally company registration.'))
            seller_state=state(inv.get('seller_state'),gstin)
            known={state(s) for s in facts['states']};known.discard('')
            if seller_state and known and seller_state not in known:
                problems.append(issue(inv.get('number'),'Destination state',seller_state,', '.join(sorted(known)),'Supplier state differs from the selected company state.'))
            problems[start:]=[link_source(p,entry) for p in problems[start:]]
    token=digest({'entries':entries,'issues':problems,'destination':facts,'company':company})
    if problems and (any(cannot_override(p) for p in problems) or not approvals or any(a!=token for a in approvals)):
        raise WorkflowReviewRequired(problems,token,company)


def acknowledge(plan,review,folder):
    if any(cannot_override(p) for p in review.issues):raise ValueError('Changed or unverified inputs must be corrected; acknowledgement cannot bypass them.')
    from datetime import datetime,timezone
    path=Path(folder)/'Workflow_Review_Decisions.json'
    old=read_json(path) if path.exists() else {'decisions':[]}
    old['decisions'].append({'company':review.company,'token':review.token,'issues':review.issues,'at':datetime.now(timezone.utc).isoformat(),'action':'Proceed with printed invoice details'})
    write_json(path,old)
    output=[]
    for name,data in plan:
        if name=='Sales_Vouchers.xml':
            doc=ET.fromstring(data);meta=json.loads(doc.get(MARKER));meta['acknowledgement']=review.token
            doc.set(MARKER,json.dumps(meta,ensure_ascii=False));data=ET.tostring(doc,encoding='utf-8',xml_declaration=True)
        output.append((name,data))
    return output


def selected_invoice_plan(plan,record):
    """Unticking the full batch imports this invoice, not unprocessed neighbours."""
    sales=next(ET.fromstring(data) for name,data in plan if name=='Sales_Vouchers.xml')
    if not sales.get(MARKER):return plan
    entries=json.loads(sales.get(MARKER))['entries'];number=(record.get('invoice') or {}).get('number')
    selected=[e for e in entries if e['read_sha256']==record.get('digest') and (not number or e['invoice'].get('number')==number)]
    if len(selected)!=1:raise ValueError('Selected invoice changed or is ambiguous; refresh/re-process before import.')
    wanted=selected[0]['guid'];vouchers=[v for v in sales.findall('.//VOUCHER') if v.findtext('GUID')==wanted]
    if len(vouchers)!=1:raise ValueError('Selected invoice is missing from this seller XML set.')
    ledgers={n.text for n in vouchers[0].iter('LEDGERNAME')};stocks={n.text for n in vouchers[0].iter('STOCKITEMNAME')}
    docs={name:ET.fromstring(data) for name,data in plan}
    units={n.findtext('BASEUNITS') for n in docs['Masters.xml'].iter('STOCKITEM') if n.get('NAME') in stocks}
    result=[]
    for name,data in plan:
        doc=docs[name];container=doc.find('.//REQUESTDATA')
        if name=='Sales_Vouchers.xml':container[:]=[msg for msg in container if msg.findtext('VOUCHER/GUID')==wanted]
        elif name=='Masters.xml':container[:]=[msg for msg in container if any(n.tag=='LEDGER' and n.get('NAME') in ledgers or n.tag=='STOCKITEM' and n.get('NAME') in stocks for n in msg)]
        elif name=='Units.xml':
            from .tally_units import unit_symbol
            container[:]=[msg for msg in container if unit_symbol(msg.find('UNIT')) in units]
        result.append((name,ET.tostring(doc,encoding='utf-8',xml_declaration=True)))
    return result

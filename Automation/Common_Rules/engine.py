"""Client discovery, isolation, incremental processing and review reports."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from .accounting import accounting_entries, cents, fingerprint, gstin_valid, invoice_key, state_code, validate, sales_ledger, export_notice
from .demo import prepare_demo_invoice, test_gstin
from .extraction import parse_text, text_from_pdf
from .history import History
from .masters import plan_masters, required_masters, identity
from .templates import TemplateError, check_spec, registry, write_workbook
from .tally_xml import masters_document, sales_document, save_document, verify_references

DEFAULT_LEDGERS = {'taxable':'Sales','exempt':'Exempt Sales','nil_rated':'Nil Rated Sales','non_gst':'Non GST Sales',
                   'cgst':'Output CGST','sgst':'Output SGST','igst':'Output IGST','round_off':'Round Off'}
INBOX = 'Sales Invoices (PDF)'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    temp.replace(path)


def init_client(root, name, company, seller_gstin, mode='new', demo_profile=None):
    if Path(name).name != name or name.startswith('.') or name in ('Common_Rules','tests'):
        raise ValueError('Client name must be a single non-reserved folder name')
    if not company.strip() or not gstin_valid(seller_gstin.upper()):
        raise ValueError('Supply a company name and a valid seller GSTIN (including checksum). '
                         'SELLER_GSTIN and NOT ASSIGNED are placeholders. To check PDFs before '
                         'setup, run: python main.py inspect-invoices "' + name + '"')
    client = root / name
    if client.is_symlink():
        raise ValueError('Client folder must not be a symbolic link')
    if (client / 'client.json').exists():
        raise ValueError('Client already configured; refusing to overwrite it')
    config = {'company_id':str(uuid.uuid4()),'company_name':company,'seller_gstin':seller_gstin.upper(),
              'company_mode':mode,'ledgers':dict(DEFAULT_LEDGERS),'stock_group':'Primary',
              'output_format':'xml',
              'units':{'Nos':{'formal_name':'Numbers','uqc':'NOS','decimal_places':0}}}
    if demo_profile:
        config.update(demo_only=True, demo_profile=demo_profile,
                      warning='DEMO ONLY: synthetic GSTINs and assumed fields. Use a disposable Tally test company. Never use for filing.')
    write_json(client / 'client.json', config)
    (client / INBOX).mkdir(exist_ok=True)
    (client / 'reviews').mkdir(exist_ok=True)
    return client


def init_demo_client(root, name, company, seller_state, unit):
    if unit != 'Nos':
        raise ValueError('This dummy profile currently supports the explicitly selected Nos unit only')
    code = state_code(seller_state)
    profile = {'version':1, 'seller_state':code, 'unit':unit}
    return init_client(root,name,company,test_gstin(code + 'DEMCO0000A1Z'),demo_profile=profile)


def discover(root):
    return sorted([p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and
                   not p.name.startswith('.') and ((p / INBOX).is_dir() or (p / 'client.json').is_file() or
                   any(f.is_file() and f.suffix.lower() == '.pdf' for f in p.iterdir()))], key=lambda p:p.name.casefold())


def invoice_paths(client):
    """Read PDFs directly inside a client, plus the supported optional inbox.

    Do not search reports, imports, reviews or arbitrary adjacent directories:
    they are not source-invoice locations.
    """
    paths = {p for p in client.iterdir() if p.is_file() and p.suffix.lower() == '.pdf'}
    inbox = client / INBOX
    if inbox.is_dir():
        paths.update(p for p in inbox.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf')
    return sorted(paths, key=str)


def inspect_invoices(client):
    """Extract and report without initializing a company or generating imports."""
    if not client.is_dir() or client.is_symlink():
        raise ValueError('Invoice folder must exist and must not be a symbolic link')
    records = []
    totals = []
    balanced = 0
    for path in invoice_paths(client):
        digest = None
        raw = {}
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(client.resolve()):
                raise ValueError('Invoice path escapes the client folder')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            raw = parse_text(text_from_pdf(path))
            _, issues = validate(raw, {'seller_gstin':raw.get('seller_gstin')})
            seller = str(raw.get('seller_gstin') or '').upper()
            buyer = str(raw.get('buyer_gstin') or '').upper()
            if not gstin_valid(seller):
                issues.append('Seller GSTIN is missing, unassigned or invalid')
            if buyer and not gstin_valid(buyer):
                issues.append('Invalid buyer GSTIN (format, state or checksum)')
            for index, item in enumerate(raw.get('items', []), 1):
                if not item.get('unit'):
                    issues.append(f'Item {index}: missing unit')
            for tax in ('cgst','sgst','igst'):
                if tax not in raw:
                    issues.append(f'Missing explicit {tax} amount (enter 0 if absent after review)')
            if not raw.get('buyer_state') and not buyer:
                issues.append('Buyer state required for master creation; place of supply is a separate field')
            try:
                total = cents(raw['total'])
                expected = cents(raw['taxable']) + sum(cents(raw.get(tax, 0)) for tax in ('cgst','sgst','igst')) + cents(raw.get('round_off',0))
                # This check only reconciles displayed totals, not import readiness.
                if expected == total:
                    balanced += 1
                else:
                    issues.append('Printed invoice totals do not balance')
                totals.append(total)
            except (ValueError, ArithmeticError, KeyError, TypeError):
                issues.append('Printed totals could not be reconciled')
        except Exception as exc:
            issues = [f'PDF extraction failed: {exc}']
        records.append({'source':str(path.relative_to(client)), 'source_sha256':digest,
                        'invoice':raw, 'issues':list(dict.fromkeys(issues))})
    report = client / 'reports' / 'inspection.json'
    summary = {'client':client.name,'pdf_count':len(records),
               'extracted_invoice_count':sum(bool(r['invoice'].get('number') and r['invoice'].get('items')) for r in records),
               'printed_totals_balanced':balanced,
               'invoice_total_sum':str(sum(totals)) if len(totals) == len(records) and records else None,
               'needs_review':sum(bool(r['issues']) for r in records),
               'xml_generated':False, 'report':str(report)}
    write_json(report, {'summary':summary, 'invoices':records})
    return summary


@contextmanager
def client_lock(client):
    # Atomic mkdir works on both Windows and Linux. A crash leaves a visible lock;
    # only remove it after confirming no other process is using this client.
    lock = client / '.automation' / 'run.lock'
    lock.parent.mkdir(exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Client is locked by another run (or a prior crash); inspect .automation/run.lock')
    try:
        yield
    finally:
        lock.rmdir()


def load_config(client):
    path = client / 'client.json'
    if not path.is_file():
        raise ValueError('Missing client.json; run init-client for this folder')
    config = read_json(path)
    for field in ('company_id','company_name','seller_gstin','company_mode','units','ledgers'):
        if not config.get(field):
            raise ValueError(f'Client configuration requires {field}')
    if config['company_mode'] not in ('new','existing'):
        raise ValueError('company_mode must be new or existing')
    if config.get('output_format','xml') not in ('xml','excel'):
        raise ValueError('output_format must be xml or excel')
    if config.get('demo_only'):
        profile = config.get('demo_profile', {})
        if profile.get('version') == 2:
            source = config.get('source_seller_gstin','')
            expected_seller = test_gstin(source[:14])
            if source[:2] != profile.get('seller_state'):
                raise ValueError('Demo source seller state differs from its profile')
        else:
            expected_seller = test_gstin(profile.get('seller_state','') + 'DEMCO0000A1Z')
        if (profile.get('version') not in (1,2) or profile.get('unit') != 'Nos' or
                config['company_mode'] != 'new' or config.get('output_format','xml') != 'xml' or
                config['seller_gstin'] != expected_seller):
            raise ValueError('Invalid demo configuration; use a separate new XML test company')
    if not set(DEFAULT_LEDGERS).issubset(config['ledgers']):
        raise ValueError('Missing sales/tax ledger mapping')
    ledger_names = [v.casefold().strip() for v in config['ledgers'].values()]
    if any(not name for name in ledger_names) or len(set(ledger_names)) != len(ledger_names):
        raise ValueError('Sales and tax ledgers must have distinct nonempty names')
    return config


def load_snapshot(client, config):
    path = client / 'tally_snapshot.json'
    if not path.exists():
        if config['company_mode'] == 'existing':
            raise ValueError('Existing company requires a complete reliable tally_snapshot.json before generating vouchers')
        return {'masters':[], 'vouchers':[]}
    snapshot = read_json(path)
    if snapshot.get('company_id') != config['company_id'] or snapshot.get('seller_gstin') != config['seller_gstin']:
        raise ValueError('Tally snapshot belongs to a different client/company')
    if snapshot.get('complete') is not True or not snapshot.get('exported_at'):
        raise ValueError('Tally snapshot must identify its export date and be explicitly complete')
    stamp = datetime.fromisoformat(snapshot['exported_at'])
    if stamp.tzinfo is None:
        raise ValueError('Snapshot exported_at must include timezone')
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    if age < -300 or age > config.get('snapshot_max_age_hours', 24) * 3600:
        raise ValueError('Tally snapshot is stale or dated in the future; refresh it')
    # A full canonical invoice payload is required to compare conflicting details.
    for voucher in snapshot['vouchers']:
        if 'invoice' not in voucher:
            raise ValueError('Snapshot vouchers need full canonical invoice data, not invoice numbers alone')
        _, errors = validate(voucher['invoice'], config)
        if errors:
            raise ValueError('Invalid Tally snapshot invoice: ' + '; '.join(errors))
    return snapshot


def tally_vouchers(snapshot, config):
    result = {}
    for voucher in snapshot['vouchers']:
        inv, _ = validate(voucher['invoice'], config)
        key = invoice_key(inv)
        fp = fingerprint(inv)
        if key in result and result[key] != fp:
            raise ValueError('Conflicting vouchers in Tally snapshot')
        result[key] = fp
    return result


def invalidate_outputs(client, folder=None):
    folder = folder or client/'imports'
    manifest = folder/'manifest.json'
    if manifest.exists():
        old = read_json(manifest)
        old['valid_for_import'] = False
        old['reason'] = 'A new processing run has started; use only outputs with a current valid manifest'
        write_json(manifest, old)
        # Withdraw only files explicitly recorded as created by this engine.
        for filename in old.get('files', []):
            path = (folder / filename).resolve()
            if path.parent == folder.resolve() and path.is_file():
                path.unlink()


def review_record(client, path, digest, raw, errors):
    draft = client / 'reports' / 'review_drafts' / f'{digest}.json'
    write_json(draft, {'source_sha256':digest,'source':path.name,'approved':False,'invoice':raw,'errors':errors})


def export_imports(root, client, config, invoices, masters, history, output_folder=None, source_client=None):
    if config.get('output_format','xml') == 'xml':
        return export_xml_imports(client,config,invoices,masters,history,output_folder,source_client)
    return export_excel_imports(root,client,config,invoices,masters,history,output_folder,source_client)


def export_xml_imports(client, config, invoices, masters, history, output_folder=None, source_client=None):
    verify_references(config,invoices,load_snapshot(client,config)['masters'] + history.confirmed_masters() + masters)
    folder = output_folder or client/'imports'
    staging = client / '.automation' / 'export-staging'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    files = []
    try:
        if masters:
            save_document(masters_document(config,masters,invoices),staging / 'Masters.xml')
            files.append('Masters.xml')
        save_document(sales_document(config,invoices),staging / 'Sales_Vouchers.xml')
        files.append('Sales_Vouchers.xml')
        import_order=list(files)
        required={identity(master):master for inv in invoices.values() for master in required_masters(inv,config)}
        save_document(masters_document(config,list(required.values()),invoices),staging / 'Required_Masters.xml')
        files.append('Required_Masters.xml')
        write_json(staging / 'manifest.json', {'valid_for_import':True,'output_format':'xml',
             'demo_only':bool(config.get('demo_only')),
             'source_client':source_client,
             'export_scope':folder.relative_to(client/'imports').as_posix() if folder != client/'imports' else None,
             'company_id':config['company_id'],'company_name':config['company_name'],
             'generated_at':datetime.now(timezone.utc).isoformat(),'invoice_keys':list(invoices),
             'masters':masters,'files':files,'import_order':import_order,
             'recovery_master_file':'Required_Masters.xml',
             'file_sha256':{name:hashlib.sha256((staging / name).read_bytes()).hexdigest() for name in files},
             'order':['unit','stock_group','ledger','stock_item','sales'],
             'accounting_only_exports':[{'invoice_key':key,'number':inv['number'],
                 'buyer_country':inv['buyer_country'],'export_mode':inv['export_mode'],
                 'shipping_bill_port':inv.get('shipping_bill_port'),
                 'foreign_currency':inv.get('foreign_currency'),
                 'exchange_rate':inv.get('exchange_rate'),
                 'foreign_invoice_value':inv.get('foreign_invoice_value'),
                 'notice':export_notice(config)}
                 for key,inv in invoices.items() if inv.get('accounting_only_export')],
             'gst_return_mapping_verified':False,
             'warning':('DEMO ONLY: synthetic GSTINs and assumed fields; never use for filing. ' if config.get('demo_only') else '') + 'Import Masters.xml successfully before Sales_Vouchers.xml. Generation is not import confirmation. Verify GST in a dummy Tally company first.'})
        folder.mkdir(parents=True,exist_ok=True)
        for file in staging.iterdir():
            if file.name != 'manifest.json':
                file.replace(folder / file.name)
        (staging / 'manifest.json').replace(folder / 'manifest.json')
        for key in invoices:
            history.set_status(key,'generated')
    finally:
        shutil.rmtree(staging)


def export_excel_imports(root, client, config, invoices, masters, history, output_folder=None, source_client=None):
    templates = root / 'Common_Rules' / 'templates'
    specs = registry(templates)
    kinds = {m['kind'] for m in masters} | {'sales'}
    for kind in kinds:
        if kind not in specs:
            raise TemplateError(f'Official template mapping missing for {kind}')
        check_spec(templates, specs[kind])
    streams = {'invoices':[], 'inventory':[], 'accounting':[], 'rows':[]}
    for key, inv in invoices.items():
        base = {**inv, 'invoice_key':key,'company_name':config['company_name'], 'voucher_type':'Sales','sales_ledger':sales_ledger(inv, config)}
        streams['invoices'].append(base)
        for index, item in enumerate(inv['items'], 1):
            row = {**base,'item':item,'line_number':index,'row_type':'inventory'}
            streams['inventory'].append(row)
            streams['rows'].append(row)
        for index, allocation in enumerate(accounting_entries(inv, config), 1):
            row = {**base,'allocation':allocation,'line_number':index,'row_type':'ledger'}
            streams['accounting'].append(row)
            streams['rows'].append(row)
    folder = output_folder or client/'imports'
    staging = client / '.automation' / 'export-staging'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    files = []
    try:
        for kind in ('unit','stock_group','ledger','stock_item','sales'):
            records = [m for m in masters if m['kind'] == kind]
            if kind != 'sales' and not records:
                continue
            filename = 'Sales_Output.xlsx' if kind == 'sales' else f'Masters_{kind}.xlsx'
            mapping = write_workbook(templates, specs[kind], staging / filename, streams if kind == 'sales' else {'masters':records})
            files.append(filename)
            mapping_name = f'{kind}_{mapping.name}'
            shutil.copy2(mapping, staging / mapping_name)
            files.append(mapping_name)
        write_json(staging / 'manifest.json', {'valid_for_import':True, 'company_id':config['company_id'],
             'source_client':source_client,
             'export_scope':folder.relative_to(client/'imports').as_posix() if folder != client/'imports' else None,
             'company_name':config['company_name'], 'generated_at':datetime.now(timezone.utc).isoformat(),
             'invoice_keys':list(invoices),'masters':masters,'files':files,
             'order':['unit','stock_group','ledger','stock_item','sales'],
             'warning':'Import masters successfully before sales. Generation is not import confirmation.'})
        folder.mkdir(parents=True,exist_ok=True)
        for file in staging.iterdir():
            if file.name != 'manifest.json':
                file.replace(folder / file.name)
        (staging / 'manifest.json').replace(folder / 'manifest.json')
        for key in invoices:
            history.set_status(key, 'generated')
    finally:
        shutil.rmtree(staging)


def process_client(root, client, export_scopes=None):
    with client_lock(client):
        return _process_client(root, client, export_scopes)


def _process_client(root, client, export_scopes=None):
    invalidate_outputs(client)
    for scope in (export_scopes or {}).values():
        invalidate_outputs(client,scope['output_folder'])
    config = load_config(client)
    if config.get('demo_only') and not config.get('source_seller_gstin'):
        # Legacy dummy folders may contain several fictional sellers. A single
        # configured demo seller must never hide that distinction.
        paired_sellers = set()
        for path in invoice_paths(client):
            if path.is_symlink() or not path.resolve().is_relative_to(client.resolve()):
                continue  # The normal source check reports this below.
            try:
                parsed = parse_text(text_from_pdf(path))
            except Exception:
                continue  # The per-document review path reports unreadable PDFs.
            if parsed.get('source_layout') in ('paired_columns_v1','section_panels_v1','tabular_roles_v1','receipt_items_v1','ordered_roles_v1','flexible_roles_v1'):
                paired_sellers.add(parsed.get('seller_gstin'))
        if len(paired_sellers) > 1:
            raise ValueError('Multiple sellers in this folder; use Open_Invoice_App.bat to create separate seller companies without changing existing history')
    snapshot = load_snapshot(client, config)
    tally = tally_vouchers(snapshot, config)
    history = History(client / '.automation' / 'history.sqlite3')
    issues = []
    counts = {'new':0,'duplicate':0,'review':0,'already_in_tally':0}
    try:
        history.bind_company(config['company_id'], config['seller_gstin'])
        # Also reconcile pending/generated records after a Tally snapshot refresh.
        for key, inv in history.active().items():
            if key in tally:
                if fingerprint(inv) == tally[key]:
                    history.set_status(key, 'imported')
                    history.event(inv['source'], key, 'imported', 'Confirmed in complete Tally snapshot')
                else:
                    issues.append({'source':inv['source'],'invoice_key':key,'status':'review','errors':['Stored invoice conflicts with existing Tally voucher']})
        paths = invoice_paths(client)
        for path in paths:
            raw = {}
            digest = None
            key = None
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(client.resolve()):
                    raise ValueError('Invoice path escapes the client folder')
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                override = client / 'reviews' / f'{digest}.json'
                if override.exists():
                    review = read_json(override)
                    if review.get('source_sha256') != digest or review.get('approved') is not True:
                        raise ValueError('Review must be approved and bound to this exact PDF digest')
                    raw = review['invoice']
                else:
                    text = text_from_pdf(path)
                    text_file = client / '.automation' / 'extracted_text' / f'{digest}.txt'
                    text_file.parent.mkdir(exist_ok=True)
                    text_file.write_text(text, encoding='utf-8')
                    raw = parse_text(text)
                if config.get('demo_only'):
                    raw = prepare_demo_invoice(raw,config)
                raw = {**raw, 'sha256':digest, 'source':str(path.relative_to(client))}
                inv, errors = validate(raw, config)
                if errors:
                    try:
                        key = invoice_key(inv)
                    except (ValueError, KeyError, TypeError):
                        pass
                    review_record(client, path, digest, raw, errors)
                    raise ValueError('; '.join(errors))
                key = invoice_key(inv)
                fp = fingerprint(inv)
                previous = history.lookup(key)
                if previous:
                    if previous['fingerprint'] != fp:
                        if key in tally or not history.correct_units(key,inv):
                            raise ValueError('Invoice identity matches history but transaction details differ')
                        for manifest_path in (client/'imports'/'by_client').glob('*/manifest.json'):
                            manifest=read_json(manifest_path)
                            if key in manifest.get('invoice_keys',[]):invalidate_outputs(client,manifest_path.parent)
                    counts['duplicate'] += 1
                    history.event(path.name,key,'duplicate','No second voucher created')
                    continue
                if key in tally:
                    if tally[key] != fp:
                        raise ValueError('Invoice identity matches Tally but transaction details differ')
                    history.save(key,fp,inv,'imported')
                    history.event(path.name,key,'imported','Confirmed in complete Tally snapshot')
                    counts['already_in_tally'] += 1
                    continue
                history.save(key,fp,inv,'pending')
                history.event(path.name,key,'pending','Validated; not imported')
                counts['new'] += 1
            except (ValueError, OSError, KeyError, TypeError) as exc:
                counts['review'] += 1
                message = str(exc)
                issues.append({'source':str(path.relative_to(client)),'invoice_key':key,'status':'review','errors':[message]})
                history.event(path.name,None,'pending_review',message)
                if digest:
                    review_record(client, path, digest, raw, [message])
            except Exception as exc:
                # A corrupt PDF is contained to this document. Unexpected errors
                # stay visible rather than masquerading as successful extraction.
                counts['review'] += 1
                issues.append({'source':path.name,'status':'review','errors':[f'{type(exc).__name__}: {exc}']})
                history.event(path.name,None,'pending_review',f'{type(exc).__name__}: {exc}')
        active = history.active()
        for key, inv in list(active.items()):
            _, errors = validate(inv, config)
            if errors:
                issues.append({'invoice_key':key,'status':'review','errors':errors})
        for issue in issues:
            key = issue.get('invoice_key')
            if key:
                active.pop(key, None)
        masters, master_errors = plan_masters(active, config, snapshot['masters'] + history.confirmed_masters())
        for key, errors in master_errors.items():
            issues.append({'invoice_key':key,'status':'review','errors':errors})
        eligible = {k:v for k,v in active.items() if k not in master_errors}
        export_status = 'No pending invoices'
        scope_reports = {}
        if export_scopes is None and eligible:
            try:
                export_imports(root,client,config,eligible,masters,history)
                export_status = f'Generated {len(eligible)} sales vouchers; import not confirmed'
            except (TemplateError, ValueError, KeyError, OSError) as exc:
                export_status = f'BLOCKED: {exc}'
                issues.append({'status':'export_blocked','errors':[str(exc)]})
        elif export_scopes is not None:
            available_masters=snapshot['masters']+history.confirmed_masters()
            for source_client,scope in export_scopes.items():
                chosen={key:inv for key,inv in eligible.items() if key in scope['invoice_keys']}
                selected_masters,selected_errors=plan_masters(chosen,config,available_masters)
                selected={key:inv for key,inv in chosen.items() if key not in selected_errors}
                scope_issues=[{'invoice_key':key,'status':'review','errors':errors}
                    for key,errors in {**master_errors,**selected_errors}.items() if key in scope['invoice_keys']]
                status='No pending invoices'
                if selected:
                    try:
                        export_imports(root,client,config,selected,selected_masters,history,scope['output_folder'],source_client)
                        status=f'Generated {len(selected)} sales vouchers for {source_client}; import not confirmed'
                    except (TemplateError,ValueError,KeyError,OSError) as exc:
                        status=f'BLOCKED: {exc}'
                        scope_issues.append({'status':'export_blocked','errors':[str(exc)]})
                scope_reports[source_client]={'export':status,'pending_validated':len(selected),
                    'issues':scope_issues,'output_path':str(scope['output_folder'])}
            # Keep the old output location only when it contains exactly this
            # single source folder's batch. Never retain a mixed company XML.
            if len(export_scopes)==1:
                source_client,scope=next(iter(export_scopes.items()))
                report=scope_reports[source_client]
                if eligible and set(eligible).issubset(scope['invoice_keys']) and not report['issues'] and report['pending_validated']:
                    mirror=client/'imports';mirror.mkdir(exist_ok=True)
                    manifest=read_json(scope['output_folder']/'manifest.json')
                    for filename in manifest['files']:
                        shutil.copy2(scope['output_folder']/filename,mirror/filename)
                    write_json(mirror/'manifest.json',{**manifest,'export_scope':None})
        report = {'scopes':scope_reports,'client':client.name,'company_id':config['company_id'],'output_format':config.get('output_format','xml'),'counts':counts,
                  'demo_only':bool(config.get('demo_only')),
                  'pending_validated':len(eligible),'export':export_status,'issues':issues,'history':history.statuses()}
        write_json(client / 'reports' / 'validation.json', report)
        write_json(client / 'reports' / 'master_plan.json', masters)
        write_json(client / 'reports' / 'validated_invoices.json', [
            {'invoice_key':key,'invoice':inv,'accounting':accounting_entries(inv,config)} for key,inv in eligible.items()])
        if config.get('demo_only'):
            write_json(client / 'reports' / 'demo_adjustments.json', {
                'demo_only':True,'warning':config['warning'],
                'invoices':[{'source':inv['source'],'source_sha256':inv['sha256'],
                             'printed_invoice':inv['demo_source_invoice'],
                             'adjustments':inv['demo_adjustments']} for inv in eligible.values()]})
        return report
    finally:
        history.close()


def run(root):
    clients = discover(root)
    if not clients:
        return {'message':'No client folders found','clients':[]}
    reports = []
    configurations = {}
    identity_counts = {}
    for client in clients:
        try:
            config = load_config(client)
            configurations[client] = config
            identity_counts[config['company_id']] = identity_counts.get(config['company_id'], 0) + 1
        except (ValueError, OSError, KeyError, TypeError) as exc:
            configurations[client] = exc
    for client in clients:
        try:
            config = configurations[client]
            if isinstance(config, Exception):
                raise config
            if identity_counts[config['company_id']] > 1:
                raise ValueError('Two client folders share company_id; copied histories must not create duplicate companies')
            reports.append(process_client(root,client))
        except Exception as exc:
            try:
                with client_lock(client):
                    invalidate_outputs(client)
            except (ValueError, OSError):
                pass  # Never interfere with an independently running process.
            reports.append({'client':client.name,'error':f'{type(exc).__name__}: {exc}'})
    return {'clients':reports}


def confirm_import(client, result_path):
    with client_lock(client):
        config = load_config(client)
        result = read_json(result_path)
        export_scope=result.get('export_scope')
        folder=client/'imports'
        if export_scope is not None:
            if not isinstance(export_scope,str) or Path(export_scope).is_absolute() or '..' in Path(export_scope).parts or '\\' in export_scope:
                raise ValueError('Invalid export scope')
            folder=folder/export_scope
            if folder.is_symlink() or not folder.resolve().is_relative_to((client/'imports').resolve()):
                raise ValueError('Export scope escapes the company imports folder')
        manifest_path=folder/'manifest.json'
        manifest = read_json(manifest_path)
        if manifest.get('export_scope') != export_scope:
            raise ValueError('Import results must match the generated export scope')
        if result.get('company_id') != config['company_id'] or manifest.get('company_id') != config['company_id']:
            raise ValueError('Import results must match this client company_id')
        if manifest.get('company_name') != config['company_name']:
            raise ValueError('Company name changed after this export; regenerate for the correct Tally company')
        if not manifest.get('valid_for_import') or result.get('generated_at') != manifest['generated_at']:
            raise ValueError('Import results must reference the current valid export generated_at')
        if not result.get('tally_result_reference'):
            raise ValueError('Supply the Tally result/log reference; workbook generation alone is not import confirmation')
        history = History(client / '.automation' / 'history.sqlite3')
        try:
            history.bind_company(config['company_id'], config['seller_gstin'])
            planned = {identity(m):m for m in manifest['masters']}
            confirmations = []
            for master in result.get('masters', []):
                details = master['master']
                if planned.get(identity(details)) != details:
                    raise ValueError('Master result does not match the generated master plan')
                if master['status'] not in ('imported','rejected','pending'):
                    raise ValueError('Unknown master import status')
                if master['status'] == 'imported':
                    confirmations.append(details)
            known = {identity(m):m for m in history.confirmed_masters() + confirmations + load_snapshot(client,config)['masters']}
            updates = []
            for entry in result.get('vouchers', []):
                key = entry['invoice_key']
                previous = history.lookup(key)
                if key not in manifest['invoice_keys'] or not previous or previous['status'] not in ('generated','imported','rejected','pending'):
                    raise ValueError('Voucher result does not refer to a generated invoice')
                if entry['status'] not in ('imported','rejected','pending'):
                    raise ValueError('Unknown voucher import status')
                if previous['status'] == 'imported' and entry['status'] != 'imported':
                    raise ValueError('An imported voucher cannot be downgraded')
                if entry['status'] == 'imported':
                    for required in required_masters(previous['data'],config):
                        existing = known.get(identity(required))
                        if not existing or any(existing.get(k) != v for k,v in required.items() if k not in ('kind','name')):
                            raise ValueError('Cannot confirm sales import before all matching dependent masters are confirmed')
                updates.append(entry)
            # Validate the whole result before mutating confirmation state.
            history.apply_import_result(result)
            manifest['valid_for_import'] = False
            manifest['reason'] = 'Import results recorded; run again to generate only remaining pending vouchers'
            write_json(manifest_path, manifest)
            # Copies/other source folders can refer to the same company invoice.
            # Retire those exports too, so confirmation cannot leave a second
            # valid import batch containing an already handled voucher.
            handled={entry['invoice_key'] for entry in result.get('vouchers',[])}
            candidates=[client/'imports'/'manifest.json']+list((client/'imports'/'by_client').glob('*/manifest.json'))
            for other in candidates:
                if other==manifest_path or not other.exists():
                    continue
                saved=read_json(other)
                if saved.get('company_id')==config['company_id'] and handled.intersection(saved.get('invoice_keys',[])):
                    invalidate_outputs(client,other.parent)
            return history.statuses()
        finally:
            history.close()

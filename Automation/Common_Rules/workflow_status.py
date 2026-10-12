"""Show the actual outstanding action without labelling successful reads failures."""
from collections import Counter


def invoice_status(record):
    errors=record.get('errors',[])
    if not errors:
        status=record.get('display_status',record.get('export','Invoice read'))
        if any(item.get('unit_auto') for item in record.get('invoice',{}).get('items',[])) and status!='Already confirmed imported':
            status+='; estimated unit'
        return status
    joined='; '.join(errors).casefold()
    if 'confirm test pdf' in joined:
        return 'Confirm test PDF' if record.get('demo_mode') or record.get('invoice',{}).get('test_document') else 'Choose invoice mode'
    if 'explicitly fictional; use dummy mode' in joined:return 'Use test-invoice mode'
    if 'ocr-derived' in joined or 'scanned pdf' in joined:return 'Verify scanned invoice'
    if all('unit' in error.casefold() and any(word in error.casefold() for word in ('choose','missing','mapping')) for error in errors):
        return 'Choose quantity unit'
    if 'exempt / nil-rated' in joined or 'uncertain gst classification' in joined:return 'Choose GST treatment'
    if not record.get('invoice',{}).get('seller_name') and any(word in joined for word in ('seller name','seller_name','seller gstin','seller_gstin')):
        return 'Check seller details'
    if 'transaction details differ' in joined or 'differs from existing tally' in joined:return 'Invoice differs from saved entry'
    if 'gstin' in joined:return 'Check GSTIN'
    if any(word in joined for word in ('seller identity','seller banner','seller state','seller name')):return 'Check seller details'
    if any(word in joined for word in ('does not reconcile','does not equal','round off','amount','tax total')):return 'Check amounts / GST'
    if 'missing' in joined:return 'Complete missing fields'
    return 'Check invoice: '+errors[0][:70]


def scan_summary(records):
    pdfs=len({record.get('source_path',record['path']) for record in records})
    actions=Counter(invoice_status(record) for record in records if record.get('errors'))
    prepared=sum(not record.get('errors') and record.get('batch_voucher_count',0)>0 and record.get('display_status')!='Already confirmed imported' for record in records)
    confirmed=sum(record.get('display_status')=='Already confirmed imported' and not record.get('errors') for record in records)
    parts=[f'{pdfs} PDFs; {len(records)} invoices read',f'{prepared} XML prepared']
    estimated=sum(any(item.get('unit_auto') for item in r.get('invoice',{}).get('items',[])) for r in records)
    if estimated:parts.append(f'{estimated} with estimated units (editable)')
    if confirmed:parts.append(f'{confirmed} already imported')
    parts.extend(f'{count} {action.lower()}' for action,count in actions.items())
    return '; '.join(parts)+'. XML preparation does not import into Tally.'

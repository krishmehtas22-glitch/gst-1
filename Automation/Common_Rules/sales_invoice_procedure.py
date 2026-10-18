"""Explicit sales/RCM facts; never erase printed tax or infer RCM from zero GST."""
from decimal import Decimal, InvalidOperation


def reverse_charge(invoice):
    return str(invoice.get('reverse_charge') or '').strip().casefold() in ('yes','y','true','1')


def normalize_rcm(invoice):
    """Only absent supplier-payable tax is derived from a confirmed RCM declaration."""
    if not reverse_charge(invoice):return
    derived=[]
    for head in ('cgst','sgst','igst','cess'):
        if invoice.get(head) in (None,''):
            invoice[head]='0';derived.append(head)
    if derived:
        invoice['rcm_tax_basis']='Zero supplier-payable '+', '.join(derived)+' from explicit reverse-charge declaration; not printed amounts.'


def validate_rcm(invoice):
    """Conflicting RCM cannot silently become a forward-charge XML invoice."""
    if not reverse_charge(invoice):return
    if invoice.get('classification')!='taxable' or invoice.get('supply')=='EXPORT':
        raise ValueError('RCM sales require taxable domestic treatment; review reverse charge, classification and supply. Existing XML retained.')
    for head in ('cgst','sgst','igst','cess'):
        raw=invoice.get(head)
        if raw in (None,''):continue  # Explicit RCM supplies a zero payable amount.
        try:
            amount=Decimal(str(raw).replace(',',''))
            if not amount.is_finite() or amount!=0:raise ValueError()
        except (InvalidOperation,ValueError):
            raise ValueError('RCM conflicts with '+head.upper()+' amount '+str(raw)+'. Review the printed invoice; nonzero tax will not be erased. Existing XML retained.') from None
    try:
        values=[Decimal(str(invoice.get(k,'0')).replace(',','')) for k in ('taxable','total','round_off')]
        if any(not v.is_finite() for v in values) or values[1]!=values[0]+values[2]:raise ValueError()
    except (InvalidOperation,ValueError):
        raise ValueError('RCM total must equal taxable value plus round-off with zero supplier-payable GST. Correct the invoice totals in review. Existing XML retained.') from None


def check_document(invoice):
    kind=str(invoice.get('document_type') or '').strip().casefold().replace(' ','_')
    if kind and kind not in ('sales_invoice','tax_invoice','invoice'):
        raise ValueError('Document type '+kind+' is not a confirmed sales invoice. Review the source before generating Sales XML. Existing XML retained.')

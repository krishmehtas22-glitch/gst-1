"""Invoice-IGST reference and local manual review; no refund entitlement calculation."""
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
import hashlib,json,uuid
from Common_Rules.export_metadata import is_export,export_country

STATUSES=('Unreviewed','Eligibility reviewed','Claimed','Not eligible')
NOTICE=('The estimate is the IGST recorded on the invoice, not proof of tax payment, refund eligibility, an approved claim or government payment. '
        'LUT input-tax-credit refunds require purchase/ITC and return records and are not calculated here. Nothing is posted as refund receivable in Tally.')


def amount(value):
    if value is None or str(value).strip()=='':return None
    try:
        result=Decimal(str(value).replace(',','').strip())
        return result.quantize(Decimal('.01')) if result.is_finite() else None
    except (ValueError,InvalidOperation):return None


def summary(record):
    inv=record.get('invoice') or {}
    result={'export':False,'country':'','estimate':None,'status':'Not applicable','reason':'','display':'—'}
    if record.get('listing_only') or not is_export(inv):return result
    result.update(export=True,status='Review required')
    try:result['country']=export_country(inv)
    except ValueError as exc:result.update(reason=str(exc),display='Review country');return result
    if inv.get('classification')=='export_lut':
        result.update(status='LUT / ITC not calculated',display='LUT · ITC not calculated',reason='No export IGST refund is estimated for LUT. A possible ITC refund needs separate records.');return result
    if inv.get('classification')!='export_igst' or str(inv.get('supply') or 'EXPORT').strip().upper() not in ('EXPORT','EXPORT IGST','EXPORT_IGST'):
        result.update(reason='Confirm export with payment of IGST before using an estimate.',display='Review treatment');return result
    igst=amount(inv.get('igst'));cgst=amount(inv.get('cgst'));sgst=amount(inv.get('sgst'))
    taxable=amount(inv.get('taxable'));total=amount(inv.get('total'))
    if igst is None or igst<=0 or cgst is None or sgst is None or cgst!=0 or sgst!=0:
        result.update(reason='Positive IGST and explicit zero CGST/SGST must be verified on the export invoice.',display='Review GST');return result
    if taxable is None or total is None or taxable<0 or total<=0 or igst>total:
        result.update(reason='Verify invoice taxable value, total and IGST before using an estimate.',display='Review amounts');return result
    # Never use original foreign-currency amounts as an INR refund reference.
    if inv.get('foreign_currency') and (amount(inv.get('exchange_rate')) is None or amount(inv.get('exchange_rate'))<=0):
        result.update(reason='Verify the printed exchange rate and INR accounting amounts first.',display='Review currency');return result
    result.update(estimate=format(igst,'.2f'),status='Unverified',display=format(igst,',.2f')+' · unverified',reason=NOTICE)
    return result


def review_key(record):
    inv=record.get('invoice') or {}
    identity={'client':record.get('client'),'source':record.get('digest') or str(record.get('source_path') or record.get('path')),
              **{k:inv.get(k) for k in ('number','date','seller_gstin','buyer_country','classification','supply','taxable','total','igst','cgst','sgst','foreign_currency','exchange_rate')}}
    return hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def load_review(root,record):
    path=Path(root)/'.invoice_app'/'export_refund_reviews'/(review_key(record)+'.json')
    if not path.exists():return None
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('key')!=review_key(record) or data.get('status') not in STATUSES:raise ValueError('Invalid saved refund review.')
        if data.get('status')=='Claimed' and (amount(data.get('claim_amount')) is None or amount(data['claim_amount'])<=0):raise ValueError('Invalid saved claim amount.')
        return data
    except (ValueError,OSError,TypeError,AttributeError) as exc:raise ValueError('Saved refund review could not be read: '+str(exc)) from exc


def save_review(root,record,status,claim_amount='',reference='',notes=''):
    info=summary(record)
    if not info['export']:raise ValueError('Select an analysed export invoice.')
    if status not in STATUSES:raise ValueError('Choose a valid review status.')
    claim=amount(claim_amount)
    if str(claim_amount).strip() and (claim is None or claim<0):raise ValueError('Enter a nonnegative claim amount.')
    if status=='Claimed':
        if info['estimate'] is None:raise ValueError('Verify export IGST before recording this IGST-refund claim.')
        if claim is None or claim<=0 or claim>amount(info['estimate']):raise ValueError('Claim amount must be positive and no greater than the recorded export IGST.')
        if not str(reference).strip():raise ValueError('Enter the claim / shipping bill reference.')
    if status=='Eligibility reviewed' and not str(notes).strip():raise ValueError('Record the basis for the eligibility review in notes.')
    data={'schema_version':1,'key':review_key(record),'status':status,'invoice_igst_reference':info['estimate'],
          'claim_amount':format(claim,'.2f') if claim is not None else None,'reference':str(reference).strip(),
          'notes':str(notes).strip(),'updated_at':datetime.now(timezone.utc).isoformat(),'manual_review':True,'tally_posting':False}
    folder=Path(root)/'.invoice_app'/'export_refund_reviews';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(data['key']+'.json');temporary=folder/(data['key']+'.'+uuid.uuid4().hex+'.tmp')
    try:temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return data

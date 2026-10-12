"""Read printed export/exempt treatment before deciding the payable GST split."""
import re
from .accounting import EXPORT_COUNTRIES, EXPORT_MODES


def apply_printed_treatment(invoice,text,warnings):
    compact=' '.join(text.casefold().split())
    supply=' '.join(str(invoice.get('supply') or '').upper().replace('_',' ').split())
    simple=re.sub(r'[^A-Z0-9 ]',' ',supply);simple=' '.join(simple.split())
    classification=invoice.get('classification')
    lut=bool(re.search(r'\bexport\b.{0,100}\b(?:lut|letter of undertaking)\b.{0,100}\bwithout payment of (?:igst|integrated tax)\b',compact))
    igst=bool(re.search(r'\bexport\b.{0,100}\bwith payment of (?:igst|integrated tax)\b',compact))
    if simple in ('EXPORT LUT','EXPORT UNDER LUT','EXPORT WITHOUT PAYMENT OF IGST') or classification=='export_lut':lut=True
    if simple in ('EXPORT IGST','EXPORT WITH IGST','EXPORT WITH PAYMENT OF IGST') or classification=='export_igst':igst=True
    if lut and igst:
        warnings.append('Conflicting export payment declarations: both LUT and payment of IGST')
        return
    if simple.startswith('EXPORT') or lut or igst:
        invoice['supply']='EXPORT'
        treatment='export_lut' if lut else 'export_igst' if igst else None
        if treatment:
            if classification not in (None,'','export','taxable',treatment):
                warnings.append('Printed export treatment conflicts with GST classification')
            invoice['classification']=treatment
            mode=EXPORT_MODES[treatment]
            if invoice.get('export_mode') not in (None,'',mode):warnings.append('Printed export payment mode conflicts with export declaration')
            else:invoice['export_mode']=mode
        foreign_pos=str(invoice.get('place_of_supply') or '').strip()
        lower=foreign_pos.casefold()
        foreign=lower in ('outside india','foreign country','overseas','96','96 - foreign country','outside india (96)')
        tail=re.sub(r'\s*\((?:na|n/a|96)\)\s*$','',foreign_pos,flags=re.I).rsplit(',',1)[-1].strip()
        country=EXPORT_COUNTRIES.get(tail.casefold())
        if country:invoice.setdefault('buyer_country',country);foreign=True
        if foreign:invoice['place_of_supply']='Outside India'
        gst=str(invoice.get('buyer_gstin') or '').casefold().strip()
        if gst in ('unregistered','unregistered (foreign entity)','n/a','na','n/a - overseas buyer',
                   'not applicable - overseas buyer','not applicable (export)','not applicable','none','-'):
            invoice['buyer_gstin']='';invoice['buyer_registration']='Unregistered'
        state=str(invoice.get('buyer_state') or '').strip()
        if state.casefold() in ('n/a','na','outside india','foreign country','overseas') or state.casefold() in EXPORT_COUNTRIES:
            invoice['buyer_state']='Outside India'
            if state.casefold() in EXPORT_COUNTRIES:invoice.setdefault('buyer_country',EXPORT_COUNTRIES[state.casefold()])
        if not invoice.get('buyer_country'):
            # Country must be printed, not inferred from an overseas buyer's name.
            for line in text.splitlines():
                match=re.search(r'\b(?:buyer country|country of destination|destination country|country)\s*:\s*(.+)',line,re.I)
                if match:invoice['buyer_country']=re.split(r'\s{2,}|\s*\|\s*',match[1])[0].strip();break
            if not invoice.get('buyer_country'):
                for line in text.splitlines():
                    columns=re.split(r'\s{2,}',line.strip())
                    if len(columns)!=2:continue
                    candidate=columns[1].rsplit(',',1)[-1].strip()
                    country=EXPORT_COUNTRIES.get(candidate.casefold())
                    if country:invoice['buyer_country']=country;break
        return
    explicit_exempt=classification=='exempt' or simple=='EXEMPT' or bool(re.search(r'\bexempt supply\s*:\s*(?:no gst|gst exempt)|\bgst exempt\b',compact))
    explicit_nil=classification=='nil_rated' or simple in ('NIL','NIL RATED','NIL RATED SUPPLY')
    if explicit_exempt and explicit_nil:
        warnings.append('Conflicting exempt and nil-rated classifications');return
    if explicit_exempt or explicit_nil:
        treatment='exempt' if explicit_exempt else 'nil_rated'
        if classification not in (None,'','taxable','exempt','nil_rated',treatment):warnings.append('Printed exemption conflicts with GST classification')
        invoice['supply']='EXEMPT';invoice['classification']=treatment
    elif simple in ('INTRA STATE','INTRASTATE','INTRA'):
        invoice['supply']='INTRA'
    elif simple in ('INTER STATE','INTERSTATE','INTER'):
        invoice['supply']='INTER'

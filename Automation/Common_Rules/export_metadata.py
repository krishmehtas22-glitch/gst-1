"""Export country metadata only; never calculate tax or refund entitlement."""
from .accounting import EXPORT_COUNTRIES, state_code


def is_export(invoice):
    return invoice.get('classification') in ('export_lut','export_igst') or str(invoice.get('supply') or '').strip().upper().startswith('EXPORT')


def export_country(invoice):
    if not is_export(invoice):return None
    raw=str(invoice.get('buyer_country') or '').strip()
    country=EXPORT_COUNTRIES.get(raw.casefold())
    if not country or country=='India':
        raise ValueError('Export country required for invoice '+str(invoice.get('number') or '(number missing)')+'. Open Review and enter the printed foreign buyer/destination country; existing XML is retained.')
    pos=str(invoice.get('place_of_supply') or '').strip()
    try:state_code(pos);indian_pos=True
    except ValueError:indian_pos=pos.casefold()=='india'
    if indian_pos:
        raise ValueError('Export place of supply conflicts with the foreign country for invoice '+str(invoice.get('number') or '(number missing)')+'. Review before generating XML; existing XML is retained.')
    return country


def party_country_fields(invoice):
    country=export_country(invoice)
    return {'COUNTRYNAME':country,'LEDSTATENAME':'Not Applicable'} if country else {}


def voucher_country_fields(invoice):
    country=export_country(invoice)
    return {'COUNTRYOFRESIDENCE':country,'STATENAME':'Not Applicable','PLACEOFSUPPLY':'Outside India'} if country else {}

"""Validate exact Tally quantity precision, never round or scale quantities."""
from decimal import Decimal,InvalidOperation

MAX_DECIMALS=6


def decimal_places(value):
    try:quantity=Decimal(str(value).replace(',','').strip())
    except (ValueError,InvalidOperation):raise ValueError('Quantity is not a valid number.') from None
    if not quantity.is_finite():raise ValueError('Quantity must be finite.')
    # Work from the tuple, without Decimal.normalize's context rounding.
    digits=list(quantity.as_tuple().digits);exponent=quantity.as_tuple().exponent
    if not any(digits):return 0
    while digits and digits[-1]==0:digits.pop();exponent+=1
    return max(0,-exponent)


def validate_records(records):
    for record in records:
        for index,item in enumerate((record.get('invoice') or {}).get('items',[]),1):
            if item.get('quantity') in (None,''):continue  # Existing missing-item review remains intact.
            try:required=decimal_places(item['quantity'])
            except ValueError:continue  # Existing invalid-item fallback remains intact.
            if required>MAX_DECIMALS:
                raise ValueError('Invoice '+str(record['invoice'].get('number') or record.get('path'))+
                    ', item '+str(index)+': quantity '+str(item['quantity'])+' '+str(item.get('unit') or '')+
                    ' requires '+str(required)+' decimal places; Tally units support at most 6. '
                    'Quantity was not rounded; previous XML retained. Review the source quantity/unit.')


def validate_existing_units(vouchers,catalog):
    existing={entry['name'].strip().casefold():entry for entry in catalog.values() if entry['kind']=='units'}
    required={}
    for node in vouchers.iter():
        if node.tag not in ('ACTUALQTY','BILLEDQTY') or not node.text:continue
        value,symbol=node.text.split(' ',1)
        key=symbol.strip().casefold()
        required[key]=max(required.get(key,0),decimal_places(value))
    for key,precision in required.items():
        if key not in existing:continue
        entry=existing[key]
        try:available=int(entry['decimals'])
        except (ValueError,TypeError):available=-1
        if available<precision:
            raise ValueError('Existing Tally unit '+entry['name']+' needs '+str(precision)+
                ' decimal places for this batch (currently '+str(entry['decimals'])+'). '
                'Increase its Number of decimal places in Tally, then read Tally masters again. '
                'Quantities were not rounded; previous XML retained.')

"""Source-preserving INR projection. Never fetch market rates or invoke AI."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from difflib import get_close_matches
from pathlib import Path
import hashlib, json, re, unicodedata, uuid

# ISO 4217 codes; names/symbols are deliberately conservative where ambiguous.
CODES=set('AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XOF XPF YER ZAR ZMW ZWG'.split())
ALIASES={
    'indian rupee':'INR','indian rupees':'INR','rupees':'INR','rs':'INR','₹':'INR',
    'us dollar':'USD','us dollars':'USD','united states dollar':'USD','us$':'USD','u.s. dollar':'USD',
    'euro':'EUR','euros':'EUR','€':'EUR','pound sterling':'GBP','british pound':'GBP','british pounds':'GBP','£':'GBP',
    'uae dirham':'AED','uae dirhams':'AED','dirham':'AED','dirhams':'AED','د.إ':'AED',
    'japanese yen':'JPY','chinese yuan':'CNY','renminbi':'CNY','rmb':'CNY',
    'australian dollar':'AUD','australian dollars':'AUD','a$':'AUD',
    'canadian dollar':'CAD','canadian dollars':'CAD','c$':'CAD',
    'singapore dollar':'SGD','singapore dollars':'SGD','s$':'SGD',
    'new zealand dollar':'NZD','nz$':'NZD','swiss franc':'CHF','swiss francs':'CHF',
    'saudi riyal':'SAR','qatari riyal':'QAR','kuwaiti dinar':'KWD','bahraini dinar':'BHD',
    'oman rial':'OMR','omani rial':'OMR','south african rand':'ZAR',
}
MONEY=('taxable','cgst','sgst','igst','cess','round_off','total')
ITEM_MONEY=('rate','value','list_rate','printed_cgst','printed_sgst','printed_igst','printed_total')


def currency_code(value):
    value=unicodedata.normalize('NFKC',str(value or '')).strip()
    if not value:return None
    if value.upper() in CODES:return value.upper()
    key=re.sub(r'\s+',' ',value.casefold()).rstrip('.')
    codes=set(re.findall(r'(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])',value.upper())) & CODES
    for symbol,code in [('€','EUR'),('£','GBP'),('₹','INR')]:
        if symbol in value:codes.add(code)
    for symbol,code in [('US$','USD'),('NZ$','NZD'),('A$','AUD'),('C$','CAD'),('S$','SGD')]:
        if re.search(r'(?<![A-Za-z])'+re.escape(symbol),value,re.I):codes.add(code)
    if len(codes)>1:raise ValueError('Conflicting currency codes / symbols; review Currency / exchange rate.')
    if key in ALIASES:return ALIASES[key]
    if len(codes)==1:return codes.pop()
    # A spelling repair is allowed only for a long, unambiguous currency name.
    if len(key)>=7 and key.isascii() and re.fullmatch(r'[a-z ]+',key):
        near=get_close_matches(key,[k for k in ALIASES if len(k)>=7],n=3,cutoff=.88)
        if near and len({ALIASES[k] for k in near})==1:return ALIASES[near[0]]
    raise ValueError('Currency is unclear: '+value+'. Choose its currency code in Currency / exchange rate.')


def decimal(value,label):
    raw=str(value).strip()
    if ',' in raw and not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?',raw):
        raise ValueError('Use a decimal point for '+label+'; comma grouping is unclear.')
    raw=raw.replace(',','')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',raw) or len(raw)>40:
        raise ValueError('Enter a valid '+label+'.')
    try:result=Decimal(raw)
    except InvalidOperation:raise ValueError('Enter a valid '+label+'.') from None
    if not result.is_finite() or abs(result)>Decimal('1e20'):raise ValueError('Invalid '+label+'.')
    return result


def facts(invoice):
    return {**{k:invoice.get(k) for k in (*MONEY,'currency','foreign_currency','exchange_rate','exchange_rate_basis','exchange_rate_units','foreign_invoice_value')},
            'items':[{k:i.get(k) for k in (*ITEM_MONEY,'quantity','name','hsn','unit')} for i in invoice.get('items',[])]}


def fingerprint(invoice):
    return hashlib.sha256(json.dumps(facts(invoice),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def settings_path(root,record):
    identity=[record['client'],record.get('digest') or str(record.get('source_path') or record['path'])]
    key=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return Path(root)/'.invoice_app'/'currency_reviews'/(key+'.json')


def load_settings(root,record):
    path=settings_path(root,record)
    if not path.exists():return None
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('facts_sha256')!=fingerprint(record['invoice']):
        raise ValueError('Invoice amounts changed. Review Currency / exchange rate again; previous XML retained.')
    return data


def save_settings(root,record,code,rate,basis='foreign'):
    code=currency_code(code)
    if not code:raise ValueError('Choose the invoice currency.')
    if basis not in ('foreign','INR'):raise ValueError('Choose whether the displayed source amounts are foreign currency or INR.')
    parsed=decimal(rate,'INR exchange rate') if str(rate or '').strip() else None
    if code!='INR' and (parsed is None or parsed<=0):raise ValueError('Enter INR per 1 '+code+' (greater than zero).')
    data={'schema_version':1,'facts_sha256':fingerprint(record['invoice']),'currency':code,
          'exchange_rate':format(parsed,'f') if parsed is not None else '1','amounts_basis':basis,'manual':True}
    convert(record['invoice'],data)  # Validate before storing a correction.
    path=settings_path(root,record);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
    try:temporary.write_text(json.dumps(data,indent=2),encoding='utf-8');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return data


def convert(invoice,settings=None):
    """Return an INR copy; never mutate extraction, manual review or quantities."""
    inv=deepcopy(invoice)
    source=currency_code(settings['currency'] if settings else inv.get('currency'))
    foreign=currency_code(inv.get('foreign_currency')) if inv.get('foreign_currency') else None
    if settings:
        foreign=source if source!='INR' else None
        source='INR' if settings['amounts_basis']=='INR' else source
    if source is None and foreign:
        raise ValueError('Confirm whether the invoice amounts are '+foreign+' or INR in Currency / exchange rate.')
    if source in (None,'INR'):
        # Existing dual-currency INR invoices must not be multiplied again.
        if foreign and foreign!='INR':
            rate=decimal(settings['exchange_rate'] if settings else inv.get('exchange_rate'),'INR exchange rate')
            if rate<=0:raise ValueError('Positive exchange rate required for '+foreign+'.')
        if settings:
            inv.update(currency='INR',foreign_currency=foreign or '',exchange_rate=settings['exchange_rate'])
        return inv
    if foreign and foreign!=source:raise ValueError('Conflicting currency fields; review Currency / exchange rate.')
    rate=decimal(settings['exchange_rate'] if settings else inv.get('exchange_rate'),'INR per 1 '+source+' exchange rate')
    if rate<=0:raise ValueError('Exchange rate must be greater than zero.')
    direction='INR_per_foreign' if settings else inv.get('exchange_rate_basis','INR_per_foreign')
    if direction not in ('INR_per_foreign','foreign_per_INR'):
        raise ValueError('Exchange-rate direction is unclear. Enter INR per 1 '+source+' in Currency / exchange rate.')
    with localcontext() as ctx:
        ctx.prec=50
        units=decimal('1' if settings else inv.get('exchange_rate_units') or '1','exchange-rate unit count')
        if units<=0:raise ValueError('Exchange-rate unit count must be positive.')
        rate=rate/units if direction=='INR_per_foreign' else units/rate
        def scaled(value,label,rounded=True):
            result=decimal(value,label)*rate
            return format(result.quantize(Decimal('.01'),rounding=ROUND_HALF_UP) if rounded else result,'f')
        for key in MONEY:
            if inv.get(key) not in (None,''):inv[key]=scaled(inv[key],key)
        for item in inv.get('items',[]):
            for key in ITEM_MONEY:
                if item.get(key) not in (None,''):item[key]=scaled(item[key],key,key not in ('rate','list_rate'))
        inv.update(currency='INR',foreign_currency=source,exchange_rate=format(rate,'f'),
                   foreign_invoice_value=invoice.get('total'),
                   currency_conversion={'source_currency':source,'inr_per_unit':format(rate,'f'),
                                        'rate_source':'manual' if settings else 'invoice','original_amounts':facts(invoice)})
    return inv


def for_record(root,record):
    return convert(record.get('invoice') or {},load_settings(root,record) if root is not None else None)

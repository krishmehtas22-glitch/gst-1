"""Visible and editable unit estimates from printed tokens and product context.

Do not scale quantity/rate/value or interpret medicine strength as sold mass.
Printed/custom units and explicit invoice corrections outrank estimates.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from .accounting import money
from .unit_catalog import UNITS

ALIASES={
    'Nos':('no','nos','nos.','number','numbers','each','ea'),
    'PCS':('pc','pcs','pcs.','piece','pieces','piece(s)'),
    'Units':('unit','units','unt'),
    'KG':('kg','kgs','kilogram','kilograms','kilogramme','kilogrammes','kilo','kilos'),
    'GMS':('g','gm','gms','gram','grams','gramme','grammes'),
    'MG':('mg','milligram','milligrams'), 'MCG':('mcg','ug','µg','μg','microgram','micrograms'),
    'MT':('mt','mts','metric ton','metric tons','metric tonne','metric tonnes','tonne','tonnes'),
    'LTR':('l','lt','ltr','ltrs','litre','litres','liter','liters'),
    'ML':('ml','mlt','millilitre','millilitres','milliliter','milliliters'),
    'MTR':('m','mtr','mtrs','meter','meters','metre','metres'),
    'CMS':('cm','cms','centimeter','centimeters','centimetre','centimetres'),
    'MM':('mm','millimeter','millimeters','millimetre','millimetres'),
    'FT':('ft','foot','feet'), 'SQFT':('sq ft','sqft','square feet'), 'SQMT':('sq m','sqm','sqmt','square metres','square meters'),
    'BOX':('box','boxes'), 'BTL':('btl','bottle','bottles'), 'BAG':('bag','bags'),
    'CTN':('ctn','carton','cartons'), 'Packs':('pack','packs','pac'), 'PKT':('pkt','packet','packets'),
    'SET':('set','sets'), 'PRS':('pair','pairs','prs'), 'DOZ':('doz','dozen','dozens'),
    'ROLL':('roll','rolls','rol'), 'REAM':('ream','reams','rim'),
    'TBS':('tbs','tablet','tablets','tab','tabs'), 'STRIP':('strip','strips'),
    'BLISTER':('blister','blisters','blister pack','blister packs'),
    'Vials':('vial','vials'), 'AMP':('ampoule','ampoules','ampule','ampules'),
    'Tubes':('tube','tubes','tub'), 'JAR':('jar','jars'), 'QTL':('qtl','quintal','quintals'),
    'Qty':('qty','quantity'),
}
ALIAS_INDEX={alias.casefold():key for key,aliases in ALIASES.items() for alias in aliases}
PLACEHOLDERS={'','-','--','n/a','na','not applicable','not specified','not mentioned','as applicable',
              'unknown','none','null','not stated','unspecified','not available','tbd'}
PACK_WORDS={'box':'BOX','boxes':'BOX','carton':'CTN','cartons':'CTN','packet':'PKT','packets':'PKT',
 'pack':'Packs','packs':'Packs','bag':'BAG','bags':'BAG','roll':'ROLL','rolls':'ROLL',
 'strip':'STRIP','strips':'STRIP','blister':'BLISTER','blisters':'BLISTER','bottle':'BTL','bottles':'BTL',
 'vial':'Vials','vials':'Vials','ampoule':'AMP','ampoules':'AMP','tube':'Tubes','tubes':'Tubes',
 'jar':'JAR','jars':'JAR','set':'SET','sets':'SET','pair':'PRS','pairs':'PRS','dozen':'DOZ','ream':'REAM','reams':'REAM'}
MASS_FOOD=r'\b(?:rice|wheat|flour|atta|grain|grains|dal|lentils?|pulses?|potatoes?|tomatoes?|onions?|vegetables?|sugar|salt|spices?|turmeric|chilli|chili)\b'
COUNT_GOODS=r'\b(?:pens?|pencils?|folders?|files?|notebooks?|books?|keyboards?|mouse|mice|lights?|lamps?|bulbs?|tools?|fasteners?|bolts?|nuts?|screws?|bags?|bottles?|boxes?|cartons?|cartons?|utensils?|monitors?|thermometers?|masks?|stents?|implants?|syringes?|gloves?|shirts?|chairs?|tables?|computers?|printers?|phones?)\b'
STRENGTH=r'\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|μg|g|ml)\b'


def canonical_unit(token,units=UNITS):
    token=' '.join(str(token or '').strip().split())
    exact=next((key for key in units if key.casefold()==token.casefold()),None)
    return exact or (ALIAS_INDEX.get(token.casefold()) if ALIAS_INDEX.get(token.casefold()) in units else None)


def quantity_parts(value):
    text=str(value or '').strip()
    match=re.fullmatch(r'([+-]?[\d,]+(?:\.\d+)?)\s*([^\d]+)?',text)
    if not match:return None
    suffix=(match[2] or '').strip()
    if suffix and not canonical_unit(suffix) and uncertain_unit(suffix):return None
    return match[1],suffix


def uncertain_unit(token):
    text=str(token or '').strip().casefold()
    return text in PLACEHOLDERS or bool(re.search(r'\b(?:as applicable|or)\b|[/|]',text))


def default_missing_quantity(item):
    """User-authorized, visible defaults; zero/invalid printed numbers remain.

    Quantity 1 is an assumption, not a value extracted from the document.
    An explicitly printed unit always outranks the generic Units fallback.
    """
    if item.get('quantity') is None or str(item.get('quantity','')).strip() in ('','-','--','n/a','N/A'):
        item.update(quantity='1',quantity_assumed=True,quantity_confirmed=False,
                    quantity_evidence='Quantity omitted: default 1 requested by you')
        if not item.get('unit'):
            item.update(unit='Units',unit_auto=True,unit_origin='estimated',unit_confidence=0,
                        unit_evidence='Quantity and unit omitted: default 1 Units requested by you')


def suggest_unit(item,invoice):
    name=str(item.get('name','')).casefold()
    try:quantity=money(item.get('quantity',0));whole=quantity==quantity.to_integral_value()
    except (ValueError,TypeError,ArithmeticError):return None
    if quantity<=0:return None
    # Rate basis / explicit container wording outranks a product category.
    basis=re.search(r'\b(?:per|sold by|billed by|priced per)\s+([a-zµμ]+(?:\s+(?:tonnes?|tons?|feet|metres?|meters?))?)\b',name)
    if basis and canonical_unit(basis[1]):return canonical_unit(basis[1]),'Printed description states '+basis[0],.95
    pack_pattern='|'.join(sorted(PACK_WORDS,key=len,reverse=True))
    packaging=re.search(r'\b('+pack_pattern+r')\s+of\b|\(\s*('+pack_pattern+r')\s*\)',name)
    if packaging:
        word=packaging[1] or packaging[2]
        return PACK_WORDS[word],'Description identifies sold packaging: '+word,.92
    for word in ('strip','strips','blister','blisters','vial','vials','ampoule','ampoules','tube','tubes','bottle','bottles','jar','jars','pair','pairs','dozen','ream','reams','roll','rolls','set','sets'):
        if re.search(r'\b'+word+r'\b',name):return PACK_WORDS[word],'Product/packaging keyword: '+word,.84
    if re.search(r'\b(?:assortment|tool kit|toolkit)\b',name):return 'SET','Assorted tools estimated as a set',.72
    medicine=str(item.get('hsn','')).startswith(('3003','3004')) or bool(re.search(r'\b(?:paracetamol|amoxicillin|medicine|antibiotic|syrup|ointment|capsule|tablet|infusion)\b',name))
    if medicine:
        if re.search(r'\b(?:tablet|tablets|tabs)\b',name):return 'TBS','Medicine form: tablets; strength is not quantity',.88
        if re.search(r'\b(?:ointment|cream)\b',name):return 'Tubes','Medicinal ointment/cream estimated as a tube',.75
        if re.search(r'\b(?:syrup|oral suspension)\b',name) and re.search(STRENGTH,name):return 'BTL','Liquid medicine with a stated bottle-size/strength estimated as bottles',.78
        return ('Nos' if whole else 'Units'),'Medicine strength ignored; counted items/unspecified dosage packaging estimated',.65
    mass_food=bool(re.search(MASS_FOOD,name))
    liquid=bool(re.search(r'\b(?:milk|oil|diesel|petrol|fuel|juice|alcohol|solvent|water)\b',name))
    pack_size=bool(re.search(r'\b\d+(?:\.\d+)?\s*(?:kg|g|gm|grams?|ml|litres?|liters?|l)\b',name))
    if whole and pack_size and (mass_food or liquid):return 'Packs','Stated retail pack size; counted packs estimated, not content weight/volume',.60
    if mass_food:return 'KG','Loose/unpackaged food or grain normally billed by weight',.82
    if liquid:return 'LTR','Unpackaged liquid normally billed by volume',.78
    if re.search(r'\b(?:cable|wire|fabric|cloth|rope)\b',name):
        if whole and re.search(r'\b\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\b',name):return 'ROLL','Stated length in description estimated as a roll; no content conversion',.58
        return 'MTR','Continuous cable/wire/fabric normally billed by length',.70
    if re.search(COUNT_GOODS,name):return ('Nos' if whole else 'Units'),'Countable product keyword; packaging not explicitly stated',.75 if whole else .35
    if re.search(r'\b(?:scrap|metal powder|steel ingots?|aluminium ingots?|aluminum ingots?|granules?|resin)\b',name):return 'KG','Bulk material normally billed by weight',.72
    return ('Nos' if whole else 'Units'),'No reliable unit clue; visible generic count/quantity estimate — check before import',.35


def product_key(invoice,item,demo):
    seller=str(invoice.get('seller_gstin','')).strip().upper()
    name=' '.join(str(invoice.get('seller_name','')).casefold().split())
    product=' '.join(str(item.get('name','')).casefold().split())
    hsn=str(item.get('hsn',''))
    if not all((seller,name,product,hsn)):return None
    return hashlib.sha256(json.dumps([bool(demo),seller,name,product,hsn],ensure_ascii=False).encode()).hexdigest()


def item_signature(item):
    values=[str(item.get('name','')).strip().casefold(),str(item.get('hsn',''))]
    for key in ('quantity','rate','value'):
        try:values.append(format(money(item.get(key,'')).normalize(),'f'))
        except (ValueError,TypeError,ArithmeticError):values.append(str(item.get(key,'')))
    return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()


def _read(path,default):
    from .engine import read_json
    return read_json(path) if path.exists() else deepcopy(default)


class UnitResolver:
    def __init__(self,root,demo=True,enabled=True):
        self.root=root;self.demo=demo;self.enabled=enabled;self.catalogs={}
        self.preferences=_read(root/'.invoice_app/unit_preferences.json',{'version':1,'products':{}})
        for path in (root/'.invoice_app/companies').glob('*/client.json'):
            try:
                config=_read(path,{})
                if bool(config.get('demo_only'))!=bool(demo):continue
                key=(config.get('source_seller_gstin','').upper(),config.get('source_seller_name','').casefold())
                if isinstance(config.get('units'),dict):self.catalogs[key]=config['units']
            except (ValueError,OSError,TypeError):continue

    def apply(self,record):
        invoice=deepcopy(record['invoice'])
        units={**UNITS,**self.catalogs.get((str(invoice.get('seller_gstin','')).upper(),str(invoice.get('seller_name','')).casefold()),{})}
        record['available_units']=list(units)
        record['demo_mode']=self.demo
        cache=self.root/'.invoice_app/unit_estimates'/(record['digest']+'.json')
        saved=_read(cache,{'source_sha256':record['digest'],'items':{}})
        previous=saved.get('items',{}) if saved.get('source_sha256')==record['digest'] else {}
        updates={}
        for index,item in enumerate(invoice.get('items',[])):
            default_missing_quantity(item)
            parts=quantity_parts(item.get('quantity',''))
            if parts and parts[1]:
                item.setdefault('printed_quantity',item['quantity']);item['quantity']=parts[0]
                if not item.get('unit'):item['unit']=parts[1]
            raw=item.get('unit','');known=canonical_unit(raw,units)
            if known=='Qty' and not item.get('unit_correction_reviewed') and item.get('unit_origin')!='manual':
                known=None;raw='' # Qty labels a quantity column, not a selling unit.
            if known:
                if str(raw)!=known:item.setdefault('printed_unit',raw)
                item['unit']=known
                if not item.get('unit_origin'):
                    item.update(unit_origin='manual' if record.get('reviewed') else 'printed',unit_auto=False,unit_confidence=1.0,
                                unit_evidence='Confirmed invoice unit' if record.get('reviewed') else 'Printed unit: '+str(raw))
                updates[str(index)]={'signature':item_signature(item),'unit_data':{key:item[key] for key in item if key.startswith('unit_') or key=='unit'}}
                continue
            if not uncertain_unit(raw):
                if not item.get('unit_origin'):
                    item.update(unit_origin='manual' if record.get('reviewed') else 'printed',
                                unit_auto=False,unit_confidence=1.0,unit_evidence='Printed custom unit: '+str(raw))
                continue # Preserve custom printed symbols without inventing conversions.
            if not self.enabled:continue
            signature=item_signature(item)
            retained=previous.get(str(index),{})
            if retained.get('signature')==signature and canonical_unit(retained.get('unit_data',{}).get('unit'),units):
                item.update(retained['unit_data']);item['unit']=canonical_unit(item['unit'],units)
                updates[str(index)]={'signature':signature,'unit_data':{key:item[key] for key in item if key.startswith('unit_') or key=='unit'}}
                continue
            learned=self.preferences.get('products',{}).get(product_key(invoice,item,self.demo),{})
            if canonical_unit(learned.get('unit'),units):
                suggestion=(canonical_unit(learned['unit'],units),'Your previous correction for this supplier/product',.98);origin='learned'
            else:
                suggestion=suggest_unit(item,invoice);origin='estimated'
            if suggestion:
                unit,reason,confidence=suggestion
                if unit not in units:continue
                item.update(unit=unit,unit_origin=origin,unit_auto=True,unit_evidence=reason,unit_confidence=confidence)
                updates[str(index)]={'signature':signature,'unit_data':{key:item[key] for key in item if key.startswith('unit_') or key=='unit'}}
        record['invoice']=invoice
        if self.enabled and saved.get('items')!=updates:
            from .engine import write_json
            write_json(cache,{'source_sha256':record['digest'],'items':updates})


def remember_units(root,record,invoice):
    from .engine import write_json
    preferences_path=root/'.invoice_app/unit_preferences.json'
    prefs=_read(preferences_path,{'version':1,'products':{}})
    cache_path=root/'.invoice_app/unit_estimates'/(record['digest']+'.json')
    cache=_read(cache_path,{'source_sha256':record['digest'],'items':{}})
    for index,item in enumerate(invoice.get('items',[])):
        if not item.get('unit_correction_reviewed'):continue
        key=product_key(invoice,item,record.get('demo_mode',True))
        if key:prefs.setdefault('products',{})[key]={'unit':item['unit'],'source_sha256':record['digest']}
        cache.setdefault('items',{})[str(index)]={'signature':item_signature(item),
            'unit_data':{field:item[field] for field in item if field.startswith('unit_') or field=='unit'}}
    write_json(preferences_path,prefs);write_json(cache_path,cache)

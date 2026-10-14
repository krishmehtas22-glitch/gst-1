"""Local unit symbols and GST UQC mappings; no automatic quantity conversion.

References: India Compliance GST UOM_MAP and ERPNext unit definitions.
Custom mg/mcg/strip/vial units use OTH, not invented standard GST codes.
"""
UNITS = {
    'Nos': {'formal_name':'Numbers','uqc':'NOS','decimal_places':0},
    'KG': {'formal_name':'Kilograms','uqc':'KGS','decimal_places':3},
    'ROLL': {'formal_name':'Rolls','uqc':'ROL','decimal_places':0,'tally_uqc':'ROL-ROLLS'},
    'SET': {'formal_name':'Sets','uqc':'SET','decimal_places':0},
    'BOX': {'formal_name':'Boxes','uqc':'BOX','decimal_places':0},
    'PRS': {'formal_name':'Pairs','uqc':'PRS','decimal_places':0,'tally_uqc':'PRS-PAIRS'},
    'REAM': {'formal_name':'Reams','uqc':'RIM','decimal_places':0,'tally_uqc':'RIM-REAMS'},
    'PKT': {'formal_name':'Packets','uqc':'PAC','decimal_places':0,'tally_uqc':'PAC-PACKS'},
    'KGS': {'formal_name':'Kilograms','uqc':'KGS','decimal_places':3},
    'DOZ': {'formal_name':'Dozens','uqc':'DOZ','decimal_places':0,'tally_uqc':'DOZ-DOZENS'},
    'MT': {'formal_name':'Metric Tonnes','uqc':'MTS','decimal_places':3,'tally_uqc':'MTS-METRIC TON'},
    'PCS': {'formal_name':'Pieces','uqc':'PCS','decimal_places':0},
    'LTR': {'formal_name':'Litres','uqc':'LTR','decimal_places':3},
    'MTR': {'formal_name':'Metres','uqc':'MTR','decimal_places':3},
    'Units': {'formal_name':'Units','uqc':'UNT','decimal_places':0},
    'Vials': {'formal_name':'Vials','uqc':'OTH','decimal_places':0},
    'Packs': {'formal_name':'Packs','uqc':'PAC','decimal_places':0,'tally_uqc':'PAC-PACKS'},
    'Tubes': {'formal_name':'Tubes','uqc':'TUB','decimal_places':0,'tally_uqc':'TUB-TUBES'},
    'Liters': {'formal_name':'Liters','uqc':'LTR','decimal_places':3},
    'GMS': {'formal_name':'Grammes','uqc':'GMS','decimal_places':6},
    'MG': {'formal_name':'Milligrams','uqc':'OTH','decimal_places':6},
    'MCG': {'formal_name':'Micrograms','uqc':'OTH','decimal_places':6},
    'ML': {'formal_name':'Millilitres','uqc':'MLT','decimal_places':3,'tally_uqc':'MLT-MILLILITRE'},
    'BTL': {'formal_name':'Bottles','uqc':'BTL','decimal_places':0,'tally_uqc':'BTL-BOTTLES'},
    'BAG': {'formal_name':'Bags','uqc':'BAG','decimal_places':0,'tally_uqc':'BAG-BAGS'},
    'CTN': {'formal_name':'Cartons','uqc':'CTN','decimal_places':0,'tally_uqc':'CTN-CARTONS'},
    'TBS': {'formal_name':'Tablets','uqc':'TBS','decimal_places':0,'tally_uqc':'TBS-TABLETS'},
    'STRIP': {'formal_name':'Strips','uqc':'OTH','decimal_places':0},
    'BLISTER': {'formal_name':'Blister Packs','uqc':'OTH','decimal_places':0},
    'AMP': {'formal_name':'Ampoules','uqc':'OTH','decimal_places':0},
    'JAR': {'formal_name':'Jars','uqc':'OTH','decimal_places':0},
    'FT': {'formal_name':'Feet','uqc':'OTH','decimal_places':3},
    'CMS': {'formal_name':'Centimetres','uqc':'CMS','decimal_places':3,'tally_uqc':'CMS-CENTIMETERS'},
    'MM': {'formal_name':'Millimetres','uqc':'OTH','decimal_places':3},
    'SQFT': {'formal_name':'Square Feet','uqc':'SQF','decimal_places':3,'tally_uqc':'SQF-SQUARE FEET'},
    'SQMT': {'formal_name':'Square Metres','uqc':'SQM','decimal_places':3,'tally_uqc':'SQM-SQUARE METERS'},
    'QTL': {'formal_name':'Quintals','uqc':'QTL','decimal_places':3,'tally_uqc':'QTL-QUINTAL'},
    'Qty': {'formal_name':'Quantity (unspecified measure)','uqc':'OTH','decimal_places':6},
}

# Exact choices transcribed from the user's TallyPrime 6.2 UQC dropdown.
# These are reporting classifications; they never convert quantities or rates.
TALLY_UQC_LABELS = {
    'BAG':'BAG-BAGS','BAL':'BAL-BALE','BDL':'BDL-BUNDLES',
    'BKL':'BKL-BUCKLES','BOU':'BOU-BILLION OF UNITS','BOX':'BOX-BOX',
    'BTL':'BTL-BOTTLES','BUN':'BUN-BUNCHES','CAN':'CAN-CANS',
    'CBM':'CBM-CUBIC METERS','CCM':'CCM-CUBIC CENTIMETERS',
    'CMS':'CMS-CENTIMETERS','CTN':'CTN-CARTONS','DOZ':'DOZ-DOZENS',
    'DRM':'DRM-DRUMS','GGK':'GGK-GREAT GROSS','GMS':'GMS-GRAMMES',
    'GRS':'GRS-GROSS','GYD':'GYD-GROSS YARDS','KGS':'KGS-KILOGRAMS',
    'KLR':'KLR-KILOLITRE','KME':'KME-KILOMETRE','LTR':'LTR-LITRES',
    'MLT':'MLT-MILLILITRE','MTR':'MTR-METERS','MTS':'MTS-METRIC TON',
    'NOS':'NOS-NUMBERS','OTH':'OTH-OTHERS','PAC':'PAC-PACKS',
    'PCS':'PCS-PIECES','PRS':'PRS-PAIRS','QTL':'QTL-QUINTAL',
    'ROL':'ROL-ROLLS','SET':'SET-SETS','SQF':'SQF-SQUARE FEET',
    'SQM':'SQM-SQUARE METERS','SQY':'SQY-SQUARE YARDS',
    'TBS':'TBS-TABLETS','TGM':'TGM-TEN GROSS','THD':'THD-THOUSANDS',
    'TON':'TON-TONNES','TUB':'TUB-TUBES','UGS':'UGS-US GALLONS',
    'UNT':'UNT-UNITS','YDS':'YDS-YARDS',
}
UQC_SYMBOLS = {'KGS':'KG','MLT':'ML','MTS':'MT','NOS':'Nos','PAC':'Packs',
    'ROL':'ROLL','SQF':'SQFT','SQM':'SQMT','TUB':'Tubes','UNT':'Units'}
NEW_UNIT_DESCRIPTIONS = {
    'BAL':'Baled item','BDL':'Bundle','BKL':'Buckle',
    'BOU':'Billion-unit count','BUN':'Bunch','CAN':'Canned item',
    'CBM':'Cubic metre','CCM':'Cubic centimetre','DRM':'Drum',
    'GGK':'Great-gross count','GRS':'Gross count','GYD':'Gross yard',
    'KLR':'Kilolitre measure','KME':'Kilometre measure','OTH':'Other measure',
    'SQY':'Square yard','TGM':'Ten-gross count','THD':'Thousand',
    'TON':'Tonne','UGS':'US gallon','YDS':'Yard',
}
FRACTIONAL_UQC = {'CBM','CCM','CMS','GMS','GYD','KGS','KLR','KME','LTR',
    'MLT','MTR','MTS','QTL','SQF','SQM','SQY','TON','UGS','YDS'}
for _code,_label in TALLY_UQC_LABELS.items():
    _symbol=UQC_SYMBOLS.get(_code,_code)
    UNITS.setdefault(_symbol,{'formal_name':NEW_UNIT_DESCRIPTIONS.get(_code,_symbol),
        'uqc':_code,'decimal_places':6 if _code in FRACTIONAL_UQC else 0})
    UNITS[_symbol]['tally_uqc']=_label

# Classify a printed/custom symbol without renaming it in stock/voucher fields.
UQC_NAME_ALIASES = {
    'BAL':('bale','bales'), 'BDL':('bundle','bundles'),
    'BKL':('buckle','buckles'), 'BOU':('billion of units','billion units'),
    'BUN':('bunch','bunches'), 'CAN':('can','cans'),
    'CBM':('cubic meter','cubic meters','cubic metre','cubic metres','cu m','m³','m3'),
    'CCM':('cubic centimeter','cubic centimeters','cubic centimetre','cubic centimetres','cc','cm³','cm3'),
    'DRM':('drum','drums'), 'GGK':('great gross',), 'GRS':('gross',),
    'GYD':('gross yard','gross yards'),
    'KLR':('kilolitre','kilolitres','kiloliter','kiloliters','kl'),
    'KME':('kilometre','kilometres','kilometer','kilometers','km'),
    'SQY':('square yard','square yards','sq yd','sqyd'),
    'TGM':('ten gross',), 'THD':('thousand','thousands'),
    'TON':('ton','tons'), 'UGS':('us gallon','us gallons','us gal'),
    'YDS':('yard','yards','yd'),
    'CMS':('cm','centimetre','centimetres','centimeter','centimeters'),
    'LTR':('litre','litres','liter','liters','l'),
    'GMS':('gram','grams','gramme','grammes','g','gm'),
    'MTR':('metre','metres','meter','meters','m'),
    'PAC':('pack','packs','packet','packets'),
}
UQC_ALIAS_INDEX={alias.casefold():code for code,aliases in UQC_NAME_ALIASES.items() for alias in aliases}


def _unit_definition(symbol):
    name=' '.join(str(symbol or '').split()).casefold()
    catalog=next((v for k,v in UNITS.items() if k.casefold()==name),None)
    if catalog is not None:return catalog
    code=UQC_ALIAS_INDEX.get(name)
    return UNITS.get(UQC_SYMBOLS.get(code,code),{})


# Descriptions are words, separate from symbols and GST reporting labels.
FORMAL_SINGULAR = {
    'packs':'Pack','units':'Unit','vials':'Vial','tubes':'Tube','liters':'Liter',
    'numbers':'Number','pieces':'Piece','kilograms':'Kilogram','grammes':'Gramme',
    'litres':'Litre','metres':'Metre','meters':'Metre','boxes':'Box','sets':'Set',
    'rolls':'Roll','pairs':'Pair','reams':'Ream','packets':'Packet','dozens':'Dozen',
    'bottles':'Bottle','bags':'Bag','cartons':'Carton','tablets':'Tablet',
    'cases':'Case','strips':'Strip','jars':'Jar','ampoules':'Ampoule',
}
STANDARD_UQC = {'NOS':'NOS-NUMBERS','PCS':'PCS-PIECES','KGS':'KGS-KILOGRAMS',
    'GMS':'GMS-GRAMMES','LTR':'LTR-LITRES','MTR':'MTR-METERS','BOX':'BOX-BOX',
    'SET':'SET-SETS','UNT':'UNT-UNITS','OTH':'OTH-OTHERS'}
STANDARD_UQC.update({entry['uqc']:entry['tally_uqc'] for entry in UNITS.values()
                     if entry.get('tally_uqc')})
STANDARD_UQC.update(TALLY_UQC_LABELS)
STANDARD_UQC.update({label:label for label in TALLY_UQC_LABELS.values()})
# Correct the old generated spelling to the choice shown in Tally's dropdown.
STANDARD_UQC['MLT-MILILITRE']='MLT-MILLILITRE'


def unit_uqc(symbol,value=None):
    """Assign catalog UQC for known symbols; custom units use OTH unless explicit."""
    catalog=_unit_definition(symbol)
    expected=catalog.get('tally_uqc') or STANDARD_UQC.get(catalog.get('uqc'))
    value=str(value or '').strip()
    if not value or value.casefold() in {'not applicable','not applicable-','na','none','unknown','oth','oth-others','unt','unt-units'}:
        return expected or 'OTH-OTHERS'
    return STANDARD_UQC.get(value.upper(),value if '-' in value else (expected or 'OTH-OTHERS'))


def unit_formal_name(symbol,description=None,uqc=None):
    """Use a plain description distinct from the symbol and UQC code/label."""
    name=str(symbol).strip()
    normalize=lambda value:' '.join(str(value or '').split()).casefold()
    catalog=_unit_definition(name)
    formal=str(description or catalog.get('formal_name') or '').strip()
    labels=[uqc,catalog.get('uqc'),catalog.get('tally_uqc'),unit_uqc(name,uqc)]
    forbidden={normalize(name)}
    for label in labels:
        if label:
            forbidden.add(normalize(label))
            parts=str(label).split('-',1)
            forbidden.update(normalize(part) for part in parts)
    if not formal or normalize(formal) in forbidden or '(selling unit)' in normalize(formal):
        candidate=str(catalog.get('formal_name') or name)
        formal=FORMAL_SINGULAR.get(normalize(candidate),FORMAL_SINGULAR.get(normalize(name),'Measure of '+name))
        if normalize(formal) in forbidden:
            formal={'ream':'Paper ream','roll':'Material roll','set':'Item set',
                    'box':'Container box'}.get(normalize(name),'Measure of '+name)
    return formal

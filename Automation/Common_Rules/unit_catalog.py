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
    'ML': {'formal_name':'Millilitres','uqc':'MLT','decimal_places':3,'tally_uqc':'MLT-MILILITRE'},
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


def unit_uqc(symbol,value=None):
    """Assign catalog UQC for known symbols; custom units use OTH unless explicit."""
    catalog=next((v for k,v in UNITS.items() if k.casefold()==str(symbol).strip().casefold()),{})
    expected=catalog.get('tally_uqc') or STANDARD_UQC.get(catalog.get('uqc'))
    value=str(value or '').strip()
    if not value or value.casefold() in {'not applicable','not applicable-','na','none','unknown','oth','oth-others','unt','unt-units'}:
        return expected or 'OTH-OTHERS'
    return STANDARD_UQC.get(value.upper(),value if '-' in value else (expected or 'OTH-OTHERS'))


def unit_formal_name(symbol,description=None,uqc=None):
    """Use a plain description distinct from the symbol and UQC code/label."""
    name=str(symbol).strip()
    normalize=lambda value:' '.join(str(value or '').split()).casefold()
    catalog=next((v for k,v in UNITS.items() if k.casefold()==name.casefold()),{})
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

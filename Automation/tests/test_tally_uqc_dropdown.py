import hashlib
from pathlib import Path
import pytest
from Common_Rules.unit_catalog import TALLY_UQC_LABELS,UQC_SYMBOLS,unit_uqc
from Common_Rules.unit_inference import canonical_unit
from Common_Rules.tally_units import simple_unit


@pytest.mark.parametrize('code',list(TALLY_UQC_LABELS))
def test_dropdown_choices_emit_exact_uqc_and_different_plain_description(code):
    symbol=UQC_SYMBOLS.get(code,code)
    node=simple_unit(symbol,None,6,code.lower())
    label=TALLY_UQC_LABELS[code]
    assert node.findtext('GSTREPUOM')==label
    formal=node.findtext('ORIGINALNAME')
    assert formal.casefold() not in {label.casefold(),*(p.casefold() for p in label.split('-',1))}
    assert '(selling' not in formal
    assert node.findtext('NAME')==symbol and node.findtext('DECIMALPLACES')=='6'
    assert unit_uqc(symbol,label.lower())==label


@pytest.mark.parametrize('printed,symbol,uqc',[
    ('cubic metres','CBM','CBM-CUBIC METERS'),
    ('cc','CCM','CCM-CUBIC CENTIMETERS'),
    ('bundle','BDL','BDL-BUNDLES'),
    ('bales','BAL','BAL-BALE'),
    ('kilolitres','KLR','KLR-KILOLITRE'),
    ('km','KME','KME-KILOMETRE'),
    ('square yards','SQY','SQY-SQUARE YARDS'),
    ('US gallons','UGS','UGS-US GALLONS'),
    ('yards','YDS','YDS-YARDS'),
    ('gross','GRS','GRS-GROSS'),
])
def test_printed_new_unit_spelling_has_verified_mapping(printed,symbol,uqc):
    assert unit_uqc(symbol)==uqc
    node=simple_unit(printed,None,6,None)
    assert node.findtext('GSTREPUOM')==uqc
    assert node.findtext('NAME')==printed


@pytest.mark.parametrize('printed,expected',[
    ('pac','Packs'),('rol','ROLL'),('sqm','SQMT'),('sqft','SQFT'),
    ('metric tonnes','MT'),('tonnes','MT'),('ml','ML'),('cm','CMS')])
def test_existing_printed_symbol_choices_remain_stable(printed,expected):
    assert canonical_unit(printed)==expected


def test_millilitre_matches_actual_dropdown_spelling():
    assert unit_uqc('ML','MLT-MILILITRE')=='MLT-MILLILITRE'


def test_button_transport_helpers_have_not_changed():
    root=Path(__file__).resolve().parents[2]
    expected={
        'tally_import.py':'aa0ac53f912f80b9cb14e82457ccc5bf674358d7c8d075bf78a0f1c08900810c',
        'tally_units.py':'1fc16af22c7a314d6c2fa2de34b316cd2b084fb25325523ebefc9d7f4b74f65a',
    }
    for name,digest in expected.items():
        assert hashlib.sha256((root/'Automation/Common_Rules'/name).read_bytes()).hexdigest()==digest

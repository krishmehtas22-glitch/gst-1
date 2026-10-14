import xml.etree.ElementTree as ET
import pytest
from Automation.Common_Rules.unit_catalog import unit_formal_name,UNITS,unit_uqc
from Automation.Common_Rules.tally_units import simple_unit,prepare_unit_create


@pytest.mark.parametrize('description',['PAC','pac-packs','  PAC-PACKS  ','Packs'])
def test_formal_label_does_not_repeat_symbol_or_uqc(description):
    unit=simple_unit('Packs',description,3,'PAC-PACKS')
    assert unit.findtext('ORIGINALNAME')=='Pack'
    assert unit.findtext('NAME')=='Packs'
    assert unit.findtext('GSTREPUOM')=='PAC-PACKS'
    assert unit.findtext('DECIMALPLACES')=='3'


def test_legacy_transport_and_custom_uqc_label():
    unit=ET.fromstring('<UNIT><GSTREPUOM>XYZ-CUSTOM</GSTREPUOM></UNIT>')
    prepare_unit_create(unit,'Cases','XYZ-CUSTOM')
    assert unit.findtext('ORIGINALNAME')=='Case'
    assert unit.findtext('GSTREPUOM')=='XYZ-CUSTOM'
    assert unit_formal_name('Packs','Pack units','PAC-PACKS')=='Pack units'
    assert unit_formal_name('Packs','PAC')=='Pack'


@pytest.mark.parametrize('symbol',list(UNITS))
def test_all_catalog_units_receive_uqc_and_plain_distinct_formal_name(symbol):
    node=simple_unit(symbol,None,3,None)
    code=node.findtext('GSTREPUOM')
    formal=node.findtext('ORIGINALNAME')
    assert code and '-' in code
    assert '(selling' not in formal
    assert formal.casefold() not in {symbol.casefold(),code.casefold(),*(p.casefold() for p in code.split('-',1))}
    assert node.findtext('NAME')==symbol and node.findtext('DECIMALPLACES')=='3'


@pytest.mark.parametrize('old_code',[None,'Not Applicable','UNT-UNITS','OTH-OTHERS','PAC-PACKS'])
def test_missing_or_legacy_generic_pack_uqc_is_assigned(old_code):
    node=ET.Element('UNIT')
    if old_code:ET.SubElement(node,'GSTREPUOM').text=old_code
    prepare_unit_create(node,'Packs','Packs (selling unit)')
    assert node.findtext('GSTREPUOM')=='PAC-PACKS'
    assert node.findtext('ORIGINALNAME')=='Pack'


def test_custom_unit_uqc_is_not_fabricated():
    assert unit_uqc('Custom measures')=='OTH-OTHERS'
    assert unit_uqc('Custom measures','XYZ-CUSTOM')=='XYZ-CUSTOM'


@pytest.mark.parametrize('code',['PAC','pac','PAC-PACKS'])
def test_pack_short_code_is_expanded_for_tally(code):
    assert unit_uqc('Packs',code)=='PAC-PACKS'


def test_unknown_bare_code_cannot_leave_uqc_unassigned():
    assert unit_uqc('Custom size','unknown code')=='OTH-OTHERS'

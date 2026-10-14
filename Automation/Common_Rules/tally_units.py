"""Unit creation only, following Tally's official Simple Unit XML example.

https://help.tallysolutions.com/sample-xml/ (Units of Measure)
Exported UNIT NAME attributes are not part of the documented creation payload.
"""
import xml.etree.ElementTree as ET
from .unit_catalog import unit_formal_name


def unit_symbol(node):
    return node.findtext('NAME') or node.get('NAME') or ''


def prepare_unit_create(node,symbol,formal):
    """Normalize only a copied unit; never stock/voucher quantities or names."""
    node.attrib.clear()
    node.set('Action','Create')
    for tag,value in (('NAME',symbol),('ORIGINALNAME',formal)):
        child=node.find(tag)
        if child is None:child=ET.SubElement(node,tag)
        child.text=str(value)
    for tag in ('MAILINGNAME','ADDITIONALNAME'):
        for child in list(node.findall(tag)):node.remove(child)
    return node


def simple_unit(symbol,description,decimal_places,uqc):
    node=ET.Element('UNIT',{'Action':'Create'})
    for tag,value in (('NAME',symbol),('ISSIMPLEUNIT','Yes'),
                      ('ORIGINALNAME',unit_formal_name(symbol,description)),
                      ('DECIMALPLACES',decimal_places),('GSTREPUOM',uqc)):
        ET.SubElement(node,tag).text=str(value)
    return node

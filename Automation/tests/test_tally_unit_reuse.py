"""Existing and multi-folder units must not block otherwise valid imports."""
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
from Common_Rules.tally_import import prepare_units,send_plan
from Common_Rules.tally_xml import envelope,message,text


def unit(name,original,decimals=0):
    node=ET.Element('UNIT',{'NAME':name,'ACTION':'Create'})
    for tag,value in {'NAME':name,'ORIGINALNAME':original,'DECIMALPLACES':str(decimals),'ISSIMPLEUNIT':'Yes','GSTREPUOM':'UNT-UNITS'}.items():text(node,tag,value)
    return node


def xml(*units):
    document,data=envelope('','All Masters')
    for node in units:message(data).append(node)
    return ET.tostring(document)


def test_duplicate_symbol_across_folders_uses_max_precision_once():
    original=xml(unit('PCS','Pieces',0),unit('PCS','Pieces',3))
    combined,reused,renamed=prepare_units(original,[])
    nodes=ET.fromstring(combined).findall('.//UNIT')
    assert len(nodes)==1 and nodes[0].get('NAME')=='PCS'
    assert nodes[0].findtext('DECIMALPLACES')=='3'
    assert nodes[0].findtext('ORIGINALNAME')=='PCS'
    assert nodes[0].findtext('ADDITIONALNAME')=='Pieces'
    assert not reused and renamed==[{'unit':'PCS','original_name':'PCS','formal_name':'Pieces'}]
    assert len(ET.fromstring(original).findall('.//UNIT'))==2


def test_existing_symbols_reused_without_rewriting_tally_units():
    existing=unit('PCS','User custom description',4)
    original=ET.tostring(existing)
    prepared,reused,renamed=prepare_units(xml(unit('PCS','Pieces',0)),[existing])
    assert not ET.fromstring(prepared).findall('.//UNIT')
    assert reused==['PCS'] and not renamed
    assert ET.tostring(existing)==original


def test_duplicate_original_name_new_alias_retains_symbol_and_uqc():
    prepared,reused,renamed=prepare_units(xml(unit('KG','Kilograms',3),unit('KGS','Kilograms',3)),[])
    nodes=ET.fromstring(prepared).findall('.//UNIT')
    assert [n.get('NAME') for n in nodes]==['KG','KGS']
    assert [n.findtext('ORIGINALNAME') for n in nodes]==['KG','KGS']
    assert [n.findtext('ADDITIONALNAME') for n in nodes]==['Kilograms','Kilograms [unit KGS]']
    assert [n.findtext('GSTREPUOM') for n in nodes]==['UNT-UNITS','UNT-UNITS']
    assert len(renamed)==2


def test_existing_formal_name_collision_new_symbol_disambiguated():
    prepared,_,renamed=prepare_units(xml(unit('PCS','Pieces')),[unit('Pieces','Pieces')])
    assert ET.fromstring(prepared).findtext('.//ORIGINALNAME')=='PCS'
    assert ET.fromstring(prepared).findtext('.//ADDITIONALNAME')=='Pieces [unit PCS]'
    assert ET.fromstring(prepared).find('.//UNIT').get('NAME')=='PCS'


def test_insufficient_existing_precision_never_rounds_quantities():
    with pytest.raises(ValueError,match='Quantities were not rounded'):prepare_units(xml(unit('KG','Kilograms',3)),[unit('KG','Kilograms',0)])


def test_conflicting_simple_compound_type_not_silently_reused():
    existing=unit('PCS','Pieces');existing.find('ISSIMPLEUNIT').text='No'
    with pytest.raises(ValueError,match='simple/compound'):prepare_units(xml(unit('PCS','Pieces')),[existing])


def test_reused_units_skip_post_and_continue_masters_then_vouchers():
    sales,data=envelope('','Vouchers')
    voucher=ET.SubElement(message(data),'VOUCHER');text(voucher,'VOUCHERNUMBER','KEEP-1');text(voucher,'AMOUNT','123.45')
    original_sales=ET.tostring(sales)
    plan=[('Units.xml',xml(unit('PCS','Pieces'))),('Masters.xml',xml()),('Sales_Vouchers.xml',original_sales)]
    posts=[];read_targets=[]
    def transport(payload):
        root=ET.fromstring(payload)
        if root.findtext('./HEADER/TALLYREQUEST')=='Export':
            if root.findtext('./HEADER/ID')=='InvoiceReaderUnits':
                read_targets.append(root.findtext('.//SVCURRENTCOMPANY'))
                return b'<ENVELOPE><COLLECTION><UNIT NAME="PCS"><ORIGINALNAME>Existing pieces</ORIGINALNAME><ISSIMPLEUNIT>Yes</ISSIMPLEUNIT><DECIMALPLACES>0</DECIMALPLACES></UNIT></COLLECTION></ENVELOPE>'
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(payload)
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    results=send_plan(plan,'Chosen',transport)
    assert results[0]['skipped'] and results[0]['existing_units_reused']==['PCS']
    assert len(posts)==2 and read_targets==['Chosen']
    assert ET.fromstring(posts[-1]).findtext('.//VOUCHERNUMBER')=='KEEP-1'
    assert ET.fromstring(posts[-1]).findtext('.//AMOUNT')=='123.45'
    assert plan[-1][1]==original_sales


def test_duplicate_original_error_still_stops_if_not_resolved():
    def transport(payload):
        root=ET.fromstring(payload)
        if root.findtext('./HEADER/TALLYREQUEST')=='Export':
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        return b'<RESPONSE><CREATED>0</CREATED><ALTERED>3</ALTERED><ERRORS>0</ERRORS><LINEERROR>DUPLICATE ORIGINAL NAME</LINEERROR></RESPONSE>'
    result=send_plan([('Units.xml',xml(unit('PCS','Pieces'))),('Masters.xml',xml())],'Chosen',transport)
    assert len(result)==1 and result[0]['errors']==['Unit PCS: DUPLICATE ORIGINAL NAME']
    assert result[0]['attempted_units']==['PCS']
    assert 'DUPLICATE ORIGINAL NAME' in result[0]['unit_results'][0]['response_xml']


def test_legacy_descriptive_original_names_fixed_before_tally_post():
    # Same situation as the screenshot: three already-existing symbols, plus
    # a new symbol whose legacy XML incorrectly used a description as identity.
    source=xml(unit('PCS','Pieces'),unit('REAM','Reams'),unit('ROLL','Rolls'),unit('Nos','Numbers'))
    existing=b'<ENVELOPE><COLLECTION>'+b''.join(ET.tostring(unit(n,n)) for n in ('PCS','REAM','ROLL'))+b'</COLLECTION></ENVELOPE>'
    posted=[]
    def transport(payload):
        root=ET.fromstring(payload)
        if root.findtext('./HEADER/TALLYREQUEST')=='Export':
            if root.findtext('./HEADER/ID')=='InvoiceReaderUnits':return existing
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posted.append(root)
        node=root.find('.//UNIT')
        if node is not None:
            assert node.get('NAME')==node.findtext('ORIGINALNAME')=='Nos'
            assert node.findtext('ADDITIONALNAME')=='Numbers'
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    result=send_plan([('Units.xml',source),('Masters.xml',xml())],'Chosen',transport)
    assert not any(r['errors'] for r in result)
    assert result[0]['existing_units_reused']==['PCS','REAM','ROLL']
    assert result[0]['attempted_units']==['Nos']
    assert len(posted)==2
    assert ET.fromstring(source).find(".//UNIT[@NAME='Nos']/ORIGINALNAME").text=='Numbers'


def test_failure_diagnostic_names_exact_unit_and_preserves_earlier_counters():
    posted=[]
    def transport(payload):
        root=ET.fromstring(payload)
        if root.findtext('./HEADER/TALLYREQUEST')=='Export':return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posted.append(root.find('.//UNIT').get('NAME'))
        if len(posted)==1:return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
        return b'<RESPONSE><CREATED>0</CREATED><ERRORS>0</ERRORS><LINEERROR>DUPLICATE ORIGINAL NAME</LINEERROR></RESPONSE>'
    result=send_plan([('Units.xml',xml(unit('PCS','Pieces'),unit('Units','Units'))),('Masters.xml',xml())],'Chosen',transport)
    assert len(result)==1 and result[0]['counts']['CREATED']==1
    assert result[0]['errors']==['Unit Units: DUPLICATE ORIGINAL NAME']
    assert posted==['PCS','Units']
    assert result[0]['unit_results'][1]['unit']=='Units'


def test_many_folder_definitions_create_each_symbol_once():
    source=xml(*(unit('PCS','Pieces',i%4) for i in range(16)))
    merged,_,_=prepare_units(source,[])
    units=ET.fromstring(merged).findall('.//UNIT')
    assert len(units)==1 and units[0].findtext('DECIMALPLACES')=='3'
    assert units[0].findtext('ORIGINALNAME')=='PCS'


@pytest.mark.parametrize('symbol',['Packs','Units','Vials','Tubes','Liters'])
def test_formal_name_equal_to_symbol_is_removed_without_changing_symbol(symbol):
    node=unit(symbol,symbol,3);text(node,'ADDITIONALNAME',symbol)
    source=xml(node);prepared,_,adjusted=prepare_units(source,[])
    result=ET.fromstring(prepared).find('.//UNIT')
    assert result.get('NAME')==result.findtext('NAME')==result.findtext('ORIGINALNAME')==symbol
    assert result.find('ADDITIONALNAME') is None
    assert result.findtext('DECIMALPLACES')=='3'
    assert ET.fromstring(source).findtext('.//ADDITIONALNAME')==symbol
    assert adjusted==[{'unit':symbol,'original_name':symbol,'formal_name':''}]


def test_packs_conflict_repair_reaches_masters_and_vouchers_with_same_values():
    packs=unit('Packs','Packs');text(packs,'ADDITIONALNAME','Packs')
    source=xml(unit('PCS','PCS'),unit('REAM','REAM'),unit('ROLL','ROLL'),packs)
    sales,data=envelope('','Vouchers');v=ET.SubElement(message(data),'VOUCHER')
    for tag,value in {'GUID':'keep-guid','DATE':'20261014','PARTYLEDGERNAME':'Keep buyer',
                      'ACTUALQTY':'17 Packs','BILLEDQTY':'17 Packs','RATE':'12.345/Packs','AMOUNT':'209.87'}.items():text(v,tag,value)
    saved=ET.tostring(sales);posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            if doc.findtext('./HEADER/ID')=='InvoiceReaderUnits':
                return b'<ENVELOPE><COLLECTION>'+b''.join(ET.tostring(unit(n,n)) for n in ('PCS','REAM','ROLL'))+b'</COLLECTION></ENVELOPE>'
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(doc);node=doc.find('.//UNIT')
        if node is not None and node.findtext('ADDITIONALNAME')==node.findtext('ORIGINALNAME'):
            return b'<RESPONSE><CREATED>0</CREATED><ERRORS>0</ERRORS><LINEERROR>DUPLICATE ORIGINAL NAME</LINEERROR></RESPONSE>'
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    results=send_plan([('Units.xml',source),('Masters.xml',xml()),('Sales_Vouchers.xml',saved)],'Chosen',transport)
    assert len(results)==3 and not any(r['errors'] for r in results)
    assert results[0]['existing_units_reused']==['PCS','REAM','ROLL']
    assert results[0]['attempted_units']==['Packs']
    assert len(results[0]['existing_unit_definitions'])==3
    assert [doc.findtext('.//REPORTNAME') for doc in posts]==['All Masters','All Masters','Vouchers']
    assert ET.tostring(posts[-1].find('.//VOUCHER'))==ET.tostring(ET.fromstring(saved).find('.//VOUCHER'))
    assert ET.fromstring(source).find(".//UNIT[@NAME='Packs']/ADDITIONALNAME").text=='Packs'

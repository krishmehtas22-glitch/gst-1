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
    assert nodes[0].findtext('ORIGINALNAME')=='Pieces'
    assert nodes[0].find('ADDITIONALNAME') is None
    assert nodes[0].findtext('MAILINGNAME')=='Pieces'
    assert not reused and renamed==[{'unit':'PCS','original_name':'Pieces','formal_name':'Pieces'}]
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
    assert [n.findtext('ORIGINALNAME') for n in nodes]==['Kilograms','Kilograms [unit KGS]']
    assert [n.findtext('MAILINGNAME') for n in nodes]==['Kilograms','Kilograms [unit KGS]']
    assert [n.findtext('GSTREPUOM') for n in nodes]==['UNT-UNITS','UNT-UNITS']
    assert len(renamed)==2


def test_existing_formal_name_collision_new_symbol_disambiguated():
    prepared,_,renamed=prepare_units(xml(unit('PCS','Pieces')),[unit('Pieces','Pieces')])
    assert ET.fromstring(prepared).findtext('.//ORIGINALNAME')=='Pieces [unit PCS]'
    assert ET.fromstring(prepared).findtext('.//MAILINGNAME')=='Pieces [unit PCS]'
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


def test_native_descriptive_original_names_preserved_before_tally_post():
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
            assert node.get('NAME')==node.findtext('NAME')=='Nos'
            assert node.findtext('ORIGINALNAME')=='Numbers'
            assert node.findtext('MAILINGNAME')=='Numbers'
            assert node.find('ADDITIONALNAME') is None
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
    assert units[0].findtext('ORIGINALNAME')=='Pieces'
    assert units[0].get('NAME')=='PCS'


@pytest.mark.parametrize('symbol',['Packs','Units','Vials','Tubes','Liters'])
def test_formal_name_equal_to_symbol_is_replaced_without_changing_symbol(symbol):
    node=unit(symbol,symbol,3);text(node,'ADDITIONALNAME',symbol)
    source=xml(node);prepared,_,adjusted=prepare_units(source,[])
    result=ET.fromstring(prepared).find('.//UNIT')
    assert result.get('NAME')==result.findtext('NAME')==symbol
    assert result.findtext('ORIGINALNAME')==symbol+' (selling unit)'
    assert result.find('ADDITIONALNAME') is None
    assert result.findtext('MAILINGNAME')==symbol+' (selling unit)'
    assert result.findtext('DECIMALPLACES')=='3'
    assert ET.fromstring(source).findtext('.//ADDITIONALNAME')==symbol
    assert adjusted==[{'unit':symbol,'original_name':symbol+' (selling unit)','formal_name':symbol+' (selling unit)'}]


@pytest.mark.parametrize('explicit_formal',[False,True])
def test_packs_conflict_repair_reaches_masters_and_vouchers_with_same_values(explicit_formal):
    packs=unit('Packs','Packs')
    if explicit_formal:text(packs,'ADDITIONALNAME','Packs')
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
        if node is not None and node.findtext('NAME')==node.findtext('ORIGINALNAME'):
            return b'<RESPONSE><CREATED>0</CREATED><ERRORS>0</ERRORS><LINEERROR>DUPLICATE ORIGINAL NAME</LINEERROR></RESPONSE>'
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    results=send_plan([('Units.xml',source),('Masters.xml',xml()),('Sales_Vouchers.xml',saved)],'Chosen',transport)
    assert len(results)==3 and not any(r['errors'] for r in results)
    assert results[0]['existing_units_reused']==['PCS','REAM','ROLL']
    assert results[0]['attempted_units']==['Packs']
    assert len(results[0]['existing_unit_definitions'])==3
    assert [doc.findtext('.//REPORTNAME') for doc in posts]==['All Masters','All Masters','Vouchers']
    assert ET.tostring(posts[-1].find('.//VOUCHER'))==ET.tostring(ET.fromstring(saved).find('.//VOUCHER'))
    assert ET.fromstring(source).findtext(".//UNIT[@NAME='Packs']/ADDITIONALNAME")==('Packs' if explicit_formal else None)


def test_explicit_existing_units_mode_sends_unchanged_masters_then_sales_without_unit_write():
    from Common_Rules.tally_import import company_payload
    masters,data=envelope('','All Masters');stock=ET.SubElement(message(data),'STOCKITEM',{'NAME':'Keep stock'})
    text(stock,'BASEUNITS','Packs')
    sales,data=envelope('','Vouchers');v=ET.SubElement(message(data),'VOUCHER')
    for tag,value in {'GUID':'keep-id','DATE':'20261014','PARTYLEDGERNAME':'Keep buyer','ACTUALQTY':'76 Packs','RATE':'1.234/Packs','AMOUNT':'93.78'}.items():text(v,tag,value)
    plan=[('Units.xml',xml(unit('Packs','Packs'))),('Masters.xml',ET.tostring(masters)),('Sales_Vouchers.xml',ET.tostring(sales))]
    before=list(plan);posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            assert doc.findtext('./HEADER/ID')=='InvoiceReaderCompanies'
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        assert doc.find('.//UNIT') is None
        posts.append(payload)
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    result=send_plan(plan,'Chosen',transport,units_already_available=True)
    assert result[0]['skipped'] and result[0]['counts']=={} and result[0]['errors']==[]
    assert 'Explicit masters-and-vouchers-only' in result[0]['reason']
    assert posts==[company_payload(data,'Chosen') for name,data in plan if name!='Units.xml']
    assert plan==before and len(result)==3


def test_existing_units_mode_does_not_ignore_master_failure_or_resend_vouchers():
    posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(doc.findtext('.//REPORTNAME'))
        return b'<RESPONSE><CREATED>0</CREATED><ERRORS>1</ERRORS><LINEERROR>Unit Packs is missing</LINEERROR></RESPONSE>'
    sales,_=envelope('','Vouchers')
    result=send_plan([('Units.xml',xml(unit('Packs','Packs'))),('Masters.xml',xml()),('Sales_Vouchers.xml',ET.tostring(sales))],'Chosen',transport,units_already_available=True)
    assert posts==['All Masters'] and len(result)==2
    assert result[-1]['errors']==['Unit Packs is missing']


def test_import_all_continues_after_reported_unit_and_master_errors_and_sends_all_50_vouchers():
    from Common_Rules.tally_import import company_payload
    source=xml(unit('PCS','Pieces'),unit('Packs','Packs'),unit('BOX','Boxes'))
    masters,data=envelope('','All Masters');stock=ET.SubElement(message(data),'STOCKITEM',{'NAME':'Keep stock'})
    text(stock,'BASEUNITS','Packs')
    sales,data=envelope('','Vouchers')
    for index in range(50):
        voucher=ET.SubElement(message(data),'VOUCHER')
        for tag,value in {'GUID':'keep-'+str(index),'DATE':'20261014','PARTYLEDGERNAME':'Keep buyer',
                          'STOCKITEMNAME':'Keep stock','ACTUALQTY':str(index+1)+' Packs','RATE':'1.234/Packs','AMOUNT':'100.00'}.items():text(voucher,tag,value)
    plan=[('Units.xml',source),('Masters.xml',ET.tostring(masters)),('Sales_Vouchers.xml',ET.tostring(sales))]
    original=list(plan);posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            if doc.findtext('./HEADER/ID')=='InvoiceReaderUnits':return b'<ENVELOPE><COLLECTION>'+ET.tostring(unit('PCS','PCS'))+b'</COLLECTION></ENVELOPE>'
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(payload);node=doc.find('.//UNIT')
        if node is not None:
            if node.get('NAME')=='Packs':return b'<RESPONSE><CREATED>0</CREATED><ERRORS>0</ERRORS><LINEERROR>DUPLICATE ORIGINAL NAME</LINEERROR></RESPONSE>'
            return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
        if doc.find('.//STOCKITEM') is not None:return b"<RESPONSE><CREATED>1</CREATED><ALTERED>78</ALTERED><ERRORS>0</ERRORS><LINEERROR>Unit 'Packs' does not exist!</LINEERROR></RESPONSE>"
        assert len(doc.findall('.//VOUCHER'))==50
        return b'<RESPONSE><CREATED>38</CREATED><ERRORS>12</ERRORS><LINEERROR>Stock item missing</LINEERROR></RESPONSE>'
    results=send_plan(plan,'Chosen',transport,submit_all=True)
    assert [r['file'] for r in results]==['Units.xml','Masters.xml','Sales_Vouchers.xml']
    assert results[0]['attempted_units']==['Packs','BOX'] and results[0]['counts']['CREATED']==1
    assert results[0]['errors']==['Unit Packs: DUPLICATE ORIGINAL NAME']
    assert results[1]['errors']==["Unit 'Packs' does not exist!"] and results[1]['counts']['ALTERED']==78
    assert results[2]['requested_vouchers']==50 and results[2]['counts']['CREATED']==38 and results[2]['counts']['ERRORS']==12
    assert len(posts)==4 and results[2]['errors']==['Stock item missing']
    assert posts[-2:]==[company_payload(data,'Chosen') for name,data in plan if name!='Units.xml']
    assert results[1]['request_xml'].encode()==posts[-2] and results[2]['request_xml'].encode()==posts[-1]
    assert results[2]['response_xml'].startswith('<RESPONSE>') and plan==original


@pytest.mark.parametrize('failure',[b'<html>unreadable</html>',b'<RESPONSE><STATUS>0</STATUS></RESPONSE>'])
def test_import_all_still_stops_unknown_responses_without_retry(failure):
    posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(payload);return failure
    sales,_=envelope('','Vouchers')
    result=send_plan([('Units.xml',xml(unit('Packs','Packs'))),('Masters.xml',xml()),('Sales_Vouchers.xml',ET.tostring(sales))],'Chosen',transport,submit_all=True)
    assert len(posts)==1 and len(result)==1 and result[0]['status']=='unknown'


def test_import_all_stops_after_master_timeout_preserves_unit_counts_and_attempted_request():
    posts=[]
    def transport(payload):
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(payload)
        if doc.find('.//UNIT') is None:raise OSError('Response lost after master request')
        return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS></RESPONSE>'
    sales,_=envelope('','Vouchers')
    result=send_plan([('Units.xml',xml(unit('Packs','Packs'))),('Masters.xml',xml()),('Sales_Vouchers.xml',ET.tostring(sales))],'Chosen',transport,submit_all=True)
    assert len(posts)==len(result)==2 and result[0]['counts']['CREATED']==1
    assert result[1]['status']=='unknown' and result[1]['request_attempted']
    assert result[1]['request_xml'].encode()==posts[1]


def test_real_native_export_schema_repairs_legacy_packs_request_and_imports_all_three():
    from Common_Rules.tally_import import loaded_units,company_payload
    native=(Path(__file__).parent/'fixtures/tally_native_units.xml').read_bytes()
    packs=unit('Packs','Packs');text(packs,'ADDITIONALNAME','Packs (selling unit)')
    source=xml(unit('PCS','PCS'),unit('REAM','REAM'),packs,unit('ROLL','ROLL'))
    masters,data=envelope('','All Masters');stock=ET.SubElement(message(data),'STOCKITEM',{'NAME':'File folder pack'})
    text(stock,'BASEUNITS','Packs')
    sales,data=envelope('','Vouchers')
    for index in range(50):
        v=ET.SubElement(message(data),'VOUCHER')
        for tag,value in {'GUID':'native-'+str(index),'DATE':'20261014','PARTYLEDGERNAME':'Buyer',
                          'STOCKITEMNAME':'File folder pack','ACTUALQTY':'76 Packs','RATE':'5.25/Packs','AMOUNT':'399.00'}.items():text(v,tag,value)
    plan=[('Units.xml',source),('Masters.xml',ET.tostring(masters)),('Sales_Vouchers.xml',ET.tostring(sales))]
    originals=list(plan);posts=[];accepted=False
    def transport(payload):
        nonlocal accepted
        doc=ET.fromstring(payload)
        if doc.findtext('./HEADER/TALLYREQUEST')=='Export':
            if doc.findtext('./HEADER/ID')=='InvoiceReaderUnits':
                assert 'MailingName' in doc.findtext('.//FETCH')
                return native
            return b'<ENVELOPE><COLLECTION><COMPANY NAME="Chosen"/></COLLECTION></ENVELOPE>'
        posts.append(payload);node=doc.find('.//UNIT')
        if node is not None:
            # Enforce the actual server-exported schema, not the previous guess.
            assert node.get('NAME')==node.findtext('NAME')=='Packs'
            assert node.findtext('ORIGINALNAME')==node.findtext('MAILINGNAME')=='Packs (selling unit)'
            assert node.find('ADDITIONALNAME') is None
            assert node.findtext('GSTREPUOM')=='UNT-UNITS' and node.findtext('DECIMALPLACES')=='0'
            accepted=True
            return b'<RESPONSE><CREATED>1</CREATED><ERRORS>0</ERRORS><EXCEPTIONS>0</EXCEPTIONS></RESPONSE>'
        assert accepted
        return b'<RESPONSE><CREATED>50</CREATED><ERRORS>0</ERRORS><EXCEPTIONS>0</EXCEPTIONS></RESPONSE>'
    fetched=loaded_units('Chosen',transport)
    assert len(fetched)==7 and all(n.get('NAME') for n in fetched)
    result=send_plan(plan,'Chosen',transport,submit_all=True)
    assert [r['file'] for r in result]==['Units.xml','Masters.xml','Sales_Vouchers.xml']
    assert result[0]['existing_units_reused']==['PCS','REAM','ROLL']
    assert result[0]['attempted_units']==['Packs'] and result[0]['counts']['CREATED']==1
    assert not any(r['errors'] or r['counts']['EXCEPTIONS'] for r in result)
    assert result[-1]['requested_vouchers']==50
    assert posts[1:]==[company_payload(data,'Chosen') for name,data in plan if name!='Units.xml']
    assert plan==originals


def test_exception_counter_is_reported_even_without_lineerror_or_error_count():
    from Common_Rules.tally_import import import_reply
    counts,errors=import_reply(b'<RESPONSE><CREATED>0</CREATED><ERRORS>0</ERRORS><EXCEPTIONS>1</EXCEPTIONS></RESPONSE>')
    assert counts['EXCEPTIONS']==1 and counts['ERRORS']==0 and errors==[]

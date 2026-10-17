"""Exact quantity -> unit, inventory and batch XML; no live Tally writes."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib,json,zipfile,types
import xml.etree.ElementTree as ET
import pytest
from test_review_voucher_structure import record
from Common_Rules.tally_review_export import export_all
from Common_Rules.quantity_precision import decimal_places


def row(root,qty='2.4877',symbol='KG'):
    result=record(root);inv=result['invoice'];inv['items']=inv['items'][:1]
    value=format((Decimal(qty)*Decimal('1000000')).quantize(Decimal('.01')),'f')
    inv['items'][0].update(unit=symbol,quantity=qty,rate='1000000',value=value,cgst_rate='0',sgst_rate='0',igst_rate='0')
    inv.update(classification='exempt',taxable=value,total=value,cgst='0',sgst='0',igst='0',round_off='0')
    return result


@pytest.mark.parametrize('qty',['2.4877','0.000001','1.234567','2.487700','0.010000','10','10.00000000'])
@pytest.mark.parametrize('symbol',['KG','LTR','metre','PCS'])
def test_exact_quantities_survive_inventory_and_batch_xml(tmp_path,qty,symbol):
    source=row(tmp_path,qty,symbol);original=deepcopy(source['invoice'])
    export_all(tmp_path,[source],False);folder=Path(source['output_path'])
    doc=ET.parse(folder/'Sales_Vouchers.xml');units=ET.parse(folder/'Units.xml')
    for node in doc.iter():
        if node.tag in ('ACTUALQTY','BILLEDQTY'):assert node.text==qty+' '+symbol
    assert int(units.findtext('.//DECIMALPLACES'))>=decimal_places(qty)
    assert source['invoice']==original
    assert Decimal(doc.findtext('.//ALLINVENTORYENTRIES.LIST/AMOUNT'))==Decimal(original['total'])


def test_shared_unit_uses_maximum_precision_across_all_rows(tmp_path):
    source=row(tmp_path,'2')
    source['invoice']['items'].append({**source['invoice']['items'][0],'name':'Another item','quantity':'2.4877','rate':'1000000','value':'2487700'})
    source['invoice'].update(taxable='4487700',total='4487700')
    export_all(tmp_path,[source],False)
    assert ET.parse(Path(source['output_path'])/'Units.xml').findtext('.//DECIMALPLACES')=='4'


def test_insufficient_imported_unit_precision_never_removes_fractional_dependency(tmp_path):
    from test_tally_master_matching import snapshot,choice
    from Common_Rules.tally_master_matching import bind_snapshot,context,save_choices
    from Tally_Master_Snapshot import save_snapshot
    source=row(tmp_path,'2');inv=source['invoice']
    inv['items'].append({**inv['items'][0],'name':'Other item','quantity':'2.4877','value':'2487700'})
    inv.update(taxable='4487700',total='4487700')
    data,_=snapshot(tmp_path)
    # Exact symbol KG exists in Tally, but supports integers only. First row's
    # match must not cause the second row's fractional KG definition to vanish.
    raw='<ENVELOPE><COLLECTION><UNIT NAME="KG"><ISSIMPLEUNIT>Yes</ISSIMPLEUNIT><GSTREPUOM>KGS-KILOGRAMS</GSTREPUOM><DECIMALPLACES>0</DECIMALPLACES></UNIT></COLLECTION></ENVELOPE>'
    from Tally_Master_Snapshot import parse_collection
    data['units']=parse_collection(raw,'units');bind_snapshot(tmp_path,'Client',save_snapshot(tmp_path,data))
    ctx=context(tmp_path,source)
    save_choices(tmp_path,source,ctx,inv,{'items':[{'index':0,'unit':choice('U0')}]})
    with pytest.raises(ValueError,match='KG needs 4 decimal places'):export_all(tmp_path,[source],False)
    assert inv['items'][1]['quantity']=='2.4877'


def test_compatible_imported_unit_preserves_four_decimal_quantity(tmp_path):
    from test_tally_master_matching import setup,choices
    from Common_Rules.tally_master_matching import save_choices,bind_snapshot,context
    from Tally_Master_Snapshot import save_snapshot,parse_collection
    source,ctx=setup(tmp_path);inv=source['invoice'];inv['items'][0]['quantity']='2.4877'
    data=deepcopy(ctx['data'])
    data['units']=parse_collection('<ENVELOPE><COLLECTION><UNIT NAME="Number"><ISSIMPLEUNIT>Yes</ISSIMPLEUNIT><GSTREPUOM>NOS-NUMBERS</GSTREPUOM><DECIMALPLACES>4</DECIMALPLACES></UNIT></COLLECTION></ENVELOPE>','units')
    bind_snapshot(tmp_path,'Client',save_snapshot(tmp_path,data));ctx=context(tmp_path,source)
    save_choices(tmp_path,source,ctx,inv,choices());export_all(tmp_path,[source],False)
    assert ET.parse(Path(source['output_path'])/'Sales_Vouchers.xml').findtext('.//ALLINVENTORYENTRIES.LIST/ACTUALQTY')=='2.4877 Number'


@pytest.mark.parametrize('qty',['2.4877001','0.0000001'])
def test_beyond_supported_precision_holds_xml_without_rounding(tmp_path,qty):
    good=row(tmp_path);export_all(tmp_path,[good],False);folder=Path(good['output_path'])
    before={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    bad=row(tmp_path,qty)
    with pytest.raises(ValueError,match='at most 6'):export_all(tmp_path,[bad],False)
    assert bad['invoice']['items'][0]['quantity']==qty
    assert before=={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}


def test_currency_lock_and_precision_backup_chain():
    repo=Path(__file__).parents[2];change=json.loads((repo/'Automation/QUANTITY_PRECISION_CHANGE.json').read_text())
    duplicate=json.loads((repo/'Automation/DUPLICATE_WARNING_CHANGE.json').read_text())['files']
    for name,digest in change['currency_lock'].items():
        if name in duplicate:
            assert duplicate[name]['baseline_sha256']==digest
            assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==duplicate[name]['authorized_sha256']
        else:assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest
    with zipfile.ZipFile(repo/change['backup']) as z:
        for name,values in change['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==values['baseline_sha256']
            if name in duplicate:
                assert duplicate[name]['baseline_sha256']==values['authorized_sha256']
                assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==duplicate[name]['authorized_sha256']
            else:assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==values['authorized_sha256']


def test_ordinary_xml_identical_to_locked_currency_release(tmp_path):
    repo=Path(__file__).parents[2]
    with zipfile.ZipFile(repo/'Backups/Before_Quantity_Precision.zip') as z:code=z.read('Automation/Common_Rules/tally_review_export.py')
    old=types.ModuleType('Common_Rules._prior_quantity');old.__package__='Common_Rules';exec(compile(code,'old.py','exec'),old.__dict__)
    source=row(tmp_path);old.export_all(tmp_path,[source],False);folder=Path(source['output_path'])
    before={n:(folder/n).read_bytes() for n in ('Units.xml','Masters.xml','Sales_Vouchers.xml')}
    export_all(tmp_path,[source],False)
    assert before=={n:(folder/n).read_bytes() for n in before}

import pytest
from Common_Rules.extraction import parse_text


def source(style=1,number='INV-247',buyer='Buyer Business',export=False,exempt=False):
    masthead='Example Trade Supplies\n12 Industrial Estate, Mumbai\nGSTIN: 27AAAAA0000A1Z5'
    identity={1:'TAX INVOICE\nInvoice\n'+number+'\nDate\n10/10/2026',
              2:'TAX INVOICE\nInvoice reference\n'+number+'\nIssue date\n10/10/2026',
              3:'EXPORT INVOICE\n'+number+'\nInvoice date\n10/10/2026',
              4:'BILL OF SUPPLY                     Invoice: '+number+'\nDated: 10/10/2026',
              5:'INVOICE / '+number+'\nTAX INVOICE | 10/10/2026'}[style]
    country='United Arab Emirates' if export else ('Maharashtra' if style in (1,4) else 'Karnataka')
    meta='Seller state: Maharashtra (27)\nPlace of supply: '+country+'\nCurrency: INR'
    if style in (1,2,3):party='BUYER\n'+buyer+'\n'+buyer+', '+country+'\nGSTIN: '+('Foreign buyer - N/A' if export else '27BBBBB0000B1Z5')+'\nSUPPLY DETAILS\n'+meta
    else:
        party='BUYER                       SUPPLY DETAILS\n'+buyer+'                      Seller state: Maharashtra (27)\n'+buyer+', '+country+'                      Place of supply: '+country+'\nGSTIN: 27BBBBB0000B1Z5                      Currency: INR'
        if style==5:masthead='FROM                            PLACE OF SUPPLY\nExample Trade Supplies                    Karnataka\n12 Industrial Estate, Mumbai\nGSTIN 27AAAAA0000A1Z5'
    header=['Goods description','HSN','Qty','UOM','Rate','Taxable','GST %','GST amount']
    gst='0' if export or exempt else '18';tax='0.00' if gst=='0' else '18.00'
    row=['Steel tray','392610','2','PCS','50.00','100.00',gst,tax]
    table='\n'.join(header+row) if style<4 else '     '.join(header)+'\n'+'     '.join(row)
    if export:treatment='Export under LUT without payment of integrated tax. Destination: United Arab Emirates.';cgst=sgst=igst='0.00'
    elif exempt:treatment='Bill of Supply - exempt goods; no GST charged.';cgst=sgst=igst='0.00'
    elif style==1:treatment='Intra-state supply - CGST and SGST charged.';cgst=sgst='9.00';igst='0.00'
    else:treatment='Inter-state supply - IGST charged.';cgst=sgst='0.00';igst='18.00'
    total='100.00' if gst=='0' else '118.00'
    summary='Total value of goods\n100.00\nCGST\n'+cgst+'\nSGST\n'+sgst+'\nIGST\n'+igst+'\nTOTAL PAYABLE (INR)\n'+total
    destination='\nDispatch destination\nUnited Arab Emirates' if export else ''
    return masthead+'\n'+identity+destination+'\n'+party+'\n'+table+'\n'+summary+'\n'+treatment+'\nFor Example Trade Supplies\nAuthorised Signatory'


@pytest.mark.parametrize('style,export,exempt,supply',[(1,False,False,'INTRA'),(2,False,False,'INTER'),(3,True,False,'EXPORT'),(4,False,True,'EXEMPT'),(5,False,False,'INTER')])
def test_all_five_header_and_item_layouts_retain_printed_fields(style,export,exempt,supply):
    inv=parse_text(source(style,export=export,exempt=exempt))
    assert inv['number']=='INV-247' and inv['date']=='2026-10-10'
    assert inv['buyer_name']=='Buyer Business' and inv['seller_name']=='Example Trade Supplies'
    assert inv['total']==('100.00' if export or exempt else '118.00')
    assert inv['taxable']=='100.00' and inv['supply']==supply
    item=inv['items'][0]
    assert (item['quantity'],item['unit'],item['rate'],item['value'])==('2','PCS','50.00','100.00')
    assert inv['extraction_warnings']==[]
    assert inv['place_of_supply']==('Outside India' if export else '27' if style in (1,4) else '29')


def test_supply_heading_is_not_a_buyer_name():
    inv=parse_text(source(4,exempt=True))
    assert inv['buyer_name']=='Buyer Business'
    assert not any('ambiguous buyer' in w.lower() for w in inv['extraction_warnings'])


def test_conflicting_party_evidence_still_requires_review():
    text=source(1).replace('BUYER\n','Buyer: Different Business\nBUYER\n')
    inv=parse_text(text)
    assert inv['buyer_name'] is None
    assert any('ambiguous buyer' in w.lower() for w in inv['extraction_warnings'])


def test_bad_or_incomplete_item_is_not_fabricated():
    text=source(1).replace('50.00\n100.00\n18\n18.00','missing\n100.00\n18\n18.00')
    inv=parse_text(text)
    assert inv['items']==[] and inv['extraction_warnings']


def test_missing_date_is_not_replaced_with_today():
    inv=parse_text(source(2).replace('10/10/2026','unknown'))
    assert not inv.get('date') and any('date' in w.lower() for w in inv['extraction_warnings'])


def test_house_number_under_tax_invoice_title_is_not_invoice_identifier():
    text=source(1).replace('Invoice\nINV-247\n','').replace('TAX INVOICE\n','TAX INVOICE\n12\n')
    inv=parse_text(text)
    assert not inv.get('number')
    assert any('invoice number' in w.lower() for w in inv['extraction_warnings'])

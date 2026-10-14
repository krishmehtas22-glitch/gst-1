from copy import deepcopy
import pytest

from Reading_V2.structured import parse_cii, agrees_with_visible_source


def cii(code='380', basis='1'):
    return f'''<CrossIndustryInvoice>
    <ExchangedDocument><ID>INV-123</ID><TypeCode>{code}</TypeCode>
    <IssueDateTime><DateTimeString format="102">20260603</DateTimeString></IssueDateTime></ExchangedDocument>
    <SupplyChainTradeTransaction><SellerTradeParty><Name>Supplier LLC</Name></SellerTradeParty>
    <BuyerTradeParty><Name>Buyer Ltd</Name></BuyerTradeParty>
    <InvoiceCurrencyCode>EUR</InvoiceCurrencyCode>
    <IncludedSupplyChainTradeLineItem><SpecifiedTradeProduct><Name>Steel</Name></SpecifiedTradeProduct>
    <NetPriceProductTradePrice><ChargeAmount>40.00</ChargeAmount><BasisQuantity>{basis}</BasisQuantity></NetPriceProductTradePrice>
    <BilledQuantity unitCode="KGM">2.375</BilledQuantity>
    <SpecifiedTradeSettlementLineMonetarySummation><LineTotalAmount>95.00</LineTotalAmount></SpecifiedTradeSettlementLineMonetarySummation>
    </IncludedSupplyChainTradeLineItem>
    <ApplicableTradeTax><TypeCode>VAT</TypeCode><CalculatedAmount>19.00</CalculatedAmount></ApplicableTradeTax>
    <SpecifiedTradeSettlementHeaderMonetarySummation><TaxBasisTotalAmount>95.00</TaxBasisTotalAmount>
    <GrandTotalAmount>114.00</GrandTotalAmount></SpecifiedTradeSettlementHeaderMonetarySummation>
    </SupplyChainTradeTransaction></CrossIndustryInvoice>'''.encode()


def test_structured_qty_precision_and_vat_are_preserved_without_gst_relabelling():
    result=parse_cii(cii());inv=result['invoice']
    assert inv['number']=='INV-123' and inv['date']=='2026-06-03'
    assert inv['items'][0]['quantity']=='2.375' and inv['items'][0]['unit']=='KG'
    assert inv['items'][0]['rate']=='40.00' and inv['total']=='114.00'
    assert not any(k in inv for k in ('cgst','sgst','igst'))
    assert inv['source_non_gst_taxes'][0]['CalculatedAmount']=='19.00'


def test_nonunit_price_basis_is_not_scaled_into_an_invented_rate():
    item=parse_cii(cii(basis='1000'))['invoice']['items'][0]
    assert item['quantity']=='2.375' and 'rate' not in item
    assert item['source_price_basis']=='1000' and item['source_price_amount']=='40.00'


def test_credit_note_is_not_silently_treated_as_sales():
    assert parse_cii(cii(code='381')) is None


def test_embedded_xml_rejects_external_entities():
    with pytest.raises(ValueError):parse_cii(b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]>'+cii())


def test_hidden_metadata_cannot_replace_different_visible_invoice():
    parsed=parse_cii(cii())
    tokens=[{'id':'p1w1','text':'OTHER-999','box':[.1,.1,.2,.2]}]
    source={'invoice':{'number':'OTHER-999'},'field_evidence':{'number':{'origin':'positioned_label'}},
            'document':{'pages':[{'number':1,'lines':[{'text':'OTHER-999','tokens':tokens}]}]}}
    assert {'number','date','total','seller_name','buyer_name'} <= set(agrees_with_visible_source(parsed,source))

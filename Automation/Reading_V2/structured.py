"""Read an invoice's own embedded CII data before resorting to OCR/AI.

This is a declared structured-input path, not a visual-extraction accuracy test.
Foreign VAT is retained as metadata, never relabelled as Indian GST.
"""
from datetime import datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from .reader import decimal, date_value, key, regional_numbers

UNECE_UNITS = {'C62': 'Units', 'H87': 'PCS', 'PCE': 'PCS', 'KGM': 'KG',
               'GRM': 'GMS', 'MTR': 'MTR', 'CMT': 'CM', 'MMT': 'MM',
               'LTR': 'LTR', 'MLT': 'ML', 'TNE': 'TON', 'MTK': 'SQM',
               'MTQ': 'CBM', 'SET': 'SET', 'PR': 'PRS', 'PK': 'Packs'}


def local(node):
    return node.tag.split('}')[-1]


def first(parent, name):
    return next((n for n in parent.iter() if local(n) == name), None) if parent is not None else None


def value(parent, name):
    node = first(parent, name)
    return node.text.strip() if node is not None and node.text else None


def address(party):
    node = first(party, 'PostalTradeAddress')
    if node is None:
        return None
    return ', '.join(filter(None, [value(node, tag) for tag in
                    ('LineOne', 'LineTwo', 'LineThree', 'CityName', 'PostcodeCode', 'CountryID')]))


def parse_cii(data):
    if len(data) > 2*1024*1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Embedded invoice XML exceeds limits or contains a DTD/entity')
    root = ET.fromstring(data)
    if local(root) not in ('CrossIndustryInvoice', 'CrossIndustryDocument'):
        return None
    header = first(root, 'ExchangedDocument')
    if header is None:
        header = first(root, 'HeaderExchangedDocument')
    if header is None or value(header, 'TypeCode') != '380':
        return None  # Credit notes/corrections are not silently converted to Sales.
    dates = first(header, 'IssueDateTime')
    date = value(dates, 'DateTimeString')
    if not date or not re.fullmatch(r'\d{8}', date):
        raise ValueError('Unsupported embedded invoice date')
    date = datetime.strptime(date, '%Y%m%d').date().isoformat()
    seller, buyer = first(root, 'SellerTradeParty'), first(root, 'BuyerTradeParty')
    sums = first(root, 'SpecifiedTradeSettlementHeaderMonetarySummation')
    if sums is None:
        sums = first(root, 'SpecifiedTradeSettlementMonetarySummation')
    invoice = {'number': value(header, 'ID'), 'date': date,
               'seller_name': value(seller, 'Name'), 'buyer_name': value(buyer, 'Name'),
               'seller_address': address(seller), 'buyer_address': address(buyer),
               'buyer_country': value(first(buyer, 'PostalTradeAddress'), 'CountryID'),
               'currency': value(root, 'InvoiceCurrencyCode'),
               'total': value(sums, 'GrandTotalAmount'), 'items': []}
    # TaxBasisTotal includes header allowances/charges, unlike LineTotalAmount.
    invoice['taxable'] = value(sums, 'TaxBasisTotalAmount')
    if not invoice.get('number') or decimal(invoice['total']) is None:
        raise ValueError('Embedded invoice identifier/total is missing or invalid')
    notes = ['Embedded CII input used; visual/structured agreement and tax treatment still require review.']
    for line in root.iter():
        if local(line) != 'IncludedSupplyChainTradeLineItem':
            continue
        qty = first(line, 'BilledQuantity')
        net = first(line, 'NetPriceProductTradePrice')
        basis = value(net, 'BasisQuantity')
        unit_code = qty.get('unitCode') if qty is not None else None
        item = {'name': value(first(line, 'SpecifiedTradeProduct'), 'Name'),
                'quantity': qty.text.strip() if qty is not None and qty.text else None,
                'value': value(first(line, 'SpecifiedTradeSettlementLineMonetarySummation'), 'LineTotalAmount')}
        if net is not None and basis in (None, '1', '1.0', '1.00', '1.0000'):
            item['rate'] = value(net, 'ChargeAmount')
        elif net is not None:
            notes.append('Non-unit price basis retained; unit rate was not invented or quantity scaled.')
            item['source_price_basis'] = basis
            item['source_price_amount'] = value(net, 'ChargeAmount')
        if unit_code:
            item.update(unit=UNECE_UNITS.get(unit_code, unit_code), unit_origin='structured',
                        unit_basis='embedded', source_unece_unit=unit_code,
                        unit_reason='Unit declared in embedded invoice XML; no quantity conversion.')
        for field in ('quantity', 'rate', 'value'):
            if item.get(field) is not None and decimal(item[field]) is None:
                raise ValueError('Invalid structured line quantity/amount')
        invoice['items'].append({k:v for k,v in item.items() if v is not None})
    invoice['source_non_gst_taxes'] = []
    for tax in root.iter():
        if local(tax) == 'ApplicableTradeTax':
            invoice['source_non_gst_taxes'].append({name: value(tax, name) for name in
                    ('TypeCode', 'CategoryCode', 'RateApplicablePercent', 'CalculatedAmount')})
    if invoice['source_non_gst_taxes']:
        notes.append('Embedded VAT/tax metadata retained separately; not mapped to CGST/SGST/IGST.')
    return {'invoice': {k:v for k,v in invoice.items() if v is not None}, 'warnings': notes,
            'source_kind': 'embedded_cii', 'visual_accuracy_measured': False}


def read_embedded(path):
    candidates = []
    reader = PdfReader(Path(path))
    for name, blobs in reader.attachments.items():
        if not name.lower().endswith('.xml'):
            continue
        for blob in blobs:
            parsed = parse_cii(blob)
            if parsed:
                parsed['attachment_name'] = name
                candidates.append(parsed)
    if not candidates:
        return None
    identities = {(p['invoice'].get('number'), p['invoice'].get('date'),
                   p['invoice'].get('total')) for p in candidates}
    if len(identities) != 1:
        raise ValueError('Conflicting embedded invoices; explicit document grouping is required')
    if len(candidates) > 1:
        raise ValueError('Multiple embedded invoice versions; no automatic preference was selected')
    return candidates[0]


def agrees_with_visible_source(parsed, result):
    """Some public 'schema-correct' PDFs embed a different example invoice.

    Never let that hidden attachment silently replace the visible invoice.
    Absence of proof also requires review, rather than an assumed agreement.
    """
    invoice = parsed['invoice']
    locale = regional_numbers(result['document'])
    disagreements = []
    for field in ('number', 'date', 'total', 'seller_name', 'buyer_name'):
        proposed = invoice.get(field)
        if not proposed:
            if field in {'number', 'date', 'total'}:
                disagreements.append(field)
            continue
        existing = result.get('field_evidence', {}).get(field)
        observed = result['invoice'].get(field)
        if existing and existing['origin'] == 'positioned_label' and observed:
            if field == 'total':
                equal = decimal(observed) == decimal(proposed)
            elif field == 'date':
                equal = date_value(str(observed)) == proposed
            else:
                equal = key(observed) == key(proposed)
            if not equal:
                disagreements.append(field)
                continue
        found = False
        for page in result['document']['pages']:
            for line in page['lines']:
                words = line['tokens']
                for start in range(len(words)):
                    for end in range(start+1, min(len(words)+1, start+12)):
                        raw = ' '.join(t['text'] for t in words[start:end])
                        if field == 'total':
                            match = decimal(raw, locale) == decimal(proposed)
                        elif field == 'date':
                            match = date_value(raw) == proposed
                        else:
                            match = key(raw) == key(proposed)
                        if match:
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if not found:
            disagreements.append(field)
    return disagreements

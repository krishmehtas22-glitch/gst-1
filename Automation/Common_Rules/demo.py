"""Explicit, auditable substitutions for marked synthetic test documents only."""
from copy import deepcopy
import re

from .accounting import TAXES, EXPORT_MODES, gstin_valid, money, state_code


def test_gstin(base):
    """A checksum-valid test identifier does not establish GST registration."""
    if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z', base):
        raise ValueError('Synthetic GSTIN base has an unsupported format')
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for index, char in enumerate(base):
        product = alphabet.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    result = base + alphabet[(36 - total % 36) % 36]
    if not gstin_valid(result):
        raise ValueError('Synthetic GSTIN needs a supported Indian state')
    return result


def prepare_demo_invoice(raw, config):
    if raw.get('source_layout') in ('paired_columns_v1','section_panels_v1','supplier_mapping_v1'):
        return prepare_paired_demo(raw, config)
    if config['demo_profile'].get('version') != 1:
        raise ValueError('This seller-specific demo configuration requires the paired seller/buyer layout')
    profile = config['demo_profile']
    if raw.get('dummy_document') is not True:
        raise ValueError('Demo mode accepts only PDFs explicitly marked as synthetic dummy documents')
    if raw.get('extraction_warnings'):
        raise ValueError('Ambiguous extraction must be reviewed before demo substitutions')
    if raw.get('seller_gstin') != 'NOT ASSIGNED':
        raise ValueError('This demo profile requires the printed seller GSTIN to be NOT ASSIGNED')
    if state_code(raw.get('seller_state', '')) != profile['seller_state']:
        raise ValueError('Printed seller state does not match the demo company state')
    if raw.get('invoice_type') not in ('B2B','B2C') or len(raw.get('items', [])) != 1:
        raise ValueError('Demo profile supports this single-item domestic B2B/B2C layout only')

    inv = deepcopy(raw)
    inv['demo_only'] = True
    inv['demo_source_invoice'] = deepcopy(raw)
    changes = []

    def change(record, field, value, reason, location='invoice'):
        before = record.get(field)
        if before != value:
            record[field] = value
            changes.append({'location':location,'field':field,'printed':before,'demo_value':value,'reason':reason})

    change(inv,'seller_gstin',config['seller_gstin'],'Synthetic test identifier; seller registration is unassigned')
    if inv['invoice_type'] == 'B2B':
        buyer = inv.get('buyer_gstin', '')
        if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]', buyer):
            raise ValueError('Dummy B2B invoice needs a printed synthetic buyer GSTIN')
        if inv.get('buyer_registration') not in (None,'Regular'):
            raise ValueError('Printed buyer registration conflicts with the Regular demo assumption')
        if inv.get('buyer_state') and state_code(inv['buyer_state']) != buyer[:2]:
            raise ValueError('Printed buyer state conflicts with the synthetic buyer GSTIN')
        change(inv,'buyer_gstin',test_gstin(buyer[:14]),'Checksum substitution for the printed synthetic test GSTIN')
        change(inv,'buyer_registration','Regular','Explicit demo assumption for synthetic B2B customer')
        change(inv,'buyer_state',buyer[:2],'State from the printed synthetic buyer GSTIN')
    else:
        if inv.get('buyer_registration') != 'Unregistered' or inv.get('buyer_gstin'):
            raise ValueError('Dummy B2C invoice must explicitly identify an unregistered customer')
        if not inv.get('buyer_state'):
            change(inv,'buyer_state',state_code(inv['place_of_supply']),
                   'Demo assumption: buyer state equals printed place of supply')

    item = inv['items'][0]
    if item.get('unit') and item['unit'] != profile['unit']:
        raise ValueError('Printed unit conflicts with the explicitly selected demo unit')
    change(item,'unit',profile['unit'],'Unit explicitly selected by the user for dummy quantities','item 1')
    present = {tax for tax in TAXES if tax in inv}
    if present not in ({'cgst','sgst'}, {'igst'}):
        raise ValueError('Demo tax summary must contain CGST/SGST or IGST')
    for tax in TAXES:
        if tax not in present:
            if item.get(f'{tax}_rate') and money(item[f'{tax}_rate']) != 0:
                raise ValueError('Printed item tax rate conflicts with the omitted tax component')
            change(inv,tax,'0','Demo assumption: omitted GST component is zero')
            change(item,f'{tax}_rate','0','Demo assumption: omitted GST component is zero','item 1')
    full_rate = sum(money(item[f'{tax}_rate']) for tax in TAXES)
    alias = f"{item['name']} [DEMO HSN {item['hsn']} GST {format(full_rate.normalize(), 'f')}%]"
    change(item,'name',alias,'Separate demo stock masters because sample products have varying illustrative GST rates','item 1')
    inv['demo_adjustments'] = changes
    return inv


def prepare_paired_demo(raw, config):
    """Audited demo substitutions for the supplied multi-item fictional PDFs."""
    if raw.get('dummy_document') is not True:
        raise ValueError('Demo mode accepts only PDFs explicitly marked as synthetic dummy documents')
    if raw.get('extraction_warnings'):
        raise ValueError('; '.join(raw['extraction_warnings']))
    if state_code(raw.get('seller_state','')) != config['demo_profile']['seller_state']:
        raise ValueError('Printed seller state does not match the demo company state')
    if raw.get('supply') not in ('INTRA','INTER','EXEMPT','EXPORT'):
        raise ValueError('Unsupported supply treatment in this demo layout')
    is_export = raw.get('supply') == 'EXPORT'
    if is_export and raw.get('export_mode') != EXPORT_MODES.get(raw.get('classification'),False):
        raise ValueError('Export requires an explicit matching LUT/IGST payment mode')
    inv = deepcopy(raw)
    inv['demo_only'] = True
    inv['demo_source_invoice'] = deepcopy(raw)
    changes = []

    def change(record, field, value, reason, location='invoice'):
        before = record.get(field)
        if before != value:
            changes.append({'location':location,'field':field,'printed':before,'demo_value':value,'reason':reason})
            record[field] = value

    seller = raw.get('seller_gstin','')
    if config.get('source_seller_gstin') and seller != config['source_seller_gstin']:
        raise ValueError('Printed seller differs from the source seller assigned to this company')
    if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',seller) or seller[:2] != state_code(raw['seller_state']):
        raise ValueError('Printed fictional seller GSTIN/state needs review')
    change(inv,'seller_gstin',config['seller_gstin'],'Use the configured synthetic demo seller identifier')
    buyer = raw.get('buyer_gstin','')
    if buyer:
        if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',buyer) or (raw.get('buyer_state') and buyer[:2] != state_code(raw['buyer_state'])):
            raise ValueError('Printed fictional buyer GSTIN/state needs review')
        if not raw.get('buyer_state'):
            change(inv,'buyer_state',buyer[:2],'State from the printed buyer GSTIN')
        change(inv,'buyer_gstin',test_gstin(buyer[:14]),'Checksum substitution for explicitly fictional test GSTIN')
        change(inv,'buyer_registration','Regular','Demo assumption: fictional registered buyer uses Regular registration')
    elif is_export:
        change(inv,'buyer_registration','Unregistered','Overseas buyer explicitly has no Indian GSTIN')
    elif inv.get('buyer_registration') != 'Unregistered':
        raise ValueError('Missing explicit buyer registration')
    intra = False if is_export else state_code(inv['place_of_supply']) == config['demo_profile']['seller_state']
    if raw['supply'] not in ('EXEMPT','EXPORT') and intra != (raw['supply'] == 'INTRA'):
        raise ValueError('Printed supply conflicts with seller state/place of supply')
    for index, item in enumerate(inv['items'],1):
        unit = next((unit for unit in config['units'] if unit.casefold() == item.get('unit','').casefold()),None)
        if not unit:
            raise ValueError('Printed unit needs a configured unit mapping')
        change(item,'unit',unit,'Normalize printed unit capitalization',f'item {index}')
        full_rate = sum(money(item[tax+'_rate']) for tax in TAXES)
        alias = f"{item['name']} [DEMO HSN {item['hsn']} GST {format(full_rate.normalize(), 'f')}%]"
        change(item,'name',alias,'Keep demo stock identity specific to HSN and GST rate',f'item {index}')
    inv['demo_adjustments'] = changes
    return inv

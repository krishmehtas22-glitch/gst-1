"""Read Tally masters into an isolated review snapshot; never apply to the reader."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import uuid
import xml.etree.ElementTree as ET

from Common_Rules.tally_import import post_xml, loaded_companies

COLLECTIONS = {
    'ledgers': ('Ledger', 'LEDGER', 'Name,Parent,PartyGSTIN,MailingName,Address,LedStateName,CountryName,LedgerContact,LedgerPhone,LedgerEmail,IsBillWiseOn'),
    'stock_items': ('StockItem', 'STOCKITEM', 'Name,Parent,BaseUnits,AdditionalUnits,GSTApplicable,GSTDetails,HSNDetails,Description'),
    'units': ('Unit', 'UNIT', 'Name,OriginalName,MailingName,DecimalPlaces,IsSimpleUnit,GSTRepUOM,BaseUnits,AdditionalUnits,Conversion'),
}


def export_request(company, category):
    """Company-scoped Export/Collection only. No Import, Create, Alter or Delete."""
    if not company or not company.strip():
        raise ValueError('Select an open Tally company first.')
    master_type, _, fields = COLLECTIONS[category]
    name = 'BillSyncSnapshot' + master_type
    envelope = ET.Element('ENVELOPE')
    header = ET.SubElement(envelope, 'HEADER')
    for key, value in [('VERSION', '1'), ('TALLYREQUEST', 'Export'), ('TYPE', 'Collection'), ('ID', name)]:
        ET.SubElement(header, key).text = value
    desc = ET.SubElement(ET.SubElement(envelope, 'BODY'), 'DESC')
    variables = ET.SubElement(desc, 'STATICVARIABLES')
    ET.SubElement(variables, 'SVEXPORTFORMAT').text = '$$SysName:XML'
    ET.SubElement(variables, 'SVCURRENTCOMPANY').text = company
    collection = ET.SubElement(ET.SubElement(ET.SubElement(desc, 'TDL'), 'TDLMESSAGE'), 'COLLECTION', NAME=name, ISMODIFY='No')
    ET.SubElement(collection, 'TYPE').text = master_type
    ET.SubElement(collection, 'FETCH').text = fields
    return ET.tostring(envelope, encoding='utf-8', xml_declaration=True)


def parse_collection(raw, category):
    # Tally exports XML 1.0-invalid control references in system names (e.g. &#4;).
    # Strip those controls only; retain the complete returned master XML for review.
    if isinstance(raw, bytes):
        encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-16-le' if raw.startswith(b'<\x00') else 'utf-16-be' if raw.startswith(b'\x00<') else 'utf-8-sig'
        try:
            text = raw.decode(encoding)
        except UnicodeError as exc:
            raise ValueError('Tally returned unreadable ' + category.replace('_', ' ') + '.') from exc
    else:
        text = raw
    def control_ref(match):
        number = int(match[1][1:], 16) if match[1].startswith(('x', 'X')) else int(match[1])
        return '' if number < 32 and number not in (9, 10, 13) else match[0]
    text = re.sub(r'&#(x[0-9a-fA-F]+|X[0-9a-fA-F]+|[0-9]+);', control_ref, text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    try:
        response = ET.fromstring(text)
    except (ValueError, ET.ParseError) as exc:
        raise ValueError('Tally returned unreadable ' + category.replace('_', ' ') + '.') from exc
    errors = [(node.text or '').strip() for node in response.iter() if node.tag in ('LINEERROR', 'ERROR') and (node.text or '').strip()]
    if errors or response.findtext('.//STATUS') == '0':
        raise ValueError('Tally could not export ' + category.replace('_', ' ') + ': ' + ('; '.join(errors) or 'request rejected'))
    collections = list(response.iter('COLLECTION'))
    if not collections:
        raise ValueError('Tally returned no ' + category.replace('_', ' ') + ' collection. No snapshot was saved.')
    tag = COLLECTIONS[category][1]
    records = []
    for collection in collections:
        for node in collection.iter(tag):
            name = (node.get('NAME') or node.findtext('NAME') or '').strip()
            if not name:
                raise ValueError('Tally returned an unnamed ' + tag.lower() + '; no snapshot was saved.')
            fields = {}
            for child in node:
                fields.setdefault(child.tag, []).append(' '.join(child.itertext()).strip())
            records.append({'name': name, 'fields': fields, 'xml': ET.tostring(node, encoding='unicode')})
    return records


def collect_snapshot(company, transport=post_xml, progress=lambda message: None):
    if company not in loaded_companies(transport):
        raise ValueError('The selected company is no longer open in Tally. Reconnect and choose it again.')
    snapshot = {'schema_version': 1, 'mode': 'review_only', 'company': company,
                'collected_at': datetime.now(timezone.utc).isoformat(), 'applied_to_reader': False}
    for category in COLLECTIONS:
        progress('Reading ' + category.replace('_', ' ') + ' from ' + company + '…')
        snapshot[category] = parse_collection(transport(export_request(company, category)), category)
    snapshot['counts'] = {category: len(snapshot[category]) for category in COLLECTIONS}
    return snapshot


def save_snapshot(root, snapshot):
    """Only this feature's directory is written. No reviews/caches/XML/catalogue edits."""
    digest = hashlib.sha256(snapshot['company'].encode('utf-8')).hexdigest()[:16]
    folder = Path(root) / '.invoice_app' / 'tally_master_snapshots' / digest
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    path = folder / (stamp + '_' + uuid.uuid4().hex[:8] + '.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(snapshot, stream, indent=2, ensure_ascii=False)
    return path

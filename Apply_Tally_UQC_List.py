"""All 45 Tally dropdown UQCs, unit catalog only; import button unchanged."""
from pathlib import Path
from datetime import datetime
import ast,base64,hashlib,json,zlib,shutil
import xml.etree.ElementTree as ET

DATA = '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'


def main():
    root=Path(__file__).resolve().parent
    folder=root/'Automation'/'Common_Rules'
    if not folder.is_dir():folder=root/'Common_Rules'
    payload=json.loads(zlib.decompress(base64.b64decode(DATA)))
    sha=lambda s:hashlib.sha256(s.encode('utf-8')).hexdigest()
    writes={};originals={}
    for item in payload:
        path=folder/item['name']
        if not path.is_file():raise SystemExit('Reader source missing; nothing changed: '+str(path))
        original=path.read_bytes();old=original.decode('utf-8-sig')
        if sha(old)==sha(item['text']):continue
        if sha(old) not in item['before']:raise SystemExit('Different source version; nothing changed: '+str(path))
        ast.parse(item['text'],filename=str(path))
        originals[path]=original;writes[path]=item['text'].encode('utf-8')
    namespace={}
    catalog=next(item['text'] for item in payload if item['name']=='unit_catalog.py')
    exec(compile(catalog,'updated_unit_catalog','exec'),namespace)
    count=0;units_found=0
    base=root/'.invoice_app'/'batch_xml'
    for path in sorted(base.glob('*/current/Units.xml')):
        if not path.resolve().is_relative_to(base.resolve()):
            raise SystemExit('Unit XML points outside the batch folder; nothing changed.')
        original=path.read_bytes();document=ET.fromstring(original)
        if document.findtext('./HEADER/TALLYREQUEST')!='Import Data' or document.findtext('.//REPORTNAME')!='All Masters':
            raise SystemExit('Unexpected Units.xml envelope; nothing changed: '+str(path))
        data=document.find('.//REQUESTDATA')
        if data is None:raise SystemExit('Units.xml has no request data; nothing changed: '+str(path))
        changed=False
        for message in data:
            for unit in message:
                if unit.tag!='UNIT':raise SystemExit('Unexpected master in Units.xml; nothing changed: '+str(path))
                units_found+=1
                symbol=unit.findtext('NAME') or unit.get('NAME')
                if not symbol:raise SystemExit('Unit has no symbol; nothing changed: '+str(path))
                code=namespace['unit_uqc'](symbol,unit.findtext('GSTREPUOM'))
                formal=namespace['unit_formal_name'](symbol,unit.findtext('ORIGINALNAME'),code)
                before=ET.tostring(unit)
                for tag,value in [('ORIGINALNAME',formal),('GSTREPUOM',code)]:
                    node=unit.find(tag)
                    if node is None:node=ET.SubElement(unit,tag)
                    node.text=value
                for node in unit.findall('MAILINGNAME'):node.text=formal
                for node in unit.findall('ADDITIONALNAME'):unit.remove(node)
                if ET.tostring(unit)!=before:changed=True;count+=1
        if changed:
            originals[path]=original
            writes[path]=ET.tostring(document,encoding='utf-8',xml_declaration=True)
    if writes:
        backup=root/'.invoice_app'/'code_backups'/datetime.now().strftime('all_unit_uqc_%Y%m%d_%H%M%S_%f')
        for path in writes:
            target=backup/path.relative_to(root)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(originals[path])
        try:
            for path,raw in writes.items():path.write_bytes(raw)
        except Exception:
            for path in writes:path.write_bytes(originals[path])
            raise
        print('Installed. Backup: '+str(backup))
    else:print('Current XML and code already follow the unit rule.')
    print('Current unit definitions checked: '+str(units_found)+'; changed: '+str(count))
    print('Installed all 45 dropdown UQCs with plain distinct formal names. Import button code unchanged.')
    print('Masters, vouchers, quantities, rates and historical XML were not changed.')
    print('No AI requests or Tally imports sent. Restart Python reader; rebuild EXE if used.')
    print('Existing exceptions inside Tally are not removed by this update.')


if __name__=='__main__':main()

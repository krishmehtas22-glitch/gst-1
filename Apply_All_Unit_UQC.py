"""Unit-only offline update: current XML and all future generated/imported units."""
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
    print('Every generated/imported unit receives UQC and a different plain formal name.')
    print('Masters, vouchers, quantities, rates and historical XML were not changed.')
    print('No AI requests or Tally imports sent. Restart Python reader; rebuild EXE if used.')
    print('Existing exceptions inside Tally are not removed by this update.')


if __name__=='__main__':main()

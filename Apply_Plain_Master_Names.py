"""Offline update of the actual desktop AI-to-XML action, Reader 7.25/7.26/7.27 -> 7.28.
Close the Python reader first. Import ALL, XML writers, UQC and history are preserved.
"""
from pathlib import Path
from datetime import datetime
import ast, base64, hashlib, json, zlib

DATA = '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'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def import_method(source):
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == 'import_tally']
    if len(nodes) != 1:
        raise SystemExit('Cannot verify the locked Import ALL method; nothing changed.')
    node = nodes[0]
    return ''.join(source.splitlines(keepends=True)[node.lineno-1:node.end_lineno])


def main():
    root = Path(__file__).resolve().parent
    # Prefer the app beside this installer: that is the documented launch path.
    # A full-source ZIP may also leave a second, unrelated Automation checkout.
    if (root/'Invoice_Desktop.py').is_file() and (root/'Common_Rules').is_dir():
        package = root
    elif (root/'Automation/Invoice_Desktop.py').is_file() and (root/'Automation/Common_Rules').is_dir():
        package = root/'Automation'
    else:
        raise SystemExit('Save this installer beside Invoice_Desktop.py and Common_Rules.')
    if not (package/'Common_Rules').is_dir():
        raise SystemExit('Save this installer in the existing invoice reader source folder.')
    protected_names = ('tally_import.py','tally_units.py','unit_catalog.py','unit_inference.py',
                       'tally_xml.py','client_xml_output.py','groq_reader.py','ai_first.py','desktop_ai.py')
    protected = {package/'Common_Rules'/name: (package/'Common_Rules'/name).read_bytes()
                 for name in protected_names if (package/'Common_Rules'/name).exists()}
    app = package/'Invoice_Desktop.py'
    print('Installing naming-only patch beside: '+str(app), flush=True)
    if not app.is_file():
        raise SystemExit('Invoice_Desktop.py is missing; nothing changed.')
    locked_method = import_method(app.read_text(encoding='utf-8-sig'))
    pending = []
    for item in json.loads(zlib.decompress(base64.b64decode(DATA))):
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('Unexpected update path; nothing changed.')
        path = package/relative
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != package.parent):
            raise SystemExit('Linked source path refused; nothing changed.')
        text = item['text']
        if sha(text.encode()) != item['sha256']:
            raise SystemExit('Update verification failed; nothing changed.')
        ast.parse(text, filename=str(relative))
        if relative.name == 'Invoice_Desktop.py' and import_method(text) != locked_method:
            raise SystemExit('Installed Import ALL differs; the update refused to replace it. Nothing changed.')
        original = path.read_bytes() if path.exists() else None
        if original is not None:
            normalized = original.decode('utf-8-sig').replace('\r\n','\n')
            if sha(normalized.encode()) == item['sha256']:
                continue
            if sha(normalized.encode()) not in item['before']:
                raise SystemExit('Unknown local source preserved; nothing changed: '+str(path))
        elif not item['create']:
            raise SystemExit('Required reader source missing; nothing changed: '+str(path))
        pending.append((path, original, text.encode()))
    if not pending:
        print('Plain master names patch is already installed at: '+str(package))
        print('Reader version and buttons are unchanged.')
        return
    backup = root/'.invoice_app/code_backups'/('plain_master_names_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    for path, original, raw in pending:
        if original is not None:
            target = backup/path.relative_to(package)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
    changed = []
    try:
        for path, original, raw in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            changed.append((path, original))
            path.write_bytes(raw)
        if any(p.read_bytes() != raw for p, raw in protected.items()):
            raise RuntimeError('Protected reader files changed unexpectedly')
        if import_method(app.read_text(encoding='utf-8')) != locked_method:
            raise RuntimeError('Locked Import ALL verification failed')
    except Exception:
        for path, original in reversed(changed):
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    print('Plain party and inventory names patch installed. Backup: '+str(backup))
    print('Reader version/buttons, AI extraction, values, UQC and Import ALL are unchanged.')
    print('Restart the Python reader. Double-click an invoice and Save changes to XML to regenerate its client XML locally.')
    print('This installer sent no AI requests, generated no XML and sent no Tally imports.')
    print('Existing Tally masters/vouchers are not automatically renamed. Review existing entries before importing again.')
    print('An old EXE requires a Windows rebuild; this patch updates Python source only.')


if __name__ == '__main__':
    main()

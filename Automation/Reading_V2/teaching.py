"""Explicit, local supplier/layout guidance for future evidence-checked AI reads."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import tempfile
import sys

from .reader import key, read_invoice
from .document import union

VERSION = 1
DEFAULT_ROOT = Path(__file__).resolve().parent.parent


def library_path(root=None):
    return Path(root if root is not None else DEFAULT_ROOT)/'.invoice_app'/'reading_guidance.json'


def occurrences(result, phrase):
    """Require a unique literal first-page phrase; never execute PDF instructions."""
    wanted = key(phrase).split()
    if not wanted:
        return []
    matches = []
    for page in result['document']['pages'][:1]:
        for line in page['lines']:
            parts = [(part, token) for token in line['tokens'] for part in key(token['text']).split()]
            for start in range(len(parts)-len(wanted)+1):
                selected = parts[start:start+len(wanted)]
                if [p for p, _ in selected] == wanted:
                    tokens = {t['id']: t for _, t in selected}
                    matches.append({'text': phrase, 'box': union([t['box'] for t in tokens.values()]),
                                    'token_ids': list(tokens), 'page': page['number']})
    return matches


def supplier_evidence(result, supplier):
    if key(supplier) != key(result['invoice'].get('seller_name')):
        raise ValueError('Supplier must match the extracted seller. Review the seller identity first.')
    choices = occurrences(result, supplier)
    # A name repeated in the signatory is fine; require exactly one header match.
    choices = [c for c in choices if c['box'][1] < .23]
    if len(choices) != 1:
        raise ValueError('Cannot uniquely verify the supplier in the first-page header.')
    return choices[0]


def supplier_gstin(result):
    value = result['invoice'].get('seller_gstin')
    evidence = result.get('field_evidence', {}).get('seller_gstin')
    if value and evidence and key(value) == key(evidence.get('raw_text')):
        return str(value).strip().upper()
    return ''


def rule_id(rule):
    data = {k: rule[k] for k in ('supplier', 'supplier_gstin', 'supplier_box', 'anchors', 'instruction')}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:20]


def load_library(root=None):
    path = library_path(root)
    if not path.exists():
        return {'version': VERSION, 'rules': []}
    if path.stat().st_size > 2_000_000:
        raise ValueError('Reading guidance library is too large; existing file was preserved.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != VERSION or not isinstance(data.get('rules'), list):
        raise ValueError('Invalid reading guidance library; existing file was preserved.')
    if len(data['rules']) > 1000:
        raise ValueError('Reading guidance library has too many rules.')
    seen = set()
    for rule in data['rules']:
        if not isinstance(rule, dict) or rule.get('approved_by') != 'explicit_teaching_command':
            raise ValueError('Unapproved reading guidance rule.')
        if not isinstance(rule.get('instruction'), str) or not 1 <= len(rule['instruction']) <= 2000:
            raise ValueError('Invalid reading instruction.')
        if (not isinstance(rule.get('supplier'), str) or not rule['supplier'].strip() or
                not isinstance(rule.get('supplier_gstin'), str) or type(rule.get('enabled')) is not bool):
            raise ValueError('Invalid supplier guidance scope.')
        anchors = rule.get('anchors')
        if not isinstance(anchors, list) or not 2 <= len(anchors) <= 8:
            raise ValueError('Invalid layout anchors.')
        for label in [{'box': rule.get('supplier_box'), 'text': rule['supplier']}] + anchors:
            if not isinstance(label, dict) or not isinstance(label.get('text'), str) or not 1 <= len(label['text']) <= 100:
                raise ValueError('Invalid layout anchor text.')
            box = label.get('box')
            if (not isinstance(box, list) or len(box) != 4 or
                    any(type(x) not in (float, int) or not 0 <= x <= 1 for x in box) or
                    box[0] >= box[2] or box[1] >= box[3]):
                raise ValueError('Invalid layout anchor coordinates.')
        if rule.get('id') != rule_id(rule) or rule['id'] in seen:
            raise ValueError('Reading guidance identity mismatch.')
        seen.add(rule['id'])
    return data


def save_change(root, change):
    path = library_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock')
    try:
        stream = lock.open('x')
    except FileExistsError:
        raise ValueError('Another teaching operation holds the library lock; no changes made.') from None
    temporary = None
    try:
        with stream:
            data = load_library(root)
            outcome = change(data)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='reading_guidance_', suffix='.tmp', delete=False) as out:
                temporary = Path(out.name)
                json.dump(data, out, ensure_ascii=True, indent=2)
            os.replace(temporary, path)
            return outcome
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def teach(result, supplier, anchors, instruction, root=None, replace=None):
    instruction = instruction.strip()
    if not 1 <= len(instruction) <= 2000:
        raise ValueError('Use a reading instruction of 1 to 2000 characters.')
    if (not 2 <= len(anchors) <= 8 or any(not key(a) for a in anchors) or
            len({key(a) for a in anchors}) != len(anchors)):
        raise ValueError('Choose 2 to 8 distinct printed layout headings.')
    if result.get('invoice_grouping_required') or result.get('document_kind') != 'invoice_candidate':
        raise ValueError('Teach using one sales invoice, not a receipt or grouped document.')
    supplier = supplier.strip()
    proof = supplier_evidence(result, supplier)
    labels = []
    for anchor in anchors:
        anchor = anchor.strip()
        if not 1 <= len(anchor) <= 100:
            raise ValueError('Layout headings must be 1 to 100 characters.')
        found = occurrences(result, anchor)
        if len(found) != 1:
            raise ValueError('Choose a heading that occurs once on page 1: '+anchor)
        labels.append({'text': anchor, 'box': found[0]['box']})
    rule = {'supplier': supplier, 'supplier_gstin': supplier_gstin(result),
            'supplier_box': proof['box'], 'anchors': labels, 'instruction': instruction,
            'enabled': True, 'approved_by': 'explicit_teaching_command',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'example_sha256': result['source_sha256']}
    rule['id'] = rule_id(rule)

    def change(data):
        old = next((r for r in data['rules'] if r['id'] == replace), None) if replace else None
        if replace and (old is None or key(old['supplier']) != key(supplier) or
                        old['supplier_gstin'] != rule['supplier_gstin']):
            raise ValueError('Replacement must identify a saved rule for this supplier.')
        duplicate = next((r for r in data['rules'] if r['id'] == rule['id']), None)
        if old is not None and old['id'] != rule['id']:
            old['enabled'] = False
        if duplicate is not None:
            duplicate['enabled'] = True
        else:
            if len(data['rules']) >= 1000:
                raise ValueError('Reading guidance library is full.')
            data['rules'].append(rule)
        return rule['id']
    return save_change(root, change)


def disable(rule_id_value, root=None):
    def change(data):
        for rule in data['rules']:
            if rule['id'] == rule_id_value:
                rule['enabled'] = False
                return
        raise ValueError('Saved rule not found; nothing changed.')
    save_change(root, change)


def close_box(a, b):
    return all(abs(x-y) <= .035 for x, y in zip(a, b))


def match_guidance(result, root=None):
    matched, changed = [], []
    for rule in load_library(root)['rules']:
        if not rule['enabled'] or key(rule['supplier']) != key(result['invoice'].get('seller_name')):
            continue
        try:
            proof = supplier_evidence(result, rule['supplier'])
        except ValueError:
            continue
        # Missing/changed GSTIN never weakens an existing identity requirement.
        if supplier_gstin(result) != rule['supplier_gstin']:
            continue
        fits = close_box(proof['box'], rule['supplier_box'])
        for anchor in rule['anchors']:
            found = occurrences(result, anchor['text'])
            fits = fits and len(found) == 1 and close_box(found[0]['box'], anchor['box'])
        if fits:
            matched.append({'id': rule['id'], 'instruction': rule['instruction']})
        else:
            changed.append(rule['id'])
    # Different instructions on overlapping scopes require explicit replacement.
    if len(matched) > 1:
        return {'status': 'ambiguous_rules', 'rules': [], 'candidate_ids': [r['id'] for r in matched]}
    if matched:
        return {'status': 'matched', 'rules': matched}
    return {'status': 'layout_changed_review' if changed else 'no_matching_rule',
            'rules': [], 'candidate_ids': changed}


def main():
    parser = argparse.ArgumentParser(description='Teach future supplier/layout reading. No AI requests or Tally imports.')
    parser.add_argument('invoice', type=Path, nargs='?')
    parser.add_argument('--supplier', help='Confirm the exact supplier printed in the header.')
    parser.add_argument('--anchor', action='append', default=[], help='A unique printed heading; repeat at least twice.')
    parser.add_argument('--instruction', help='How to read fields; never paste an API key or old financial values.')
    parser.add_argument('--library-root', type=Path)
    parser.add_argument('--replace', help='Replace an existing rule for the same supplier.')
    parser.add_argument('--disable', help='Disable a saved rule by ID.')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.list and args.disable:
        parser.error('Choose --list or --disable.')
    try:
        if args.list:
            for rule in load_library(args.library_root)['rules']:
                print(rule['id']+' | '+('enabled' if rule['enabled'] else 'disabled')+' | '+rule['supplier'])
                print('  '+rule['instruction'])
        elif args.disable:
            disable(args.disable, args.library_root)
            print('Rule disabled: '+args.disable)
        else:
            if args.invoice is None:
                parser.error('Provide an example PDF, --supplier, --instruction and at least two --anchor headings.')
            result = read_invoice(args.invoice)
            if sys.stdin.isatty():
                if not args.supplier:
                    proposed = str(result['invoice'].get('seller_name') or '')
                    print('Supplier read from the example: '+proposed)
                    args.supplier = input('Confirm supplier name (Enter accepts this name): ').strip() or proposed
                if not args.instruction:
                    args.instruction = input('Reading instruction for future matching invoices: ').strip()
                if not args.anchor:
                    for table in result.get('table_candidates', []):
                        print('Printed table headings: '+table['header']['raw_text'])
                    args.anchor = [a.strip() for a in input('Two or more unique printed headings, separated by |: ').split('|')]
            if not args.supplier or not args.instruction:
                parser.error('Provide --supplier and --instruction, or run interactively in Command Prompt.')
            if hashlib.sha256(args.invoice.read_bytes()).hexdigest() != result['source_sha256']:
                raise ValueError('Example PDF changed during reading; nothing saved.')
            identity = teach(result, args.supplier, args.anchor, args.instruction,
                             args.library_root, args.replace)
            print('Saved supplier/layout reading rule: '+identity)
        print('Library: '+str(library_path(args.library_root).resolve()))
        print('No AI requests, XML generation or Tally imports. Saved successful reads and approvals remain unchanged.')
    except (ValueError, OSError, KeyError, TypeError):
        # Do not expose document contents, private instruction text or API data in failures.
        raise SystemExit('Teaching operation could not be completed. Check supplier/header identity, unique anchors, rule ID and library format. Existing files were preserved.') from None


if __name__ == '__main__':
    main()

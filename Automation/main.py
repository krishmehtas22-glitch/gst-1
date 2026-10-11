"""Portable CLI: all defaults resolve relative to main.py, not the current directory."""
import argparse
import json
from pathlib import Path
import sys

from Common_Rules.engine import confirm_import, init_client, run
from Common_Rules.templates import inspect_workbook


def main(argv=None):
    parser = argparse.ArgumentParser(description='Multi-client sales PDF to TallyPrime preparation')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    commands = parser.add_subparsers(dest='command')
    commands.add_parser('run', help='Discover and process every current client')
    init = commands.add_parser('init-client', help='Create a client without overwriting existing configuration')
    init.add_argument('name')
    init.add_argument('--company', required=True)
    init.add_argument('--seller-gstin', required=True)
    init.add_argument('--mode', choices=('new','existing'), default='new')
    inspect = commands.add_parser('inspect-template', help='Inspect actual workbook sheets, cells and digest')
    inspect.add_argument('workbook', type=Path)
    confirm = commands.add_parser('confirm-import', help='Record explicit Tally results, not generation success')
    confirm.add_argument('client')
    confirm.add_argument('results', type=Path)
    args = parser.parse_args(argv)
    args.command = args.command or 'run'
    try:
        root = args.root.resolve()
        if args.command == 'run':
            result = run(root)
        elif args.command == 'init-client':
            result = {'created':str(init_client(root,args.name,args.company,args.seller_gstin,args.mode))}
        elif args.command == 'inspect-template':
            result = inspect_workbook(args.workbook)
        else:
            client = (root / args.client).resolve()
            if client.parent != root:
                raise ValueError('Client must be a direct child of the folder containing main.py')
            result = confirm_import(client,args.results)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if args.command == 'run' and any(r.get('error') or r.get('issues') for r in result['clients']):
            return 2
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

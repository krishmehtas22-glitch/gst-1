"""Double-click Start_Automatic_XML.bat to watch all demo client folders."""
import argparse
import json
from pathlib import Path
import time

from Common_Rules.watcher import DemoWatcher


def main():
    parser = argparse.ArgumentParser(description='Automatic XML for marked dummy PDFs only')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--interval', type=float, default=3)
    args = parser.parse_args()
    if args.interval < 1:
        parser.error('interval must be at least one second')
    root = args.root.resolve()
    if not root.is_dir():
        parser.error('root folder must exist')
    watcher = DemoWatcher(root)
    print('DEMO ONLY: Maharashtra seller state, Nos units. Never use for GST filing.', flush=True)
    print(f'Watching {root}\nAdd client folders and PDFs. XML goes in each client/imports folder.\n'
          'Keep this window open. Press Ctrl+C to stop. XML generation does not import into Tally.', flush=True)
    try:
        while True:
            try:
                result = watcher.poll()
                if result is not None:
                    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
            except (ValueError, OSError) as exc:
                print(f'Needs attention: {exc}', flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('\nWatcher stopped. Original PDFs and history retained.')


if __name__ == '__main__':
    main()

"""Polling for the explicitly selected synthetic demo workflow."""
from .engine import (client_lock, discover, init_demo_client, invoice_paths,
                     read_json, run)


def source_signature(root):
    """Ignore our reports/XML; notice new PDFs, edits, removals and reviews."""
    entries = []
    for client in discover(root):
        entries.append((client.name,))
        if (client / '.automation' / 'run.lock').exists():
            entries.append((client.name + '/.automation/run.lock',))
        paths = invoice_paths(client)
        paths += [client / 'client.json', client / 'tally_snapshot.json']
        reviews = client / 'reviews'
        if reviews.is_dir():
            paths += list(reviews.glob('*.json'))
        for path in sorted(paths, key=str):
            if path.is_file():
                stat = path.stat()
                entries.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(entries))


def process_demo_folders(root, state='Maharashtra', unit='Nos'):
    """Create fresh identities, never copy another client's configuration/history."""
    errors = {}
    for client in discover(root):
        if (client / 'client.json').exists():
            continue
        try:
            with client_lock(client):
                if (client / '.automation' / 'history.sqlite3').exists():
                    raise ValueError('Existing history has no client.json; restore its original configuration')
                init_demo_client(root, client.name, client.name, state, unit)
        except (ValueError, OSError) as exc:
            errors[client.name] = str(exc)
    # This launcher is only for dummy data. Never run a real client implicitly.
    real_clients = []
    for client in discover(root):
        try:
            if not read_json(client / 'client.json').get('demo_only'):
                real_clients.append(client.name)
        except (ValueError, OSError):
            pass
    if real_clients:
        return {'clients': [], 'error': 'Demo watcher stopped: real client configurations found: ' + ', '.join(real_clients)}
    result = run(root)
    for report in result['clients']:
        if report['client'] in errors:
            report['error'] = errors[report['client']]
    return result


class DemoWatcher:
    """Require two unchanged scans before processing a copied file batch."""
    def __init__(self, root, state='Maharashtra'):
        self.root = root
        self.state = state
        self.observed = None
        self.completed = None

    def poll(self):
        current = source_signature(self.root)
        if current != self.observed:
            self.observed = current
            return None
        if current == self.completed:
            return None
        result = process_demo_folders(self.root, self.state)
        # Only absorb newly created configurations. A PDF arriving during the
        # run must remain a change to process on the next stable scan.
        existing_paths = {entry[0] for entry in current}
        created_configs = [entry for entry in source_signature(self.root)
                           if entry[0] not in existing_paths and
                           entry[0].endswith('/client.json')]
        self.completed = tuple(sorted(current + tuple(created_configs)))
        self.observed = self.completed
        return result

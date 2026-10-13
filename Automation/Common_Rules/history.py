"""Client-local durable transactions and append-only processing/import events."""
from datetime import datetime, timezone
import json
import sqlite3
from .accounting import fingerprint, legacy_fingerprint, previous_financial_fingerprint


class History:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS invoices (
              invoice_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
              data TEXT NOT NULL, status TEXT NOT NULL, source_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, at TEXT NOT NULL, source TEXT,
              invoice_key TEXT, status TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS master_confirmations (
              identity TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS import_results (
              id INTEGER PRIMARY KEY, at TEXT NOT NULL, data TEXT NOT NULL);
        ''')

    def bind_company(self, company_id, seller_gstin=None):
        previous = self.db.execute("SELECT value FROM metadata WHERE key='company_id'").fetchone()
        if previous and previous[0] != company_id:
            raise ValueError('History belongs to a different company_id; do not reuse it')
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('company_id', ?)", (company_id,))
        if seller_gstin:
            previous_seller = self.db.execute("SELECT value FROM metadata WHERE key='seller_gstin'").fetchone()
            if previous_seller and previous_seller[0] != seller_gstin:
                raise ValueError('History belongs to a different seller GSTIN; do not reuse it')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('seller_gstin', ?)", (seller_gstin,))
        self.db.commit()

    def event(self, source, key, status, message):
        self.db.execute('INSERT INTO events(at,source,invoice_key,status,message) VALUES(?,?,?,?,?)',
                        (datetime.now(timezone.utc).isoformat(), str(source), key, status, message))
        self.db.commit()

    def lookup(self, key):
        row = self.db.execute('SELECT fingerprint,data,status,source_hash FROM invoices WHERE invoice_key=?', (key,)).fetchone()
        if row:
            data = json.loads(row[1])
            current = fingerprint(data)
            if row[0] not in (current,legacy_fingerprint(data),previous_financial_fingerprint(data)):
                raise ValueError('Stored invoice fingerprint does not match its retained data')
            # Read older hashes compatibly, preserving the original database,
            # invoice audit data and confirmed import status.
            return {'fingerprint':current,'data':data,'status':row[2],'sha256':row[3]}

    def save(self, key, fp, data, status):
        self.db.execute('INSERT INTO invoices VALUES(?,?,?,?,?)', (key, fp, json.dumps(data, ensure_ascii=False), status, data['sha256']))
        self.db.commit()

    def retain_saved_addresses(self, previous, invoice):
        """Keep saved metadata when an upgrade recovers a blank address.

        Only the exact same source PDF qualifies. The caller still compares
        quantities, units, amounts, GST, identities and all other saved facts.
        """
        if not previous or not invoice.get('sha256') or previous['sha256']!=invoice['sha256']:
            return invoice,{}
        saved=previous['data'];current=dict(invoice);recovered={}
        for field in ('seller_address','buyer_address'):
            if saved.get(field) in (None,'') and current.get(field) not in (None,''):
                recovered[field]=current[field]
                if field in saved:current[field]=saved[field]
                else:current.pop(field,None)
        return current,recovered

    def correct_units(self,key,invoice):
        """Explicit unit-only edits to the same unimported PDF, with an audit."""
        previous=self.lookup(key)
        if not previous or previous['status'] not in ('pending','generated') or previous['sha256']!=invoice['sha256']:
            return False
        before=previous['data'];old_items=before.get('items',[]);new_items=invoice.get('items',[])
        if len(old_items)!=len(new_items):return False
        changed=[i for i,(old,new) in enumerate(zip(old_items,new_items)) if old.get('unit')!=new.get('unit')]
        if not changed or any(not new_items[i].get('unit_correction_reviewed') for i in changed):return False
        def without_units(data):
            return {**data,'items':[{k:v for k,v in item.items() if k!='unit'} for item in data['items']]}
        if fingerprint(without_units(before))!=fingerprint(without_units(invoice)):return False
        message=json.dumps({'reason':'User changed only quantity units before import',
            'source_sha256':invoice['sha256'],'units':[{'item':i+1,'before':old_items[i]['unit'],'after':new_items[i]['unit']} for i in changed]},ensure_ascii=False)
        with self.db:
            self.db.execute("UPDATE invoices SET fingerprint=?,data=?,status='pending' WHERE invoice_key=?",(fingerprint(invoice),json.dumps(invoice,ensure_ascii=False),key))
            self.db.execute('INSERT INTO events(at,source,invoice_key,status,message) VALUES(?,?,?,?,?)',
                (datetime.now(timezone.utc).isoformat(),invoice['source'],key,'unit_corrected',message))
        return True

    def set_status(self, key, status):
        self.db.execute('UPDATE invoices SET status=? WHERE invoice_key=?', (status, key))
        self.db.commit()

    def active(self):
        return {key:json.loads(data) for key, data in self.db.execute("SELECT invoice_key,data FROM invoices WHERE status IN ('pending','generated')")}

    def statuses(self):
        return [{'invoice_key':key,'status':status,'number':json.loads(data)['number']} for key,data,status in self.db.execute('SELECT invoice_key,data,status FROM invoices ORDER BY invoice_key')]

    def confirmed_masters(self):
        return [json.loads(data) for data, in self.db.execute('SELECT data FROM master_confirmations')]

    def confirm_master(self, master):
        key = master['kind'] + '|' + master['name'].strip().casefold()
        self.db.execute('INSERT OR REPLACE INTO master_confirmations VALUES(?,?)', (key, json.dumps(master, sort_keys=True)))
        self.db.commit()

    def apply_import_result(self, result):
        """Atomically retain all outcomes, including rejected and pending masters."""
        at = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute('INSERT INTO import_results(at,data) VALUES(?,?)', (at,json.dumps(result,ensure_ascii=False)))
            for entry in result.get('masters', []):
                master = entry['master']
                key = master['kind'] + '|' + master['name'].strip().casefold()
                if entry['status'] == 'imported':
                    self.db.execute('INSERT OR REPLACE INTO master_confirmations VALUES(?,?)', (key,json.dumps(master,sort_keys=True)))
                self.db.execute('INSERT INTO events(at,source,invoice_key,status,message) VALUES(?,?,?,?,?)',
                                (at,'master:' + key,None,entry['status'],result['tally_result_reference']))
            for entry in result.get('vouchers', []):
                self.db.execute('UPDATE invoices SET status=? WHERE invoice_key=?', (entry['status'],entry['invoice_key']))
                self.db.execute('INSERT INTO events(at,source,invoice_key,status,message) VALUES(?,?,?,?,?)',
                                (at,'Tally import result',entry['invoice_key'],entry['status'],result['tally_result_reference']))

    def close(self):
        self.db.close()

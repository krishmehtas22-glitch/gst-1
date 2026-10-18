"""Explicit, read-only Tally connection and master snapshot review window."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from Common_Rules.tally_import import loaded_companies
from Tally_Master_Snapshot import collect_snapshot, save_snapshot


class TallyMasterDialog(tk.Toplevel):
    def __init__(self, parent, storage, on_saved=lambda snapshot, path: None, client=None):
        super().__init__(parent)
        self.title('Import masters from Tally')
        self.geometry('1000x670');self.minsize(800,560)
        self.transient(parent);self.grab_set()
        self.storage=Path(storage);self.on_saved=on_saved
        self.events=queue.Queue();self.running=False;self.company=tk.StringVar()
        self.protocol('WM_DELETE_WINDOW',self.close)
        panel=ttk.Frame(self,padding=18);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Import masters from Tally',font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(panel,text='Ledgers · Inventory items · Units',padding=(0,6)).pack(anchor='w')
        ttk.Label(panel,text=('Use masters for '+client+'. Relevant names, GSTINs, HSNs and units are sent to your chosen AI only when you explicitly process invoices. Unmatched entries use the existing creation method.' if client else 'Read-only review copy. No AI analysis starts here.'),wraplength=900).pack(anchor='w')
        connection=ttk.Frame(panel);connection.pack(fill='x',pady=12)
        self.connect_button=ttk.Button(connection,text='Connect / refresh companies',command=self.connect)
        self.connect_button.pack(side='left')
        ttk.Label(connection,text='Local Tally · 127.0.0.1:9000').pack(side='left',padx=12)
        select=ttk.Frame(panel);select.pack(fill='x')
        ttk.Label(select,text='Source company').pack(side='left',padx=(0,10))
        self.picker=ttk.Combobox(select,textvariable=self.company,state='readonly',width=38)
        self.picker.pack(side='left',fill='x',expand=True)
        self.read_button=ttk.Button(select,text='Import ledgers, items & units',command=self.read,state='disabled')
        self.read_button.pack(side='left',padx=(12,0))
        self.picker.bind('<<ComboboxSelected>>',lambda event:self.read_button.config(state='normal' if self.company.get() and not self.running else 'disabled'))
        self.state=ttk.Label(panel,text='Open the source company in Tally, then connect. No request has been sent.',wraplength=920)
        self.state.pack(anchor='w',pady=10)
        self.tabs=ttk.Notebook(panel);self.tabs.pack(fill='both',expand=True)
        self.tables={}
        for category,title,columns in [
            ('ledgers','Ledgers',('Name','Group','GSTIN')),
            ('stock_items','Inventory items',('Name','Group','Base unit')),
            ('units','Units',('Symbol','Formal name','UQC'))]:
            frame=ttk.Frame(self.tabs);self.tabs.add(frame,text=title+' (0)')
            table=ttk.Treeview(frame,columns=columns,show='headings',height=9)
            for column in columns:table.heading(column,text=column);table.column(column,width=250,minwidth=100)
            table.pack(side='left',fill='both',expand=True)
            scroll=ttk.Scrollbar(frame,orient='vertical',command=table.yview);scroll.pack(side='right',fill='y');table.config(yscrollcommand=scroll.set)
            table.bind('<<TreeviewSelect>>',lambda event,c=category:self.details(c))
            self.tables[category]=table
        self.detail=tk.Text(panel,height=5,wrap='word',font=('Segoe UI',9));self.detail.pack(fill='x',pady=8);self.detail.config(state='disabled')
        bottom=ttk.Frame(panel);bottom.pack(fill='x')
        self.saved_button=ttk.Button(bottom,text='View saved snapshot',command=self.open_saved);self.saved_button.pack(side='left')
        self.use_button=ttk.Button(bottom,text='Use snapshot for '+client,command=self.use_snapshot,state='disabled') if client else None
        if self.use_button:self.use_button.pack(side='left',padx=10)
        ttk.Button(bottom,text='Close',command=self.close).pack(side='right')
        self.snapshot=None;self.snapshot_path=None
        self._poll_id=self.after(100,self.poll)

    def run(self, worker):
        self.running=True
        for button in (self.connect_button,self.read_button,self.saved_button):button.config(state='disabled')
        self.picker.config(state='disabled')
        def work():
            try:worker()
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def connect(self):
        if self.running:return
        self.state.config(text='Connecting to local Tally…')
        self.run(lambda:self.events.put(('companies',loaded_companies())))

    def read(self):
        company=self.company.get()
        if self.running or not company:return
        self.state.config(text='Reading masters from '+company+'…')
        def work():
            snapshot=collect_snapshot(company,progress=lambda text:self.events.put(('progress',text)))
            path=save_snapshot(self.storage,snapshot)
            self.events.put(('snapshot',(snapshot,path)))
        self.run(work)

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get_nowait()
            if kind=='progress':self.state.config(text=value);continue
            self.running=False
            self.connect_button.config(state='normal');self.saved_button.config(state='normal');self.picker.config(state='readonly')
            if kind=='companies':
                self.picker.config(values=value)
                if self.company.get() not in value:self.company.set('')
                self.state.config(text='Choose the source company, then import its masters.' if value else 'No open company found. Open a company in Tally, then refresh.')
            elif kind=='snapshot':
                snapshot,path=value;self.show_snapshot(snapshot);self.snapshot_path=path
                self.state.config(text='Saved masters from '+snapshot['company']+'. No AI requests or Tally imports sent.')
                if self.use_button:self.use_button.config(state='normal')
                self.on_saved(snapshot,path)
            elif kind=='error':
                self.state.config(text='Could not complete the read: '+value)
                messagebox.showerror('Tally master read',value,parent=self)
            self.read_button.config(state='normal' if self.company.get() else 'disabled')
        self._poll_id=self.after(100,self.poll)

    def show_snapshot(self,snapshot):
        # Validate before replacing a prior displayed snapshot.
        if not isinstance(snapshot,dict) or snapshot.get('mode')!='review_only' or not isinstance(snapshot.get('company'),str):raise ValueError('Not a BillSync review snapshot.')
        for category in self.tables:
            rows=snapshot.get(category)
            if not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('name'),str) or not isinstance(row.get('fields'),dict) for row in rows):raise ValueError('The saved snapshot is incomplete.')
        self.snapshot=snapshot
        for index,(category,table) in enumerate(self.tables.items()):
            table.delete(*table.get_children())
            for i,row in enumerate(snapshot[category]):
                fields=row['fields']
                def field(name):return ' · '.join(str(v) for v in fields.get(name,[]))
                values=(row['name'],field('PARENT'),field('PARTYGSTIN')) if category=='ledgers' else (row['name'],field('PARENT'),field('BASEUNITS')) if category=='stock_items' else (row['name'],field('MAILINGNAME'),field('GSTREPUOM'))
                table.insert('','end',iid=str(i),values=values)
            title=('Ledgers','Inventory items','Units')[index]
            self.tabs.tab(index,text=f'{title} ({len(snapshot[category])})')
        self.set_details('Source company: '+snapshot['company']+'\nSelect a row to view its exported details. This copy is for review only.')

    def details(self,category):
        selected=self.tables[category].selection()
        if selected and self.snapshot:
            row=self.snapshot[category][int(selected[0])]
            self.set_details(json.dumps(row,indent=2,ensure_ascii=False))

    def set_details(self,text):
        self.detail.config(state='normal');self.detail.delete('1.0','end');self.detail.insert('end',text);self.detail.config(state='disabled')

    def open_saved(self):
        folder=self.storage/'.invoice_app'/'tally_master_snapshots'
        path=filedialog.askopenfilename(parent=self,title='Open saved Tally master snapshot',initialdir=str(folder if folder.exists() else self.storage),filetypes=[('Master snapshot','*.json')])
        if not path:return
        try:
            self.show_snapshot(json.loads(Path(path).read_text(encoding='utf-8')))
            self.snapshot_path=Path(path)
            if self.use_button:self.use_button.config(state='normal')
            self.state.config(text='Viewing saved review copy from '+self.snapshot['company']+'. No Tally request sent.')
        except (ValueError,OSError,TypeError,KeyError) as exc:messagebox.showerror('Saved snapshot',str(exc),parent=self)

    def use_snapshot(self):
        if self.running or not self.snapshot_path:return
        try:self.on_saved(self.snapshot,self.snapshot_path)
        except (ValueError,OSError) as exc:messagebox.showerror('Tally master selection',str(exc),parent=self);return
        self.state.config(text='Selected '+self.snapshot['company']+' for this client. Process invoices to run AI matching; no AI call sent now.')

    def close(self):
        if self.running:
            messagebox.showinfo('Reading Tally','Let the current read finish before closing this window.',parent=self);return
        self.after_cancel(self._poll_id)
        self.destroy()

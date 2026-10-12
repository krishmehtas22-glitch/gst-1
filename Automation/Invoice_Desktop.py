"""Desktop inspection, review forms and automatic processing without CMD."""
from pathlib import Path
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from Common_Rules.desktop import process_sources, save_review
from Common_Rules.watcher import source_signature

FIELDS = ['number','date','seller_name','seller_gstin','seller_state','seller_address',
          'buyer_name','buyer_gstin','buyer_registration','buyer_state','buyer_address',
          'place_of_supply','supply','classification','buyer_country',
          'taxable','cgst','sgst','igst','round_off','total']
ITEM_FIELDS = ['name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate']


class InvoiceApp:
    def __init__(self, window):
        self.window = window
        self.root = Path(__file__).resolve().parent
        self.records = []
        self.busy = False
        self.events = queue.Queue()
        self.last = None
        self.observed = None
        self.closing = False
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.title('Invoice inspection and XML')
        window.geometry('1150x700')
        controls = ttk.Frame(window, padding=10)
        controls.pack(fill='x')
        ttk.Button(controls,text='Choose invoice parent folder',command=self.choose).pack(side='left')
        self.folder_label = ttk.Label(controls,text=str(self.root))
        self.folder_label.pack(side='left',padx=10)
        self.demo = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls,text='Dummy PDFs (fictional substitutions)',variable=self.demo,command=self.reset).pack(side='right')
        actions = ttk.Frame(window,padding=10)
        actions.pack(fill='x')
        ttk.Button(actions,text='Scan and generate XML',command=self.start).pack(side='left')
        ttk.Button(actions,text='Review selected invoice',command=self.review).pack(side='left',padx=8)
        ttk.Button(actions,text='Open selected XML folder',command=self.open_output).pack(side='left')
        ttk.Button(actions,text='Open source PDF',command=self.open_source).pack(side='left',padx=8)
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions,text='Watch for new PDFs',variable=self.auto).pack(side='right')
        ttk.Label(window,text='Put PDFs in client folders under the selected parent. Separate sellers get separate company outputs.').pack(anchor='w',padx=10)
        self.status = ttk.Label(window,text='Ready. XML generation does not import into Tally.',padding=10)
        self.status.pack(fill='x')
        frame = ttk.Frame(window)
        frame.pack(fill='both',expand=True,padx=10)
        self.table = ttk.Treeview(frame,columns=('client','invoice','seller','total','status'),show='headings')
        for field,width in [('client',120),('invoice',190),('seller',260),('total',110),('status',280)]:
            self.table.heading(field,text=field.title())
            self.table.column(field,width=width)
        bar = ttk.Scrollbar(frame,orient='vertical',command=self.table.yview)
        self.table.configure(yscrollcommand=bar.set)
        self.table.pack(side='left',fill='both',expand=True)
        bar.pack(side='right',fill='y')
        self.table.bind('<<TreeviewSelect>>',self.details)
        self.table.bind('<Double-1>',lambda event:self.review())
        self.detail = tk.Text(window,height=7,wrap='word')
        self.detail.pack(fill='x',padx=10,pady=10)
        window.after(200,self.tick)

    def reset(self):
        self.last = None
        self.observed = None

    def close(self):
        self.closing = True
        self.auto.set(False)
        if self.busy:
            self.status.config(text='Finishing the current batch before closing…')
        else:
            self.window.destroy()

    def choose(self):
        if self.busy:
            return
        path = filedialog.askdirectory(initialdir=self.root)
        if path:
            self.root = Path(path)
            self.folder_label.config(text=path)
            self.records = []
            self.table.delete(*self.table.get_children())
            self.reset()

    def start(self):
        if self.busy:
            return
        self.busy = True
        self.status.config(text='Reading invoices and validating totals…')
        root, demo = self.root, self.demo.get()
        def worker():
            try:
                self.events.put(('ok',process_sources(root,demo)))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def tick(self):
        try:
            kind,value = self.events.get_nowait()
            self.busy = False
            if kind == 'error':
                self.status.config(text='Needs attention: '+value)
            else:
                self.records = value
                self.table.delete(*self.table.get_children())
                for index, record in enumerate(value):
                    inv = record['invoice']
                    state = 'Needs review' if record['errors'] else record.get('export','Inspected')
                    self.table.insert('', 'end',iid=str(index),values=(record['client'],inv.get('number',Path(record['path']).name),inv.get('seller_name',''),inv.get('total',''),state))
                count = sum(bool(record['errors']) for record in value)
                self.status.config(text=f'{len(value)} PDFs inspected; {count} need review. XML is prepared, not imported into Tally.')
                # Use the signature from before processing, so PDFs arriving
                # during a run are noticed at the next stable scan.
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.window.destroy()
            return
        if self.auto.get() and not self.busy:
            try:
                signature = (self.demo.get(),source_signature(self.root),
                             tuple((str(p),p.stat().st_mtime_ns) for p in sorted((self.root/'.invoice_app/reviews').glob('*.json'))))
                if signature == self.observed and signature != self.last:
                    self.last = signature
                    self.start()
                self.observed = signature
            except OSError as exc:
                self.status.config(text='Cannot scan folder: '+str(exc))
        self.window.after(1500,self.tick)

    def selected(self):
        selection = self.table.selection()
        return self.records[int(selection[0])] if selection else None

    def details(self,event=None):
        record = self.selected()
        self.detail.delete('1.0','end')
        if record:
            self.detail.insert('end',record['path']+'\n'+'\n'.join(record['errors'])+'\nOutput: '+record.get('company_path','Not generated'))

    def open_output(self):
        record = self.selected()
        if not record or not record.get('company_path'):
            messagebox.showinfo('XML','Select an invoice with a prepared company output.')
            return
        path = str(Path(record['company_path'])/'imports')
        if not Path(path).is_dir():
            messagebox.showinfo('XML','No XML folder is available yet. Resolve the invoice errors first.')
            return
        if os.name == 'nt':
            os.startfile(path)
        else:
            subprocess.Popen(['xdg-open',path])

    def open_source(self):
        record = self.selected()
        if not record:
            return
        try:
            if os.name == 'nt':
                os.startfile(record['path'])
            else:
                subprocess.Popen(['xdg-open',record['path']])
        except OSError as exc:
            messagebox.showerror('PDF',str(exc))

    def review(self):
        record = self.selected()
        if self.busy or not record:
            return
        if not record.get('digest'):
            messagebox.showerror('Review','The PDF could not be read. Replace it with a readable copy.')
            return
        self.auto.set(False)
        top = tk.Toplevel(self.window)
        top.title('Review invoice against the original PDF')
        top.geometry('1100x750')
        canvas = tk.Canvas(top)
        scroll = ttk.Scrollbar(top,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y')
        canvas.pack(fill='both',expand=True)
        form = ttk.Frame(canvas,padding=10)
        canvas.create_window((0,0),window=form,anchor='nw')
        form.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        ttk.Label(form,text='Compare all fields with the source PDF before approving. Unsupported export treatment stays in review.').grid(row=0,column=0,columnspan=4,sticky='w')
        values = {}
        invoice = record['invoice']
        for index,field in enumerate(FIELDS):
            row,col = index//2+1,(index%2)*2
            ttk.Label(form,text=field.replace('_',' ').title()).grid(row=row,column=col,sticky='w',padx=5)
            values[field] = tk.StringVar(value=str(invoice.get(field,'0' if field == 'round_off' else '')))
            ttk.Entry(form,textvariable=values[field],width=38).grid(row=row,column=col+1,pady=3)
        base = len(FIELDS)//2+3
        item_frame = ttk.Frame(form)
        item_frame.grid(row=base,column=0,columnspan=4,sticky='w')
        item_values = []
        def add_item(item=None):
            item = item or {}
            frame = ttk.LabelFrame(item_frame,text=f'Item {len(item_values)+1}',padding=5)
            frame.pack(fill='x',pady=5)
            variables = {}
            for index,field in enumerate(ITEM_FIELDS):
                row,col = index//3,(index%3)*2
                ttk.Label(frame,text=field.replace('_',' ').title()).grid(row=row,column=col,sticky='w',padx=3)
                variables[field] = tk.StringVar(value=str(item.get(field,'')))
                ttk.Entry(frame,textvariable=variables[field],width=24).grid(row=row,column=col+1)
            item_values.append((dict(item),variables,frame))
        for item in invoice.get('items',[]):
            add_item(item)
        buttons = ttk.Frame(form)
        buttons.grid(row=base+1,column=0,columnspan=4,pady=12)
        ttk.Button(buttons,text='Open source PDF',command=self.open_source).pack(side='left',padx=8)
        ttk.Button(buttons,text='Add item',command=add_item).pack(side='left')
        def remove_item():
            if item_values:
                item_values.pop()[2].destroy()
        ttk.Button(buttons,text='Remove last item',command=remove_item).pack(side='left',padx=8)
        def approve():
            edited = dict(invoice)
            edited.update({field:var.get().strip() for field,var in values.items()})
            edited['items'] = [{**old,**{field:var.get().strip() for field,var in variables.items()}} for old,variables,_ in item_values]
            try:
                save_review(self.root,record,edited)
            except (ValueError,OSError) as exc:
                messagebox.showerror('Review',str(exc),parent=top)
                return
            top.destroy()
            self.reset()
            self.auto.set(True)
        ttk.Button(buttons,text='Approve corrections and revalidate',command=approve).pack(side='left')


if __name__ == '__main__':
    window = tk.Tk()
    InvoiceApp(window)
    window.mainloop()

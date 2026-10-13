"""Desktop inspection, review forms and automatic processing without CMD."""
from pathlib import Path
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from Common_Rules.desktop import process_sources, save_review, reset_source_reviews, UNITS
from Common_Rules.source_documents import confirm_test_document, verify_source
from Common_Rules.workflow_status import invoice_status, scan_summary
from Common_Rules.unit_choices import open_unit_choices
from Common_Rules.engine import discover
from Common_Rules.watcher import source_signature
from Common_Rules.supplier_editor import open_layout_editor

FIELDS = ['number','date','seller_name','seller_gstin','seller_state','seller_address',
          'buyer_name','buyer_gstin','buyer_registration','buyer_state','buyer_address',
          'place_of_supply','supply','classification','buyer_country',
          'export_mode','shipping_bill_port',
          'foreign_currency','exchange_rate','foreign_invoice_value',
          'taxable','cgst','sgst','igst','round_off','total']
ITEM_FIELDS = ['name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate',
               'list_rate','discount_rate','foreign_rate','foreign_value',
               'printed_cgst','printed_sgst','printed_igst','printed_total']
REVIEW_CHOICES = {
    'classification': ('taxable','exempt','nil_rated','non_gst','export_lut','export_igst'),
    'buyer_registration': ('Regular','Composition','Unregistered','Consumer'),
    'supply': ('INTRA','INTER','EXEMPT','EXPORT'),
    'export_mode': ('','LUT_without_payment','with_payment_of_IGST'),
}
APP_VERSION='Reader 6.7'


def quantity_unit_summary(invoice):
    items=invoice.get('items',[])
    if not items:return 'Items not extracted'
    return '; '.join(str(item.get('quantity','?'))+' '+str(item.get('unit') or '?')+(' (estimated)' if item.get('unit_auto') else '')+(' (quantity assumed)' if item.get('quantity_assumed') and not item.get('quantity_confirmed') else '') for item in items[:3])+(' +'+str(len(items)-3)+' items' if len(items)>3 else '')


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
        window.title('Invoice inspection and XML — '+APP_VERSION)
        window.geometry('1350x750')
        controls = ttk.Frame(window, padding=10)
        controls.pack(fill='x')
        ttk.Button(controls,text='Choose invoice parent folder',command=self.choose).pack(side='left')
        self.folder_label = ttk.Label(controls,text=str(self.root))
        self.folder_label.pack(side='left',padx=10)
        self.demo = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls,text='Test invoices (fictional data)',variable=self.demo,command=self.reset).pack(side='right')
        scope=ttk.Frame(window,padding=(10,0))
        scope.pack(fill='x')
        ttk.Label(scope,text='Client folder:').pack(side='left')
        self.client_scope=tk.StringVar(value='All clients')
        self.client_picker=ttk.Combobox(scope,textvariable=self.client_scope,state='readonly',width=30)
        self.client_picker.pack(side='left',padx=8)
        self.client_picker.bind('<<ComboboxSelected>>',lambda event:self.reset())
        ttk.Button(scope,text='Re-read selected PDFs',command=self.reread).pack(side='left')
        ttk.Button(scope,text='Save supplier layout',command=self.supplier_layout).pack(side='left',padx=8)
        ttk.Button(scope,text='Confirm test PDF',command=self.confirm_test).pack(side='left')
        ttk.Button(scope,text='Accept / change units',command=self.units).pack(side='left',padx=8)
        ttk.Button(scope,text='Recover processing lock',command=self.recover_lock).pack(side='left')
        ttk.Button(scope,text='Read selected with Gemini',command=self.read_gemini).pack(side='left',padx=8)
        self.refresh_clients()
        actions = ttk.Frame(window,padding=10)
        actions.pack(fill='x')
        ttk.Button(actions,text='Scan and generate XML',command=self.start).pack(side='left')
        ttk.Button(actions,text='Review selected invoice',command=self.review).pack(side='left',padx=8)
        ttk.Button(actions,text='Open client XML folder',command=self.open_output).pack(side='left')
        ttk.Button(actions,text='Open source PDF',command=self.open_source).pack(side='left',padx=8)
        self.auto_units=tk.BooleanVar(value=True)
        ttk.Checkbutton(actions,text='Auto-fill units',variable=self.auto_units,command=self.reset).pack(side='left',padx=8)
        self.summary_accounting=tk.BooleanVar(value=False)
        ttk.Checkbutton(actions,text='Summary GST accounting',variable=self.summary_accounting,command=self.reset).pack(side='left',padx=8)
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions,text='Watch for new PDFs',variable=self.auto).pack(side='right')
        ttk.Button(window,text='Read client batch with Gemini → XML',command=self.read_gemini_batch).pack(anchor='w',padx=10)
        ttk.Label(window,text='Units marked estimated can be changed in Check / change units. For real invoices, untick Test invoices.').pack(anchor='w',padx=10)
        self.status = ttk.Label(window,text='Ready. XML generation does not import into Tally.',padding=10,wraplength=1250)
        self.status.pack(fill='x')
        frame = ttk.Frame(window)
        frame.pack(fill='both',expand=True,padx=10)
        self.table = ttk.Treeview(frame,columns=('client','invoice','seller','total','quantity_unit','status'),show='headings')
        for field,width in [('client',110),('invoice',165),('seller',235),('total',110),('quantity_unit',260),('status',300)]:
            self.table.heading(field,text='Quantity / unit' if field=='quantity_unit' else field.title())
            self.table.column(field,width=width)
        bar = ttk.Scrollbar(frame,orient='vertical',command=self.table.yview)
        self.table.configure(yscrollcommand=bar.set)
        self.table.pack(side='left',fill='both',expand=True)
        bar.pack(side='right',fill='y')
        self.table.bind('<<TreeviewSelect>>',self.details)
        self.table.bind('<Control-a>',self.select_all)
        self.table.bind('<Double-1>',lambda event:self.review())
        self.detail = tk.Text(window,height=7,wrap='word')
        self.detail.pack(fill='x',padx=10,pady=10)
        window.after(200,self.tick)

    def reset(self):
        self.last = None
        self.observed = None

    def refresh_clients(self):
        try:
            values=['All clients']+['Folder: '+folder.name for folder in discover(self.root)]
            if self.client_scope.get() not in values:
                values.append(self.client_scope.get())
            self.client_picker.config(values=values)
        except OSError:
            pass

    def reread(self):
        if self.busy:
            return
        records=[self.records[int(item)] for item in self.table.selection()]
        if not records:
            messagebox.showinfo('Re-read PDFs','Select the invoice rows to re-read. Use Ctrl or Shift to select several.')
            return
        try:
            reset_source_reviews(self.root,records)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Re-read PDFs',str(exc))
            return
        self.reset()
        self.start()

    def units(self):
        if self.busy:return
        watching=self.auto.get();self.auto.set(False)
        def done(changed):
            self.auto.set(watching)
            if changed:self.reset();self.start()
        open_unit_choices(self.window,self.root,self.records,done,self.selected())

    def close(self):
        self.closing = True
        self.auto.set(False)
        if self.busy:
            self.status.config(text='Finishing the current batch before closing…')
        else:
            self.window.destroy()

    def confirm_test(self):
        records=[self.records[int(item)] for item in self.table.selection()]
        if self.busy or not records:return
        if not self.demo.get():
            messagebox.showinfo('Test PDF','Select Test invoices to process fictional test documents.');return
        if any(not record.get('digest') for record in records):return
        documents={record.get('source_sha256',record['digest']):record for record in records}
        names=[record.get('source_path',record['path']) for record in documents.values()]
        if not messagebox.askyesno('Confirm fictional test data',
                f'Confirm that all {len(documents)} selected PDFs contain only fictional test invoices. This permits demo GSTIN substitutions for their invoices.\n\n'+'\n'.join(names[:8])+(' \n…' if len(names)>8 else '')):
            return
        try:
            for record in records:verify_source(self.root,record)
            for record in documents.values():confirm_test_document(self.root,record)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Test PDF',str(exc));return
        self.reset();self.start()

    def select_all(self,event=None):
        self.table.selection_set(self.table.get_children())
        return 'break'

    def choose(self):
        if self.busy:
            return
        path = filedialog.askdirectory(initialdir=self.root)
        if path:
            self.root = Path(path)
            self.folder_label.config(text=path)
            self.records = []
            self.table.delete(*self.table.get_children())
            self.client_scope.set('All clients')
            self.refresh_clients()
            self.reset()

    def start(self):
        if self.busy:
            return
        self.busy = True
        self.status.config(text='Reading invoices and validating totals…')
        root, demo, auto_units, summary_accounting = self.root, self.demo.get(),self.auto_units.get(),self.summary_accounting.get()
        selected=self.client_scope.get()
        clients=None if selected=='All clients' else [selected.removeprefix('Folder: ')]
        def worker():
            try:
                self.events.put(('ok',process_sources(root,demo,clients,auto_units,summary_accounting)))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def read_gemini(self):
        record=self.selected()
        if self.busy or not record:return
        if not record.get('digest'):
            messagebox.showerror('Gemini','Replace the unreadable PDF before requesting API extraction.');return
        if not messagebox.askyesno('Gemini PDF extraction','Send this selected PDF to Google Gemini? API quota and data-use terms apply. The result will need verification in Review. Cached results are reused.'):
            return
        self.auto.set(False);self.busy=True
        self.status.config(text='Reading selected PDF with Gemini…')
        root=self.root;demo=self.demo.get();units=self.auto_units.get();summary=self.summary_accounting.get()
        selected=self.client_scope.get();clients=None if selected=='All clients' else [selected.removeprefix('Folder: ')]
        def worker():
            try:
                from Common_Rules.gemini_reader import extract_selected
                extract_selected(root,record)
                self.events.put(('ok',process_sources(root,demo,clients,units,summary)))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def read_gemini_batch(self):
        if self.busy:return
        selected=self.client_scope.get()
        if selected=='All clients':
            messagebox.showinfo('Gemini batch','Choose one client folder first, then scan its invoices.');return
        client=selected.removeprefix('Folder: ')
        records=[r for r in self.records if r['client']==client]
        if not records:
            messagebox.showinfo('Gemini batch','Scan this client folder first.');return
        if not messagebox.askyesno('Gemini batch → XML',f'Send {len(records)} invoices from {client} to Google Gemini and apply extracted fields for XML? Review the results in Tally. Existing manual corrections are retained. GST, totals, missing fields and duplicate checks still apply. Calls are spaced for the free quota; successful cached results are reused.'):
            return
        self.auto.set(False);self.busy=True
        root=self.root;demo=self.demo.get();units=self.auto_units.get();summary=self.summary_accounting.get()
        def worker():
            try:
                from Common_Rules.gemini_batch import read_batch
                results=read_batch(root,records,progress=lambda message:self.events.put(('progress',message)))
                updated=process_sources(root,demo,[client],units,summary)
                success=sum(r['status']=='extracted' for r in results)
                self.events.put(('ok',updated))
                self.events.put(('progress',f'Gemini batch: {success}/{len(results)} extracted; {sum(not r.get("errors") and bool(r.get("output_path")) for r in updated)} invoices ready for XML. Review in Tally. Per-PDF results: .invoice_app/gemini_batch_results.json'))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def tick(self):
        try:
            kind,value = self.events.get_nowait()
            if kind=='progress':
                self.status.config(text=value)
                self.window.after(100,self.tick)
                return
            self.busy = False
            if kind == 'error':
                self.status.config(text='Needs attention: '+value)
            else:
                previous=self.selected()
                preferred=(previous.get('digest'),previous.get('client')) if previous else None
                self.records = value
                self.table.delete(*self.table.get_children())
                for index, record in enumerate(value):
                    inv = record['invoice']
                    state = invoice_status(record)
                    self.table.insert('', 'end',iid=str(index),values=(record['client'],inv.get('number',Path(record['path']).name),inv.get('seller_name') or ('Candidate: '+inv['seller_name_candidate'] if inv.get('seller_name_candidate') else 'Seller not detected — check PDF'),inv.get('total',''),quantity_unit_summary(inv),state))
                self.status.config(text=scan_summary(value))
                if value:
                    selected=next((i for i,r in enumerate(value) if (r.get('digest'),r['client'])==preferred),
                                  next((i for i,r in enumerate(value) if r['errors']),0))
                    self.table.selection_set(str(selected));self.table.see(str(selected));self.details()
                # Use the signature from before processing, so PDFs arriving
                # during a run are noticed at the next stable scan.
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.window.destroy()
            return
        if self.auto.get() and not self.busy:
            self.refresh_clients()
            try:
                signature = (self.demo.get(),self.auto_units.get(),self.summary_accounting.get(),self.client_scope.get(),source_signature(self.root),
                             tuple((str(p),p.stat().st_mtime_ns) for folder in ('reviews','supplier_layouts','document_settings','unit_estimates')
                                   for p in sorted((self.root/'.invoice_app'/folder).glob('*.json'))),
                             tuple(p.stat().st_mtime_ns for p in (self.root/'.invoice_app').glob('unit_preferences.json')))
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
            evidence=record['invoice'].get('rate_evidence')
            layout=record['invoice'].get('supplier_layout_name')
            price_note=('\nDiscounted items use net unit rates; printed list rates/discounts are retained.' if any(item.get('discount_rate') for item in record['invoice'].get('items',[])) else '')
            price_note+=''.join('\nItem '+str(i+1)+' unit '+str(item.get('unit','?'))+(': estimated — ' if item.get('unit_auto') else ': ')+str(item.get('unit_evidence','printed')) for i,item in enumerate(record['invoice'].get('items',[])))
            price_note+=''.join('\nItem '+str(i+1)+': '+str(item.get('quantity_evidence','Quantity defaulted to 1'))+(' — accepted by you' if item.get('quantity_confirmed') else ' — assumed, check against PDF') for i,item in enumerate(record['invoice'].get('items',[])) if item.get('quantity_assumed'))
            if record['invoice'].get('api_review_mode')=='tally':
                price_note+='\nGemini batch fields applied automatically; compare seller, items, units and GST in Tally. No individual human approval recorded.'
            price_note+=('\nINR accounting values converted using the printed '+record['invoice']['foreign_currency']+' exchange rate '+str(record['invoice'].get('exchange_rate','')) if record['invoice'].get('foreign_currency') else '')
            source_note=record.get('source_path',record['path'])
            if record.get('page_number'):source_note+=f" (page {record['page_number']} of {record['page_count']})"
            self.detail.insert('end',source_note+'\n'+'\n'.join(record['errors']+record.get('notices',[]))+
                ('\n'+evidence if evidence else '')+
                ('\nSupplier layout: '+layout if layout else '')+
                price_note+
                ('\nPrinted unit: '+record['invoice']['source_unit_note'] if record['invoice'].get('source_unit_note') else '')+
                '\nClient folder batch: '+str(record.get('batch_voucher_count',0))+' vouchers'+
                '\nOutput: '+record.get('output_path','Not generated')+
                ('\nTally import: Masters.xml first, then Sales_Vouchers.xml. Missing-master errors: import Required_Masters.xml with duplicate masters ignored, then retry rejected vouchers.' if not record['errors'] and record.get('output_path') else ''))

    def recover_lock(self):
        if self.busy:return
        from Common_Rules.processing_lock import recover_legacy_lock
        companies={Path(r['company_path']) for r in self.records if r.get('company_path') and any('locked' in error.casefold() for error in r.get('errors',[]))}
        if not companies:
            messagebox.showinfo('Processing lock','No locked company is shown in this scan.');return
        if not messagebox.askyesno('Recover old processing lock','Close all other invoice application windows first. Continue to back up old lock markers and retry this scan?'):return
        try:
            for company in companies:recover_legacy_lock(company)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Processing lock',str(exc));return
        self.reset();self.start()

    def open_output(self):
        record = self.selected()
        if not record or not record.get('company_path'):
            messagebox.showinfo('XML','Select an invoice with a prepared company output.')
            return
        if any('locked' in error.casefold() for error in record.get('errors',[])):
            messagebox.showinfo('XML','The current scan is blocked by a processing lock. Recover the lock and scan before importing this batch.');return
        path = record.get('output_path',str(Path(record['company_path'])/'imports'))
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
        ttk.Label(form,text='Compare all fields with the PDF. Export vouchers have no inventory movement; verify export GST reporting in Tally.').grid(row=0,column=0,columnspan=4,sticky='w')
        values = {}
        invoice = record['invoice']
        if invoice.get('source_unit_note'):
            ttk.Label(form,text='Printed '+invoice['source_unit_note']+' — choose the actual unit for each item.').grid(row=0,column=0,columnspan=4,sticky='w')
        for index,field in enumerate(FIELDS):
            row,col = index//2+1,(index%2)*2
            ttk.Label(form,text=field.replace('_',' ').title()).grid(row=row,column=col,sticky='w',padx=5)
            values[field] = tk.StringVar(value=str(invoice.get(field,'0' if field == 'round_off' else '')))
            if field in REVIEW_CHOICES:
                widget=ttk.Combobox(form,textvariable=values[field],values=REVIEW_CHOICES[field],width=36)
            else:
                widget=ttk.Entry(form,textvariable=values[field],width=38)
            widget.grid(row=row,column=col+1,pady=3)
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
                if field=='unit':
                    widget=ttk.Combobox(frame,textvariable=variables[field],values=tuple(UNITS),width=22)
                else:
                    widget=ttk.Entry(frame,textvariable=variables[field],width=24)
                widget.grid(row=row,column=col+1)
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

    def supplier_layout(self):
        record=self.selected()
        if self.busy or not record:return
        if not record.get('digest'):
            messagebox.showerror('Supplier layout','Scan a readable sample PDF first.');return
        watching=self.auto.get();self.auto.set(False)
        def done(changed):
            self.auto.set(watching)
            if changed:
                self.reset();self.start()
        open_layout_editor(self.window,self.root,record,self.demo.get(),done)


if __name__ == '__main__':
    window = tk.Tk()
    InvoiceApp(window)
    window.mainloop()

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
from Common_Rules.runtime_paths import default_data_root
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
APP_VERSION='Reader 7.30'


def quantity_unit_summary(invoice):
    items=invoice.get('items',[])
    if not items:return 'Items not extracted'
    return '; '.join(str(item.get('quantity','?'))+' '+str(item.get('unit') or '?')+(' (estimated)' if item.get('unit_auto') else '')+(' (quantity assumed)' if item.get('quantity_assumed') and not item.get('quantity_confirmed') else '') for item in items[:3])+(' +'+str(len(items)-3)+' items' if len(items)>3 else '')


class InvoiceApp:
    def __init__(self, window):
        self.window = window
        self.root = default_data_root(__file__)
        self.records = []
        self.busy = False
        self.ai_stop = None
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
        self.refresh_clients()
        actions = ttk.Frame(window,padding=10)
        actions.pack(fill='x')
        ttk.Button(actions,text='Refresh invoice list',command=self.start).pack(side='left')
        ttk.Button(actions,text='Analyse selected PDFs',command=self.analyse_selected).pack(side='left',padx=8)
        ttk.Button(actions,text='Review selected invoice',command=self.review).pack(side='left',padx=8)
        ttk.Button(actions,text='Open client XML folder',command=self.open_output).pack(side='left')
        ttk.Button(actions,text='Import to Tally',command=self.import_tally).pack(side='left',padx=8)
        ttk.Button(actions,text='Open source PDF',command=self.open_source).pack(side='left',padx=8)
        self.auto_units=tk.BooleanVar(value=True)
        ttk.Checkbutton(actions,text='Auto-fill units',variable=self.auto_units,command=self.reset).pack(side='left',padx=8)
        self.summary_accounting=tk.BooleanVar(value=False)
        ttk.Checkbutton(actions,text='Summary GST accounting',variable=self.summary_accounting,command=self.reset).pack(side='left',padx=8)
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions,text='Watch PDFs (list only)',variable=self.auto).pack(side='right')
        api_buttons=ttk.Frame(window,padding=(10,0));api_buttons.pack(fill='x')
        ttk.Button(api_buttons,text='Analyse ONE PDF with Groq',command=self.analyse_one_pdf).pack(side='left',padx=(0,8))
        ttk.Button(api_buttons,text='Read client batch with Groq → XML',command=lambda:self.read_gemini_batch('Groq')).pack(side='left')
        ttk.Button(api_buttons,text='Stop AI processing',command=self.stop_ai).pack(side='left',padx=8)
        self.ai_primary=tk.StringVar(value='Groq')
        ttk.Label(window,text='Double-click an invoice to edit its fields/items/units, then Save changes to XML. For real invoices, untick Test invoices.').pack(anchor='w',padx=10)
        ttk.Label(window,text='Complete batch import order: 1 Units.xml → 2 Masters.xml → 3 Sales_Vouchers.xml, in the SAME Tally company.').pack(anchor='w',padx=10)
        self.status = ttk.Label(window,text='PDF listing only. AI runs only after you select files or a client batch and confirm.',padding=10,wraplength=1250)
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
        window.after(0,self.start)
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
        self.revalidate()

    def units(self):
        if self.busy:return
        watching=self.auto.get();self.auto.set(False)
        def done(changed):
            self.auto.set(watching)
            if changed:self.reset();self.revalidate()
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
        self.reset();self.revalidate()

    def select_all(self,event=None):
        self.table.selection_set(self.table.get_children())
        return 'break'

    def choose(self):
        if self.busy:
            return
        path = filedialog.askdirectory(initialdir=self.root)
        if path:
            self.root = Path(path)
            self.ai_primary.set('Groq')
            self.folder_label.config(text=path)
            self.records = []
            self.table.delete(*self.table.get_children())
            self.client_scope.set('All clients')
            self.refresh_clients()
            self.reset()

    def save_ai_provider(self):
        from Common_Rules.ai_first import save_primary
        try:
            save_primary(self.root,self.ai_primary.get())
            self.reset()
        except (ValueError,OSError) as exc:
            messagebox.showerror('AI provider',str(exc))

    def watch_signature(self):
        return (self.demo.get(),self.auto_units.get(),self.summary_accounting.get(),self.client_scope.get(),source_signature(self.root),self.ai_primary.get(),
                tuple((str(p),p.stat().st_mtime_ns) for folder in ('reviews','supplier_layouts','document_settings','unit_estimates')
                      for p in sorted((self.root/'.invoice_app'/folder).glob('*.json'))),
                tuple(p.stat().st_mtime_ns for p in (self.root/'.invoice_app').glob('unit_preferences.json')))

    def start(self):
        """Startup, refresh and watcher only list filenames/metadata."""
        if self.busy:
            return
        self.busy = True
        self.status.config(text='Listing PDFs. No AI requests or XML generation…')
        root=self.root;previous=list(self.records)
        selected=self.client_scope.get()
        clients=None if selected=='All clients' else [selected.removeprefix('Folder: ')]
        def worker():
            try:
                from Common_Rules.invoice_queue import list_sources
                self.events.put(('listed',list_sources(root,clients,previous)))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def revalidate(self, client_names=None):
        """Explicit manual corrections may revalidate locally, without AI."""
        if self.busy:return
        self.busy=True
        root, demo, auto_units, summary_accounting = self.root, self.demo.get(),self.auto_units.get(),self.summary_accounting.get()
        selected=self.client_scope.get()
        clients=client_names if client_names is not None else (None if selected=='All clients' else [selected.removeprefix('Folder: ')])
        retained=[r for r in self.records if client_names is not None and r['client'] not in client_names]
        def worker():
            try:
                self.events.put(('ok',retained+process_sources(root,demo,clients,auto_units,summary_accounting)))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def stop_ai(self):
        if self.ai_stop is not None:
            self.ai_stop.set()
            self.status.config(text='Stopping AI: an active request may finish; completed reads are retained and XML will be prepared. No further provider will start.')

    def read_gemini(self,provider='Groq'):
        self.analyse_selected(provider)

    def analyse_one_pdf(self):
        if self.busy:return
        selection=self.table.selection()
        focused=self.table.focus()
        target=focused if focused in selection else (selection[0] if len(selection)==1 else None)
        if target is None:
            messagebox.showinfo('Analyse ONE PDF','Click the single PDF you want to analyse, then use this button. No AI request was sent.')
            return
        self.analyse_selected('Groq',records=[self.records[int(target)]])

    def analyse_selected(self,provider=None,records=None):
        if self.busy:return
        records=list(records) if records is not None else [self.records[int(item)] for item in self.table.selection()]
        if not records:
            messagebox.showinfo('Analyse PDFs','Select one or more PDFs. Use Ctrl/Shift or Ctrl+A to choose a batch.');return
        from Common_Rules.invoice_queue import source_path
        count=len({source_path(r) for r in records})
        provider=provider or self.ai_primary.get()
        demo=self.demo.get()
        pdf_note=(' PDF: '+Path(next(iter({source_path(r) for r in records}))).name+'.') if count==1 else ''
        test_note=' Test invoices is enabled: continuing confirms only these selected PDFs as fictional test data.' if demo else ''
        if not messagebox.askyesno(provider+' — analyse selected PDFs',f'Analyse exactly {count} selected PDFs with {provider}? At most {count} new AI attempts across configured providers; saved reads and approvals are reused. AI requests may use quota or credits. No other PDFs will receive new AI requests. Python then prepares client XML using retained/local data for the other invoices; uncertainties remain for review. No Tally import is sent.'+pdf_note+test_note):
            return
        self.busy=True
        self.ai_stop=threading.Event()
        self.status.config(text=f'Analysing {count} selected PDFs with '+provider+'…')
        root=self.root;demo=self.demo.get();units=self.auto_units.get();summary=self.summary_accounting.get()
        stop_event=self.ai_stop
        def worker():
            try:
                from Common_Rules.desktop_ai import analyse_paths
                from Common_Rules.ai_first import summary_text
                updated,report=analyse_paths(root,records,provider,demo,units,summary,
                    progress=lambda message:self.events.put(('progress',message)),stop_event=stop_event)
                self.events.put(('ok',updated))
                if count==1:
                    message=(f'ONE PDF: {Path(next(iter({source_path(r) for r in records}))).name}. '
                             f'{report.get("new_ai_attempts",0)} new AI attempts (maximum 1); saved reads/approvals are reused. '
                             f'Other PDFs received no new AI requests. Python prepared {report["xml_prepared"]} client XML vouchers from saved/local data. No Tally import sent.')
                else:message=summary_text(report)
                self.events.put(('progress',message))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def read_gemini_batch(self,provider='Groq'):
        if self.busy:return
        selected=self.client_scope.get()
        if selected=='All clients':
            messagebox.showinfo(provider+' batch','Choose one client folder first, then scan its invoices.');return
        client=selected.removeprefix('Folder: ')
        records=[r for r in self.records if r['client']==client]
        if not records:
            messagebox.showinfo(provider+' batch','Scan this client folder first.');return
        from Common_Rules.invoice_queue import source_path
        paths=sorted({source_path(r) for r in records})
        upload='PDF text (local OCR for scans) to '+provider
        demo=self.demo.get()
        test_note=' Test invoices is enabled: continuing confirms these batch PDFs are fictional test data.' if demo else ''
        if not messagebox.askyesno(provider+' batch → XML',f'Analyse {len(paths)} PDFs from {client} as {upload}? At most {len(paths)} new AI attempts across configured providers; requests may use quota or credits. Only the PDFs in this confirmed list receive new AI requests. Saved reads and approvals are reused. Python then prepares complete client XML with uncertainties retained for review. No Tally import is sent.'+test_note):
            return
        self.busy=True
        self.ai_stop=threading.Event()
        root=self.root;demo=self.demo.get();units=self.auto_units.get();summary=self.summary_accounting.get()
        stop_event=self.ai_stop
        def worker():
            try:
                from Common_Rules.ai_first import run_ai_first,summary_text
                updated,report=run_ai_first(root,demo,[client],units,summary,primary=provider,
                    progress=lambda message:self.events.put(('progress',message)),
                    confirm_test=demo,stop_event=stop_event,selected_paths=paths,max_new_requests=len(paths))
                self.events.put(('ok',updated))
                self.events.put(('progress',summary_text(report)))
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
            self.ai_stop = None
            if kind == 'error':
                self.status.config(text='Needs attention: '+value)
            else:
                previous=self.selected()
                preferred=(previous.get('digest'),previous.get('client')) if previous else None
                from Common_Rules.invoice_queue import source_path
                signatures={source_path(r):r.get('listing_signature') for r in self.records}
                for record in value:
                    if 'listing_signature' not in record:
                        record['listing_signature']=signatures.get(source_path(record))
                self.records = value
                self.table.delete(*self.table.get_children())
                for index, record in enumerate(value):
                    inv = record['invoice']
                    state = invoice_status(record)
                    self.table.insert('', 'end',iid=str(index),values=(record['client'],inv.get('number',Path(record['path']).name),'Pending AI' if record.get('listing_only') else inv.get('seller_name') or ('Candidate: '+inv['seller_name_candidate'] if inv.get('seller_name_candidate') else 'Seller not detected — check PDF'),inv.get('total',''),'Not analysed' if record.get('listing_only') else quantity_unit_summary(inv),state))
                self.status.config(text=(f'{len(value)} PDFs listed. No AI calls or XML generation. Select PDFs or choose a client batch to analyse.' if kind=='listed' else scan_summary(value)))
                if value:
                    selected=next((i for i,r in enumerate(value) if (r.get('digest'),r['client'])==preferred),
                                  next((i for i,r in enumerate(value) if r['errors']),0))
                    self.table.selection_set(str(selected));self.table.see(str(selected));self.details()
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.window.destroy()
            return
        if self.auto.get() and not self.busy:
            self.refresh_clients()
            try:
                signature = self.watch_signature()
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
                price_note+='\n'+record['invoice'].get('api_provider','AI')+' batch fields applied automatically; compare seller, items, units and GST in Tally. No individual human approval recorded.'
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
                ('\nTally import: '+('Units.xml FIRST → Masters.xml → Sales_Vouchers.xml, in the same selected Tally company. See Batch_Report.json; ignore duplicate masters. Retry rejected vouchers after repairing masters.' if record.get('tally_review_warnings') is not None else 'Masters.xml first, then Sales_Vouchers.xml. Missing-master errors: import Required_Masters.xml with duplicate masters ignored, then retry rejected vouchers.') if not record['errors'] and record.get('output_path') else ''))

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
        self.reset();self.revalidate()

    def open_output(self):
        record = self.selected()
        if not record or not (record.get('company_path') or record.get('output_path')):
            messagebox.showinfo('XML','Select an invoice with a prepared company output.')
            return
        if any('locked' in error.casefold() for error in record.get('errors',[])):
            messagebox.showinfo('XML','The current scan is blocked by a processing lock. Recover the lock and scan before importing this batch.');return
        path = record.get('output_path') or str(Path(record['company_path'])/'imports')
        if not Path(path).is_dir():
            messagebox.showinfo('XML','No XML folder is available yet. Resolve the invoice errors first.')
            return
        if os.name == 'nt':
            os.startfile(path)
        else:
            subprocess.Popen(['xdg-open',path])

    def import_tally(self):
        import gc
        if self.busy:return
        record=self.selected()
        if not record or not record.get('output_path'):
            messagebox.showinfo('Import to Tally','Select an invoice with prepared XML first.');return
        from Common_Rules.tally_import import import_plan,client_import_groups,voucher_count,loaded_companies,post_xml,send_plan,tally_executable,launch_tally
        from Common_Rules.engine import write_json
        folder=Path(record.get('group_output_path') or record['output_path'])
        try:
            selected_plan=import_plan(folder)
            groups=client_import_groups(record['output_path'],folder)
            selected_group=next(i for i,g in enumerate(groups) if (g.get('group_id')==record.get('output_seller_group') if 'group_id' in g else folder.resolve() in g['folders']))
            if 'group_id' in groups[selected_group]:selected_plan=groups[selected_group]['plan']
            plan=groups[selected_group]['plan']
            all_folder_count=len({p for g in groups for p in g['folders']})
            all_voucher_count=sum(voucher_count(g['plan']) for g in groups)
            from Common_Rules.workflow_validation import enabled as workflow_enabled,selected_invoice_plan
            if workflow_enabled(self.root):selected_plan=selected_invoice_plan(selected_plan,record)
        except (OSError,ValueError) as exc:
            messagebox.showerror('Import to Tally',str(exc));return
        self.auto.set(False);self.busy=True
        dialog=tk.Toplevel(self.window);dialog.title('Import existing XML to Tally')
        dialog._billsync_custom=True
        width=min(940,dialog.winfo_screenwidth()-60);height=min(670,dialog.winfo_screenheight()-100)
        dialog.geometry(f'{width}x{height}+30+20');dialog.minsize(min(760,width),min(460,height));dialog.transient(self.window);dialog.grab_set()
        footer=ttk.Frame(dialog,padding=8);footer.pack(side='bottom',fill='x')
        ttk.Label(dialog,text='Import to Tally',font=('Segoe UI',18,'bold')).pack(anchor='w',padx=16,pady=14)
        area=ttk.Frame(dialog);area.pack(fill='both',expand=True,padx=8)
        canvas=tk.Canvas(area,highlightthickness=0,background='white');canvas.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(area,orient='vertical',command=canvas.yview);scrollbar.pack(side='right',fill='y');canvas.configure(yscrollcommand=scrollbar.set)
        content=ttk.Frame(canvas);content_id=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(content_id,width=event.width))
        ttk.Label(content,text='Current XML: '+str(folder),wraplength=width-70).pack(anchor='w',padx=12,pady=10)
        ttk.Label(content,text='Open the destination company in Tally, then choose it below.\nOrder: '+ ' → '.join(name for name,_ in plan)).pack(anchor='w',padx=12)
        include_all=tk.BooleanVar(value=True)
        if all_folder_count>1 or len(groups)>1 or voucher_count(selected_plan)<all_voucher_count:
            ttk.Checkbutton(content,text=f'Include complete client batch: {all_voucher_count} invoices',variable=include_all).pack(anchor='w',padx=12,pady=6)
            ttk.Label(content,text=f'Untick to import only this selected set ({voucher_count(selected_plan)} invoices), when completing an earlier partial import.',wraplength=760).pack(anchor='w',padx=12)
        else:
            ttk.Label(content,text=f'This import contains {all_voucher_count} invoices.',wraplength=720).pack(anchor='w',padx=12)
        company_variables=[];company_choices=[]
        for group in groups:
            ttk.Label(content,text=group['label']+f" ({voucher_count(group['plan'])} invoices)",wraplength=760).pack(anchor='w',padx=12)
            variable=tk.StringVar(value='')
            choice=ttk.Combobox(content,textvariable=variable,state='readonly',width=80)
            choice.pack(anchor='w',padx=12,pady=5)
            company_variables.append(variable);company_choices.append(choice)
        state=ttk.Label(footer,text='Connecting to local Tally…',wraplength=680)
        state.pack(anchor='w',padx=12,pady=10)
        messages=queue.Queue();running=[False];launch_attempted=[False]
        def close():
            if running[0]:return
            self.busy=False;dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW',close)
        def refresh():
            if running[0]:return
            running[0]=True;state.config(text='Reading company list from local Tally…')
            def worker():
                try:messages.put(('companies',loaded_companies(lambda data:post_xml(data,timeout=3))))
                except Exception as exc:messages.put(('connection',str(exc)))
            # Dispose of prior Tk dialog cycles on the UI thread, never in a worker.
            gc.collect()
            threading.Thread(target=worker,daemon=True).start()
        def import_now():
            if running[0]:return
            chosen_groups=groups if include_all.get() else [{**groups[selected_group],'plan':selected_plan}]
            indices=list(range(len(groups))) if include_all.get() else [selected_group]
            targets=[company_variables[i].get() for i in indices]
            if not all(targets):
                state.config(text='Choose the destination company for each included seller first.');return
            running[0]=True
            receipt_folder=Path(record['output_path']) if include_all.get() else folder
            def worker():
                try:
                    results=[];cancelled=False;edit_issue=None
                    for group,target in zip(chosen_groups,targets):
                        try:
                            from Common_Rules.workflow_validation import WorkflowReviewRequired,acknowledge,enabled as workflow_enabled,MARKER
                            if workflow_enabled(self.root) and any(name=='Sales_Vouchers.xml' and MARKER.encode() not in data for name,data in group['plan']):
                                raise ValueError('Re-process this client to apply invoice workflow validation. Saved AI reads and human reviews are reused; no import sent.')
                            try:
                                received=send_plan(group['plan'],target,progress=lambda text:messages.put(('progress',text)),submit_all=True)
                            except WorkflowReviewRequired as review:
                                decision=queue.Queue()
                                messages.put(('workflow_review',(review,decision)))
                                answer=decision.get()
                                if answer is True:
                                    approved_plan=acknowledge(group['plan'],review,receipt_folder)
                                    received=send_plan(approved_plan,target,progress=lambda text:messages.put(('progress',text)),submit_all=True)
                                else:
                                    cancelled=True
                                    edit_issue=answer.get('issue') if isinstance(answer,dict) and answer.get('action')=='edit' else None
                                    received=[{'file':'Invoice workflow review','company':target,'errors':[],'reason':'Cancelled by user. This group and all remaining groups were not sent.','status':'cancelled','request_attempted':False}]
                        except (ValueError,OSError) as exc:
                            received=[{'file':'Company/connection check','company':target,'errors':[str(exc)],'status':'unknown'}]
                        for result in received:result['xml_folders']=[str(p) for p in group['folders']]
                        results.extend(received)
                        if cancelled or any(r.get('status')=='unknown' for r in received):break
                    try:write_json(receipt_folder/'Last_Tally_Import.json',{'import_mode':'full-submit-all','output_generation':groups[0].get('generation',record.get('output_generation')),'expected_vouchers':sum(voucher_count(g['plan']) for g in chosen_groups),'results':results,'cancelled':cancelled})
                    except OSError:pass
                    messages.put(('import_cancelled',(results,edit_issue)) if cancelled else ('imported',results))
                except Exception as exc:messages.put(('import_error',str(exc)))
            # Dispose of prior Tk dialog cycles on the UI thread, never in a worker.
            gc.collect()
            threading.Thread(target=worker,daemon=True).start()
        buttons=ttk.Frame(footer);buttons.pack(anchor='w',padx=12,pady=8)
        ttk.Button(buttons,text='Refresh companies',command=refresh).pack(side='left')
        import_button=ttk.Button(buttons,text='Import ALL: Units + Masters + Vouchers',command=import_now,state='disabled')
        import_button.pack(side='left',padx=8)
        ttk.Button(buttons,text='Close',command=close).pack(side='left')
        def poll():
            if not dialog.winfo_exists():return
            try:
                while True:
                    kind,value=messages.get_nowait()
                    if kind=='progress':state.config(text=value);continue
                    if kind=='workflow_review':
                        from Workflow_Review_Dialog import open_workflow_review
                        review,decision=value
                        open_workflow_review(dialog,review,lambda answer:decision.put(answer))
                        continue
                    running[0]=False
                    if kind=='companies':
                        for choice,variable in zip(company_choices,company_variables):
                            choice.config(values=value)
                            if variable.get() not in value:variable.set('')
                        import_button.config(state='normal' if value else 'disabled')
                        state.config(text='Choose a company and import.' if value else 'No company is available. Open your company in Tally and click Refresh companies.')
                    elif kind=='connection':
                        import_button.config(state='disabled');state.config(text=value)
                        if not launch_attempted[0] and os.name=='nt':
                            launch_attempted[0]=True
                            # Do not launch a second instance when Tally is already open.
                            try:
                                output=subprocess.run(['tasklist','/FI','IMAGENAME eq tally.exe','/FO','CSV','/NH'],capture_output=True,text=True,timeout=5).stdout.lower()
                                already_open='tally.exe' in output
                            except (OSError,subprocess.TimeoutExpired):already_open=False
                            if not already_open:
                                executable=tally_executable(self.root)
                                if executable is None:
                                    selected=filedialog.askopenfilename(parent=dialog,title='Choose installed Tally executable (one-time setup)',filetypes=[('Tally executable','*.exe')])
                                    executable=Path(selected) if selected else None
                                if executable:
                                    try:
                                        launch_tally(executable)
                                        write_json(self.root/'.invoice_app'/'tally_connection.json',{'executable':str(executable)})
                                        state.config(text='Tally opened. Select/open your company in Tally, then click Refresh companies. Enable its HTTP/XML server on port 9000 once if needed.')
                                    except (ValueError,OSError) as exc:state.config(text=str(exc))
                    elif kind=='import_cancelled':
                        results,edit_issue=value
                        attempted=any(r.get('request_attempted') for r in results)
                        state.config(text='Import cancelled. Remaining groups were not sent. '+('Earlier groups may have been sent; see Last_Tally_Import.json and check Tally.' if attempted else 'No units, masters or vouchers were sent.'))
                        import_button.config(state='normal')
                        if edit_issue:
                            matches=[(i,r) for i,r in enumerate(self.records) if str(Path(r['path']).resolve())==edit_issue.get('read_path') and r.get('digest')==edit_issue.get('read_sha256')]
                            if len(matches)==1:
                                i,matched=matches[0];close()
                                self.table.reattach(str(i),'','end');self.table.selection_set(str(i));self.table.focus(str(i));self.table.see(str(i))
                                self.window.after_idle(self.review)
                                return
                            state.config(text='Import cancelled. Refresh the invoice list, then double-click the source invoice to edit it. No new AI request was sent.')
                    elif kind=='imported':
                        lines=[];failed=False
                        for result in value:
                            counts=result.get('counts',{})
                            if result.get('requested_vouchers') is not None:lines.append('Voucher request: '+str(result['requested_vouchers'])+' invoices')
                            if result.get('continued_after_reported_error'):lines.append('Tally rejection recorded; ALL mode continued to the next XML stage.')
                            if result.get('existing_units_reused'):lines.append('Existing units reused: '+', '.join(result['existing_units_reused']))
                            if result.get('unit_original_names_adjusted'):lines.append('Unit formal names made distinct. Selling symbols unchanged.')
                            detail=result.get('reason','Already available; no import sent') if result.get('skipped') else ', '.join(f'{key.lower()} {number}' for key,number in counts.items())
                            lines.append(result['company']+' / '+result['file']+': '+detail)
                            if result.get('errors') or counts.get('ERRORS',0) or counts.get('CANCELLED',0) or counts.get('EXCEPTIONS',0):
                                failed=True;lines.extend(result.get('errors',[]))
                        title='Tally import needs attention' if failed else 'Tally import result'
                        state.config(text=title+'. Review the server counters below and check the vouchers in Tally.')
                        import_button.config(state='disabled')  # deliberate refresh before another import
                        messagebox.showinfo(title,'\n'.join(lines)+'\n\nCheck Tally before retrying. No automatic retries were sent.',parent=dialog)
                    else:state.config(text=value)
            except queue.Empty:pass
            dialog.after(100,poll)
        refresh();poll()

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

    def save_manual_edits(self, record, edited):
        """Save the human review and regenerate this client's XML locally."""
        save_review(self.root,record,edited)
        if self.demo.get():
            confirm_test_document(self.root,record)
        from Common_Rules.tally_review_export import enable
        enable(self.root,record['client'])
        self.reset()
        self.revalidate(client_names=[record['client']])

    def prepare_manual_review(self, record):
        """An explicit double-click may load saved/local fields, never call AI."""
        if not record.get('listing_only'):
            return record
        from Common_Rules.desktop import inspect_sources
        from Common_Rules.invoice_queue import source_path
        matching=[r for r in inspect_sources(self.root,[record['client']],self.demo.get(),self.auto_units.get())
                  if source_path(r)==source_path(record)]
        if not matching:
            raise ValueError('This PDF changed or disappeared. Refresh the invoice list.')
        for row in matching:
            row['listing_signature']=record.get('listing_signature')
        if len(matching)==1:
            return matching[0]
        # Independent invoice pages must keep their own source identity/review.
        retained=[r for r in self.records if source_path(r)!=source_path(record)]
        self.events.put(('ok',retained+matching))
        messagebox.showinfo('Review','This PDF contains multiple invoices. Double-click the invoice/page you want to edit. No AI request was sent.')
        return None

    def review(self):
        record = self.selected()
        if self.busy or not record:
            return
        try:
            record=self.prepare_manual_review(record)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Review',str(exc));return
        if record is None:return
        if not record.get('digest'):
            messagebox.showerror('Review','The PDF could not be read. Replace it with a readable copy.')
            return
        watching=self.auto.get();self.auto.set(False)
        top = tk.Toplevel(self.window)
        top.title('Review invoice against the original PDF')
        def close_review():
            self.auto.set(watching)
            top.destroy()
        top.protocol('WM_DELETE_WINDOW',close_review)
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
                self.save_manual_edits(record,edited)
            except (ValueError,OSError) as exc:
                messagebox.showerror('Review',str(exc),parent=top)
                return
            top.destroy()
            self.auto.set(watching)
        if self.demo.get():
            ttk.Label(form,text='Test invoices is enabled: saving confirms this PDF contains fictional test data.').grid(row=base+2,column=0,columnspan=4,sticky='w')
        ttk.Button(buttons,text='Save changes to XML',command=approve).pack(side='left')

    def supplier_layout(self):
        record=self.selected()
        if self.busy or not record:return
        if not record.get('digest'):
            messagebox.showerror('Supplier layout','Scan a readable sample PDF first.');return
        watching=self.auto.get();self.auto.set(False)
        def done(changed):
            self.auto.set(watching)
            if changed:
                self.reset();self.revalidate()
        open_layout_editor(self.window,self.root,record,self.demo.get(),done)


if __name__ == '__main__':
    window = tk.Tk()
    InvoiceApp(window)
    window.mainloop()

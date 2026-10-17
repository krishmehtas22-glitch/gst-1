"""Presentation layer over the locked Reader. Engine and import methods are inherited."""
from datetime import datetime
from pathlib import Path
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog

from Invoice_Desktop import InvoiceApp,APP_VERSION,quantity_unit_summary
from Common_Rules.runtime_paths import default_data_root
from Common_Rules.workflow_status import invoice_status
from Document_Upload import upload_documents,client_folder
from BillSync_Controls import ActionButton,rounded_box,RoundedCard,draw_icon
from Tally_Master_Dialog import TallyMasterDialog
from Export_Refund_Review import summary as refund_summary,load_review as load_refund_review,review_key,amount as refund_amount
from Export_Refund_Dialog import open_refund_review

BG='#f3f6fc';NAV='#101d30';BLUE='#2460ed';INK='#17243a';MUTED='#65748b';BORDER='#dbe3f0'
UI_VERSION='BillSync UI 2.2'


class ActivityLabel(ttk.Label):
    def __init__(self,parent,app,**kwargs):
        self.app=app;super().__init__(parent,**kwargs)
    def config(self,**kwargs):
        text=kwargs.get('text')
        if text and (not self.app.activity or self.app.activity[-1][1]!=text):
            self.app.activity.append((datetime.now().strftime('%H:%M:%S'),str(text)))
            self.app.activity=self.app.activity[-500:]
            self.app.refresh_activity()
        if text is not None:
            kwargs['text']=str(text) if len(str(text))<=150 else str(text)[:147]+'…'
        return super().configure(**kwargs)


class BillSyncApp(InvoiceApp):
    def __init__(self,window,data_root=None):
        self.window=window;self._configuration_root=default_data_root(__file__)
        storage=self._configuration_root
        if data_root is None:
            config=storage/'.invoice_app'/'billsync_ui_settings.json'
            try:
                saved=Path(json.loads(config.read_text(encoding='utf-8'))['storage']) if config.exists() else None
                if saved is not None and saved.is_dir():storage=saved
                elif (storage.parent/'Invoice_Desktop.py').is_file():storage=storage.parent
            except (ValueError,OSError,KeyError,TypeError):pass
        self.root=Path(data_root) if data_root is not None else storage
        self.refund_reviews={};self.records=[];self.busy=False;self.ai_stop=None;self.events=queue.Queue()
        self.last=None;self.observed=None;self.closing=False;self.activity=[];self._view_signature=None
        self.demo=tk.BooleanVar(value=True);self.auto_units=tk.BooleanVar(value=True)
        # Hide the old checkbox, preserving its original accounting default exactly.
        self.summary_accounting=tk.BooleanVar(value=False)
        self.auto=tk.BooleanVar(value=False);self.ai_primary=tk.StringVar(value='Groq')
        self.client_scope=tk.StringVar(value='All clients');self.client_display=tk.StringVar(value='All clients');self.search=tk.StringVar();self.filter_status=tk.StringVar(value='All statuses')
        self.style=ttk.Style(window);self.style.theme_use('clam')
        self.style.configure('.',font=('Segoe UI',9),background=BG,foreground=INK)
        self.style.configure('Card.TFrame',background='white');self.style.configure('Card.TLabel',background='white')
        self.style.configure('Heading.TLabel',font=('Segoe UI',11,'bold'),background='white')
        self.style.configure('Muted.TLabel',foreground=MUTED,background='white')
        self.style.configure('Section.TLabel',font=('Segoe UI',9),foreground='#455872',background='white')
        self.style.configure('TButton',padding=(9,6),background='white',bordercolor=BORDER,foreground=INK,relief='solid',borderwidth=1,focusthickness=0)
        self.style.map('TButton',background=[('active','#e9f0ff')])
        self.style.configure('Primary.TButton',background=BLUE,foreground='white',bordercolor=BLUE)
        self.style.map('Primary.TButton',background=[('active','#164cd0')],foreground=[('active','white')])
        self.style.configure('Upload.TButton',font=('Segoe UI',11),padding=(14,10),background=BLUE,foreground='white')
        self.style.map('Upload.TButton',background=[('active','#164cd0')])
        self.style.configure('Stop.TButton',foreground='#c62828',background='#fff4f4',bordercolor='#ed7777')
        self.style.configure('Client.TCombobox',font=('Segoe UI',10),padding=5,fieldbackground='white')
        self.style.configure('Treeview',background='white',fieldbackground='white',font=('Segoe UI',10),rowheight=30,bordercolor=BORDER)
        self.style.configure('Treeview.Heading',font=('Segoe UI',9),background='#f4f7fc',padding=(10,9),relief='flat')
        self.style.map('TCombobox',fieldbackground=[('readonly','white')],selectbackground=[('readonly','white')],selectforeground=[('readonly',INK)])
        self.style.map('Treeview',background=[('selected','#e1ebff')],foreground=[('selected',INK)])
        window.title(f'BillSync — Invoice to Tally | {UI_VERSION} | {APP_VERSION}')
        width=min(1500,max(1100,window.winfo_screenwidth()-50));height=min(1000,max(650,window.winfo_screenheight()-100))
        window.geometry(f'{width}x{height}');window.minsize(1100,650);window.configure(bg=BG)
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.bind_all('<MouseWheel>',self.scroll_workspace,add='+')
        self.sidebar=tk.Frame(window,bg=NAV,width=176);self.sidebar.pack(side='left',fill='y');self.sidebar.pack_propagate(False)
        brand=tk.Frame(self.sidebar,bg=NAV);brand.pack(anchor='w',padx=20,pady=(27,8))
        tk.Label(brand,text='Bill',font=('Segoe UI',21,'bold'),fg='white',bg=NAV).pack(side='left')
        tk.Label(brand,text='Sync',font=('Segoe UI',21,'bold'),fg='#3988ff',bg=NAV).pack(side='left')
        tk.Label(self.sidebar,text='Invoice to Tally',font=('Segoe UI',9),fg='#b5c3da',bg=NAV).pack(anchor='w',padx=22,pady=(0,24))
        for label,command,icon in [('Invoices',self.show_invoices,'document'),('Dashboard',self.show_dashboard,'bars'),('Review',self.review,'check'),('Tally',self.import_tally,'transfer'),('Clients',self.manage_clients,'person'),('Settings',self.settings,'settings')]:
            ActionButton(self.sidebar,text=label,command=command,icon=icon,style='NavActive.TButton' if label=='Invoices' else 'Nav.TButton').pack(fill='x',padx=10,pady=4)
        tk.Label(self.sidebar,text='Tally masters: review copy',font=('Segoe UI',8),fg='#b5c3da',bg=NAV,wraplength=145,justify='left').pack(side='bottom',anchor='w',padx=20,pady=20)
        # Scrollable presentation: the inherited table/controller retains its IDs and values.
        outer=ttk.Frame(window);outer.pack(side='left',fill='both',expand=True)
        self.canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=self.canvas.yview);scrollbar.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=scrollbar.set);self.canvas.pack(fill='both',expand=True)
        self.content=ttk.Frame(self.canvas,padding=(18,16));self.content_id=self.canvas.create_window((0,0),window=self.content,anchor='nw')
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.content_id,width=event.width))
        self.content.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.content.columnconfigure(0,weight=1)
        header=ttk.Frame(self.content);header.grid(row=0,column=0,sticky='ew',pady=(0,12))
        title=ttk.Frame(header);title.pack(side='left')
        ttk.Label(title,text='Invoice workspace',font=('Segoe UI',21,'bold')).pack(anchor='w')
        ttk.Label(title,text='Upload, review and import your invoices',foreground=MUTED).pack(anchor='w',pady=(3,0))
        self.test_badge=ttk.Label(header,text='  Test workspace  ',padding=(8,5),background='#fff5de',foreground='#915400');self.test_badge.pack(side='right')
        self.folder_label=ttk.Label(header,text='')
        upload=self.card(1);upload.columnconfigure(0,weight=2,uniform='upload');upload.columnconfigure(1,weight=3,uniform='upload')
        left=ttk.Frame(upload,style='Card.TFrame');left.grid(row=0,column=0,sticky='ew',padx=(0,20))
        ttk.Label(left,text='Client',style='Card.TLabel').pack(anchor='w',pady=(0,7))
        selection=ttk.Frame(left,style='Card.TFrame');selection.pack(fill='x',pady=(0,12))
        self.client_picker=ttk.Combobox(selection,textvariable=self.client_display,state='readonly',style='Client.TCombobox',font=('Segoe UI',10),width=15)
        self.client_picker.pack(side='left',fill='both',expand=True)
        self.client_picker.bind('<<ComboboxSelected>>',lambda event:self.client_changed())
        ActionButton(selection,text='New client',command=self.add_client,icon='person',style='Soft.TButton').pack(side='left',padx=(8,0))
        ActionButton(left,text='Upload invoices',style='Upload.TButton',icon='upload',command=self.upload).pack(fill='x')
        ttk.Label(left,text='PDF · PNG · JPG · JPEG',style='Muted.TLabel').pack(anchor='center',pady=(8,0))
        self.drop=tk.Canvas(upload,width=1,height=170 if window.winfo_screenheight()<900 else 190,bg='white',highlightthickness=0,cursor='hand2')
        self.drop.grid(row=0,column=1,sticky='nsew')
        self.drop.bind('<Configure>',self.draw_drop);self.drop.bind('<Button-1>',lambda event:self.upload())
        self.drop_supported=False
        try:
            from tkinterdnd2 import DND_FILES
            self.drop.drop_target_register(DND_FILES);self.drop.dnd_bind('<<Drop>>',self.drop_files);self.drop_supported=True
        except (ImportError,AttributeError,tk.TclError):pass
        stats=ttk.Frame(self.content);stats.grid(row=2,column=0,sticky='ew',pady=(0,9));self.count_labels=[]
        for i,(label,tint,accent,icon) in enumerate([('Uploaded invoices','#eef5ff',BLUE,'document'),('Awaiting processing','#fff9ed','#a86b08','clock'),('Needs review','#fff2f5','#cf3356','alert'),('XML ready','#eefaf4','#188553','check')]):
            stats.columnconfigure(i,weight=1,uniform='stats')
            card=RoundedCard(stats,fill=tint,border={'document':'#cfe0ff','clock':'#f1e0b9','alert':'#f6d5df','check':'#ceeada'}[icon],minheight=72)
            card.grid(row=0,column=i,sticky='ew',padx=(0,10 if i<3 else 0))
            glyph=tk.Canvas(card.panel,width=36,height=38,bg=tint,highlightthickness=0);glyph.pack(side='left',padx=(0,9))
            draw_icon(glyph,icon,8,9,21,accent)
            texts=tk.Frame(card.panel,bg=tint);texts.pack(side='left',fill='x',expand=True)
            tk.Label(texts,text=label,font=('Segoe UI',9),bg=tint,fg=accent,anchor='w').pack(anchor='w')
            count=tk.Label(texts,text='0',font=('Segoe UI',17),bg=tint,fg=INK,anchor='w');count.pack(anchor='w');self.count_labels.append(count)
        self.toolbar=self.card(3);self.toolbar.columnconfigure(0,weight=1,uniform='action');self.toolbar.columnconfigure(2,weight=1,uniform='action')
        self.processing_group=ttk.Frame(self.toolbar,style='Card.TFrame');self.processing_group.grid(row=0,column=0,sticky='nw')
        ttk.Label(self.processing_group,text='PROCESS INVOICES',style='Section.TLabel').pack(anchor='w',pady=(0,7))
        process=ttk.Frame(self.processing_group,style='Card.TFrame');process.pack(anchor='w')
        self.process_menu=tk.Menu(window,tearoff=False)
        self.process_menu.add_command(label='Process selected invoices',command=self.analyse_selected)
        self.process_menu.add_command(label='Process all client invoices',command=lambda:self.read_gemini_batch('Groq'))
        self.process_menu.add_command(label='Process this invoice',command=self.analyse_one_pdf)
        ActionButton(process,text='Process selected',command=self.analyse_selected,style='Primary.TButton').pack(side='left')
        self.process_more=ActionButton(process,text='⌄',command=self.show_process_menu,style='Primary.TButton',width=25)
        self.process_more.pack(side='left',padx=(2,7))
        ActionButton(process,text='Process this invoice',command=self.analyse_one_pdf).pack(side='left',padx=(0,7))
        ActionButton(process,text='Stop',command=self.stop_ai,style='Stop.TButton').pack(side='left')
        ttk.Separator(self.toolbar,orient='vertical').grid(row=0,column=1,sticky='ns',padx=14)
        self.tally_group=ttk.Frame(self.toolbar,style='Card.TFrame');self.tally_group.grid(row=0,column=2,sticky='nw')
        ttk.Label(self.tally_group,text='TALLY & XML',style='Section.TLabel').pack(anchor='w',pady=(0,7))
        tally_actions=ttk.Frame(self.tally_group,style='Card.TFrame');tally_actions.pack(anchor='w')
        ActionButton(tally_actions,text='Import to Tally',command=self.import_tally,style='Primary.TButton').pack(side='left',padx=(0,7))
        ActionButton(tally_actions,text='Read Tally masters',command=self.import_masters_from_tally).pack(side='left',padx=(0,7))
        ActionButton(tally_actions,text='View XML',command=self.view_xml,style='Text.TButton').pack(side='left',padx=(0,7))
        ActionButton(tally_actions,text='',icon='folder',width=34,command=self.open_output).pack(side='left')
        self.selection_label=ttk.Label(self.toolbar,text='No invoice selected · AI runs only when you choose Process.',style='Muted.TLabel')
        self.selection_label.grid(row=1,column=0,columnspan=3,sticky='w',pady=(9,0))
        workspace=self.card(4);workspace.columnconfigure(0,weight=1)
        tools=ttk.Frame(workspace,style='Card.TFrame');tools.grid(row=0,column=0,sticky='ew',pady=(0,10))
        ttk.Label(tools,text='Invoices',font=('Segoe UI',14,'bold'),style='Card.TLabel').pack(side='left')
        ActionButton(tools,text='Refresh',icon='refresh',command=self.start).pack(side='right',padx=(8,0))
        ttk.Combobox(tools,textvariable=self.filter_status,values=['All statuses','Awaiting processing','Needs review','XML prepared'],state='readonly',width=18).pack(side='right',padx=(8,0),ipady=5)
        search=ttk.Frame(tools,style='Card.TFrame');search.pack(side='right')
        ttk.Label(search,text='Search ',style='Muted.TLabel').pack(side='left')
        ttk.Entry(search,textvariable=self.search,width=24).pack(side='left',ipady=5)
        table_frame=ttk.Frame(workspace,style='Card.TFrame');table_frame.grid(row=1,column=0,sticky='nsew')
        self.table=ttk.Treeview(table_frame,columns=('client','invoice','seller','total','quantity_unit','status','export_country','refund_estimate'),displaycolumns=('invoice','client','seller','export_country','quantity_unit','total','refund_estimate','status'),show='headings',height=5 if window.winfo_screenheight()<900 else 7)
        for field,label,width in [('client','Client',100),('invoice','Invoice number',175),('seller','Seller',220),('total','Total (₹)',115),('quantity_unit','Quantity / unit',200),('status','Status',190),('export_country','Export country',145),('refund_estimate','Potential IGST refund (₹)',235)]:
            self.table.heading(field,text=label);self.table.column(field,width=width,minwidth=80,anchor='e' if field=='total' else 'w')
        self.table.grid(row=0,column=0,sticky='nsew');table_frame.columnconfigure(0,weight=1)
        ybar=ttk.Scrollbar(table_frame,orient='vertical',command=self.table.yview);ybar.grid(row=0,column=1,sticky='ns')
        xbar=ttk.Scrollbar(table_frame,orient='horizontal',command=self.table.xview);xbar.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.table.bind('<<TreeviewSelect>>',self.details);self.table.bind('<Control-a>',self.select_all)
        self.table.bind('<Double-1>',lambda event:self.review());self.table.bind('<Return>',lambda event:self.review())
        self.table.bind('<Button-3>',self.invoice_menu)
        self.table.tag_configure('even',background='#ffffff');self.table.tag_configure('odd',background='#f7faff')
        lower=ttk.Frame(workspace,style='Card.TFrame');lower.grid(row=2,column=0,sticky='ew',pady=(8,0))
        ttk.Label(lower,text='Double-click an invoice to view or edit details',style='Muted.TLabel').pack(side='left')
        ActionButton(lower,text='Refund review',command=self.export_refund_review,style='Text.TButton').pack(side='left',padx=14)
        self.list_count=ttk.Label(lower,text='0 invoices',style='Muted.TLabel');self.list_count.pack(side='right')
        activity=self.card(5);activity.columnconfigure(1,weight=1)
        ttk.Label(activity,text='Activity',style='Heading.TLabel').grid(row=0,column=0,padx=(0,14),sticky='w')
        self.status=ActivityLabel(activity,self,text='No AI requests running. Upload invoices to get started.',style='Muted.TLabel',wraplength=700)
        self.status.grid(row=0,column=1,sticky='ew')
        self.status.bind('<Configure>',lambda event:self.status.configure(wraplength=max(250,event.width)))
        ActionButton(activity,text='View history',command=self.activity_history,style='Text.TButton').grid(row=0,column=2,padx=(12,0))
        self.detail=tk.Text(window,wrap='word',font=('Segoe UI',10))
        self.search.trace_add('write',lambda *args:self.apply_filter())
        self.filter_status.trace_add('write',lambda *args:self.apply_filter())
        self.refresh_clients();window.after(0,self.start);window.after(200,self.tick)

    def scroll_workspace(self,event):
        if event.widget.winfo_toplevel()!=self.window or isinstance(event.widget,(ttk.Treeview,tk.Text,ttk.Combobox)):
            return
        self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')

    def card(self,row):
        card=RoundedCard(self.content,fill='white',border=BORDER)
        card.grid(row=row,column=0,sticky='ew',pady=(0,9))
        return card.panel

    def heading(self,parent,text):
        ttk.Label(parent,text=text,style='Heading.TLabel').pack(anchor='w')
        ttk.Separator(parent,orient='horizontal').pack(fill='x',pady=(5,0))

    def draw_drop(self,event=None):
        self.drop.delete('all');width=self.drop.winfo_width();height=self.drop.winfo_height()
        rounded_box(self.drop,2,2,width-3,height-3,r=18,fill='#f0f6ff',outline='#b9d2ff')
        rounded_box(self.drop,11,11,width-12,height-12,r=16,fill='#f0f6ff',outline='#8fb7fb',dash=(4,4))
        draw_icon(self.drop,'upload',width/2-17,height/2-58,34,BLUE)
        self.drop.create_text(width/2,height/2-5,text='Drag invoices here',font=('Segoe UI',12,'bold'),fill=INK)
        self.drop.create_text(width/2,height/2+23,text='or click to browse files',font=('Segoe UI',10),fill=MUTED)
        self.drop.create_text(width/2,height/2+48,text='PDF · PNG · JPG · JPEG',font=('Segoe UI',9),fill=MUTED)

    def refresh_clients(self):
        from Common_Rules.engine import discover
        try:
            values=['All clients']+[folder.name for folder in discover(self.root)]
            selected=self.client_scope.get().removeprefix('Folder: ')
            if selected not in values:values.append(selected)
            self.client_picker.config(values=values);self.client_display.set(selected)
        except OSError:pass

    def client_changed(self):
        if self.busy:
            self.client_display.set(self.client_scope.get().removeprefix('Folder: '));return
        selected=self.client_display.get()
        self.client_scope.set(selected if selected=='All clients' else 'Folder: '+selected)
        self.reset();self.start()

    def choose(self):
        if self.busy:return
        super().choose()
        config=self._configuration_root/'.invoice_app'/'billsync_ui_settings.json'
        try:
            config.parent.mkdir(parents=True,exist_ok=True)
            temporary=config.with_suffix('.tmp');temporary.write_text(json.dumps({'storage':str(self.root)}),encoding='utf-8');temporary.replace(config)
        except OSError as exc:messagebox.showwarning('Storage preference','The current storage works, but its location could not be remembered: '+str(exc))
        self.start()

    def add_client(self):
        if self.busy:return
        name=simpledialog.askstring('Add client','Client name:',parent=self.window)
        if name is None:return
        try:client_folder(self.root,name,create=True)
        except (ValueError,OSError) as exc:messagebox.showerror('Add client',str(exc));return
        self.client_scope.set('Folder: '+name.strip());self.refresh_clients();self.start()

    def upload(self):
        if self.busy:return
        paths=filedialog.askopenfilenames(parent=self.window,title='Upload invoices',filetypes=[('Invoices','*.pdf *.PDF *.png *.PNG *.jpg *.JPG *.jpeg *.JPEG')])
        if paths:self.upload_paths(paths)

    def drop_files(self,event):
        if not self.busy:self.upload_paths(self.window.tk.splitlist(event.data))
        return getattr(event,'action','copy')

    def upload_paths(self,paths):
        if self.busy:return
        client=self.client_scope.get()
        if client=='All clients':
            messagebox.showinfo('Upload invoices','Select a client first, or choose New client.');return
        self.busy=True;root=self.root;client=client.removeprefix('Folder: ')
        def worker():
            try:report=upload_documents(root,client,paths)
            except Exception as exc:report={'uploaded':[],'reused':[],'errors':[{'name':'Upload','error':str(exc)}]}
            self.events.put(('upload_finished',report))
        threading.Thread(target=worker,daemon=True).start()

    def tick(self):
        # New intake events are consumed here; engine events go to the exact original handler.
        if not self.events.empty():
            item=self.events.get_nowait()
            if item[0]=='upload_finished':
                self.busy=False;report=item[1]
                self.status.config(text=f'{len(report["uploaded"])} invoices uploaded; {len(report["reused"])} duplicates reused. No AI requests sent.')
                if report['errors']:messagebox.showerror('Some files were not uploaded','\n'.join(r['name']+': '+r['error'] for r in report['errors']))
                self.start()
            else:
                with self.events.mutex:
                    self.events.queue.appendleft(item);self.events.not_empty.notify()
        # Detached filter rows must be visible to the inherited table-clear step.
        # Restore within this callback, then reapply the filter before Tk redraws.
        visible=set(self.table.get_children())
        for index in range(len(self.records)):
            iid=str(index)
            if iid not in visible and self.table.exists(iid):self.table.reattach(iid,'','end')
        super().tick()
        if not self.closing:
            self.apply_filter();self.update_summary()

    def details(self,event=None):
        super().details(event)
        self.selection_label.config(text=f'{len(self.table.selection())} selected · AI runs only when you choose Process.')

    def show_process_menu(self):
        self.process_menu.tk_popup(self.process_more.winfo_rootx(),self.process_more.winfo_rooty()+self.process_more.winfo_height())

    def invoice_menu(self,event):
        iid=self.table.identify_row(event.y)
        if not iid:return
        if iid not in self.table.selection():self.table.selection_set(iid)
        self.table.focus(iid);self.details()
        menu=tk.Menu(self.window,tearoff=False)
        for label,command in [('View / edit details',self.review),('Tally master assignments',self.view_master_matches),('Export refund review',self.export_refund_review),('Open original invoice',self.open_source),('View prepared XML',self.view_xml),('Open XML folder',self.open_output)]:menu.add_command(label=label,command=command)
        menu.tk_popup(event.x_root,event.y_root)

    def update_summary(self):
        counts=[len(self.records),sum(bool(r.get('listing_only')) for r in self.records),sum(bool(r.get('errors') or r.get('tally_review_warnings')) for r in self.records),sum(bool(r.get('output_path')) for r in self.records)]
        for label,value in zip(self.count_labels,counts):label.config(text=str(value))
        self.test_badge.config(text='  Test workspace  ' if self.demo.get() else '  Real invoices  ',background='#fff5de' if self.demo.get() else '#e5f6ed')
        if hasattr(self,'list_count'):self.list_count.config(text=f'{len(self.table.get_children())} of {len(self.records)} invoices')

    def apply_filter(self):
        if not hasattr(self,'table'):return
        text=self.search.get().casefold();status=self.filter_status.get()
        for i,row in enumerate(self.records):
            iid=str(i)
            if not self.table.exists(iid):continue
            inv=row.get('invoice') or {};haystack=' '.join(str(inv.get(f,'')) for f in ('number','seller_name','buyer_name'))+' '+Path(row['path']).name
            match=(not text or text in haystack.casefold())
            if status=='Awaiting processing':match=match and bool(row.get('listing_only'))
            elif status=='Needs review':match=match and bool(row.get('errors') or row.get('tally_review_warnings'))
            elif status=='XML prepared':match=match and bool(row.get('output_path'))
            info=refund_summary(row)
            country=info['country'] or ('Required' if info['export'] else '—')
            display=info['display']
            if info['export']:
                key=review_key(row)
                if key not in self.refund_reviews:
                    try:self.refund_reviews[key]=load_refund_review(self.root,row)
                    except ValueError:self.refund_reviews[key]={'status':'Review file error'}
                saved=self.refund_reviews[key]
                if saved:
                    if saved['status']=='Not eligible':display='— · Not eligible'
                    elif saved['status']=='Claimed' and saved.get('claim_amount'):display=format(refund_amount(saved['claim_amount']),',.2f')+' · Claimed'
                    else:display=(format(refund_amount(info['estimate']),',.2f')+' · ' if info['estimate'] else '')+saved['status']
            self.table.set(iid,'export_country',country);self.table.set(iid,'refund_estimate',display)
            self.table.item(iid,tags=('even' if i%2==0 else 'odd',))
            if match:self.table.reattach(iid,'','end')
            else:
                self.table.selection_remove(iid);self.table.detach(iid)

    def refresh_activity(self):
        if hasattr(self,'activity_text'):self.activity_text.config(text='\n'.join(time+'  '+message for time,message in self.activity[-2:]))

    def activity_history(self):
        top=tk.Toplevel(self.window);top.title('Activity history and selected invoice details');top.geometry('1000x650')
        content=tk.Text(top,wrap='word',font=('Segoe UI',10));content.pack(fill='both',expand=True)
        content.insert('end','\n'.join(time+'  '+message for time,message in self.activity)+'\n\nSELECTED INVOICE DETAILS\n'+self.detail.get('1.0','end'))
        content.config(state='disabled')

    def export_refund_review(self):
        open_refund_review(self)

    def import_masters_from_tally(self):
        if self.busy:
            messagebox.showinfo('Tally masters','Finish the current operation before reading Tally masters.',parent=self.window);return
        selected=self.client_scope.get()
        client=selected.removeprefix('Folder: ') if selected!='All clients' else (self.selected() or {}).get('client')
        if not client:
            messagebox.showinfo('Tally masters','Choose a client or select its invoice before importing Tally masters.',parent=self.window);return
        def saved(snapshot,path):
            from Common_Rules.tally_master_matching import bind_snapshot
            bind_snapshot(self.root,client,path)
            counts=snapshot['counts']
            self.status.config(text=f"Masters selected for {client}: {counts['ledgers']} ledgers, {counts['stock_items']} items, {counts['units']} units from {snapshot['company']}. Process invoices to match with AI; no AI call sent now.")
        TallyMasterDialog(self.window,self.root,on_saved=saved,client=client)

    def view_master_matches(self):
        row=self.selected()
        if not row:return
        audit=row.get('tally_master_matching')
        if not audit:
            messagebox.showinfo('Tally master assignments','No master-matching result for this invoice. Select imported masters for its client, then process the invoice. Existing creation is the fallback.',parent=self.window);return
        top=tk.Toplevel(self.window);top.title('Tally master assignments');top.geometry('880x460')
        panel=ttk.Frame(top,padding=18);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Company: '+audit['company']).pack(anchor='w')
        ttk.Label(panel,text='Buyer ledger: '+str(audit['party'] or 'Current creation method')).pack(anchor='w',pady=8)
        table=ttk.Treeview(panel,columns=('invoice_item','stock','unit'),show='headings')
        for key,title in [('invoice_item','Invoice item'),('stock','Assigned stock item'),('unit','Assigned unit')]:table.heading(key,text=title);table.column(key,width=260)
        table.pack(fill='both',expand=True)
        items=(row.get('invoice') or {}).get('items',[])
        for entry in audit['items']:
            table.insert('','end',values=(items[entry['index']].get('name',''),entry['stock'] or 'Current creation method',entry['unit'] or 'Current creation method'))
        ttk.Label(panel,text='Invoice names and amounts are retained. Existing master references are company-specific.',wraplength=820).pack(anchor='w',pady=10)

    def view_xml(self):
        row=self.selected()
        folder=Path(row['output_path']) if row and row.get('output_path') else Path(row['company_path'])/'imports' if row and row.get('company_path') else None
        if folder is None or not folder.is_dir():messagebox.showinfo('View XML','Select an invoice with prepared XML first.');return
        top=tk.Toplevel(self.window);top.title('Prepared XML — read only');top.geometry('1050x700')
        tabs=ttk.Notebook(top);tabs.pack(fill='both',expand=True)
        for name in ('Units.xml','Masters.xml','Sales_Vouchers.xml'):
            frame=ttk.Frame(tabs);tabs.add(frame,text=name);content=tk.Text(frame,wrap='none',font=('Consolas',10));content.pack(fill='both',expand=True)
            path=folder/name
            try:body=path.read_text(encoding='utf-8-sig') if path.is_file() else 'Not generated.'
            except OSError as exc:body=str(exc)
            content.insert('end',body);content.config(state='disabled')

    def settings(self):
        top=tk.Toplevel(self.window);top.title('Settings');top.geometry('560x420')
        panel=ttk.Frame(top,padding=22);panel.pack(fill='both',expand=True)
        for title,var in [('Test invoices (fictional data)',self.demo),('Auto-fill units',self.auto_units),('Watch for new PDFs (list only)',self.auto)]:ttk.Checkbutton(panel,text=title,variable=var,command=self.reset).pack(anchor='w',pady=9)
        ttk.Separator(panel).pack(fill='x',pady=12)
        ActionButton(panel,text='Re-read selected PDFs',command=self.reread).pack(fill='x',pady=3)
        ActionButton(panel,text='Save supplier layout',command=self.supplier_layout).pack(fill='x',pady=3)
        ActionButton(panel,text='Use existing invoice storage…',command=self.choose).pack(fill='x',pady=3)
        ttk.Label(panel,text='Storage: '+str(self.root),wraplength=490).pack(anchor='w',pady=8)
        ttk.Label(panel,text='AI and accounting defaults are unchanged. Uploading never starts AI.',wraplength=490).pack(anchor='w')

    def manage_clients(self):
        top=tk.Toplevel(self.window);top.title('Clients');top.geometry('420x400')
        ttk.Label(top,text='Select a client in the workspace, or add a new client.',wraplength=360,padding=20).pack()
        ActionButton(top,text='Add client',command=self.add_client).pack(pady=8)
        for name in self.client_picker.cget('values'):
            if name!='All clients':ttk.Label(top,text=name.removeprefix('Folder: '),padding=5).pack(anchor='w',padx=20)

    def show_dashboard(self):
        top=tk.Toplevel(self.window);top.title('Dashboard');top.geometry('480x300')
        for title,label in zip(('Uploaded invoices','Awaiting processing','Needs review','XML prepared'),self.count_labels):ttk.Label(top,text=title+': '+label.cget('text'),padding=12,font=('Segoe UI',13)).pack(anchor='w')
        ttk.Label(top,text='Counts reflect listed records. XML preparation is not Tally import.',wraplength=420,padding=12).pack(anchor='w')

    def show_invoices(self):self.canvas.yview_moveto(0)


def launch(data_root=None):
    try:
        from tkinterdnd2 import TkinterDnD
        window=TkinterDnD.Tk()
    except ImportError:window=tk.Tk()
    BillSyncApp(window,data_root=data_root);window.mainloop()


if __name__=='__main__':launch()

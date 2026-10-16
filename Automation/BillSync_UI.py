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
from BillSync_Controls import ActionButton,rounded_box
from Tally_Master_Dialog import TallyMasterDialog

BG='#f3f6fc';NAV='#101d30';BLUE='#2460ed';INK='#17243a';MUTED='#65748b';BORDER='#dbe3f0'
UI_VERSION='BillSync UI 1.1'


class ActivityLabel(ttk.Label):
    def __init__(self,parent,app,**kwargs):
        self.app=app;super().__init__(parent,**kwargs)
    def config(self,**kwargs):
        text=kwargs.get('text')
        if text and (not self.app.activity or self.app.activity[-1][1]!=text):
            self.app.activity.append((datetime.now().strftime('%H:%M:%S'),str(text)))
            self.app.activity=self.app.activity[-500:]
            self.app.refresh_activity()
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
        self.records=[];self.busy=False;self.ai_stop=None;self.events=queue.Queue()
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
        self.style.configure('TButton',padding=(9,6),background='white',bordercolor=BORDER,foreground=INK,relief='solid',borderwidth=1,focusthickness=0)
        self.style.map('TButton',background=[('active','#e9f0ff')])
        self.style.configure('Primary.TButton',background=BLUE,foreground='white',bordercolor=BLUE)
        self.style.map('Primary.TButton',background=[('active','#164cd0')],foreground=[('active','white')])
        self.style.configure('Upload.TButton',font=('Segoe UI',11),padding=(14,10),background=BLUE,foreground='white')
        self.style.map('Upload.TButton',background=[('active','#164cd0')])
        self.style.configure('Stop.TButton',foreground='#c62828',background='#fff4f4',bordercolor='#ed7777')
        self.style.configure('Client.TCombobox',font=('Segoe UI',10),padding=5,fieldbackground='white')
        self.style.configure('Treeview',background='white',fieldbackground='white',font=('Segoe UI',10),rowheight=30,bordercolor=BORDER)
        self.style.configure('Treeview.Heading',font=('Segoe UI',9),background='#f4f7fc',padding=(7,7))
        self.style.map('TCombobox',fieldbackground=[('readonly','white')],selectbackground=[('readonly','white')],selectforeground=[('readonly',INK)])
        self.style.map('Treeview',background=[('selected','#e1ebff')],foreground=[('selected',INK)])
        window.title(f'BillSync — Invoice to Tally | {UI_VERSION} | {APP_VERSION}')
        width=min(1500,max(1100,window.winfo_screenwidth()-50));height=min(1000,max(650,window.winfo_screenheight()-100))
        window.geometry(f'{width}x{height}');window.minsize(1100,650);window.configure(bg=BG)
        window.protocol('WM_DELETE_WINDOW',self.close)
        window.bind_all('<MouseWheel>',self.scroll_workspace,add='+')
        self.sidebar=tk.Frame(window,bg=NAV,width=190);self.sidebar.pack(side='left',fill='y');self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar,text='B  BillSync',font=('Segoe UI',20,'bold'),fg='white',bg=NAV,pady=24).pack(anchor='w',padx=18)
        tk.Label(self.sidebar,text='Invoice to Tally',font=('Segoe UI',10),fg='#b5c3da',bg=NAV).pack(anchor='w',padx=22,pady=(0,25))
        for label,command in [('Dashboard',self.show_dashboard),('Invoices',self.show_invoices),('Review',self.review),('Tally Import',self.import_tally),('Clients',self.manage_clients),('Settings',self.settings)]:
            tk.Button(self.sidebar,text=label,command=command,anchor='w',font=('Segoe UI',11),fg='white',bg='#203f7a' if label=='Invoices' else NAV,activebackground='#254b87',activeforeground='white',relief='flat',highlightthickness=0,borderwidth=0,padx=20,pady=11).pack(fill='x',padx=10,pady=3)
        # Main scroll area keeps controls usable at laptop resolutions/high DPI.
        outer=ttk.Frame(window);outer.pack(side='left',fill='both',expand=True)
        self.canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=self.canvas.yview);scrollbar.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=scrollbar.set);self.canvas.pack(fill='both',expand=True)
        self.content=ttk.Frame(self.canvas,padding=14);self.content_id=self.canvas.create_window((0,0),window=self.content,anchor='nw')
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.content_id,width=event.width))
        self.content.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.content.columnconfigure(0,weight=1)
        header=ttk.Frame(self.content);header.grid(row=0,column=0,sticky='ew',pady=(0,12))
        ttk.Label(header,text='Invoices',font=('Segoe UI',21,'bold')).pack(side='left')
        self.test_badge=ttk.Label(header,text='  Test mode · Fictional data  ',background='#fff0bf',foreground='#915400');self.test_badge.pack(side='left',padx=16)
        self.folder_label=ttk.Label(header,text='')  # Existing controller compatibility; paths stay out of the workspace.
        upload=self.card(1);upload.columnconfigure(0,weight=3,uniform='upload');upload.columnconfigure(1,weight=2,uniform='upload')
        left=ttk.Frame(upload,style='Card.TFrame');left.grid(row=0,column=0,sticky='nsew',padx=(0,20))
        ttk.Label(left,text='Client documents',style='Heading.TLabel').pack(anchor='w',pady=(0,8))
        client_title=ttk.Frame(left,style='Card.TFrame');client_title.pack(fill='x')
        ttk.Label(client_title,text='Client',style='Muted.TLabel').pack(side='left')
        ActionButton(client_title,text='Add client',command=self.add_client).pack(side='right')
        selection=ttk.Frame(left,style='Card.TFrame');selection.pack(fill='x',pady=6)
        self.client_picker=ttk.Combobox(selection,textvariable=self.client_display,state='readonly',style='Client.TCombobox',font=('Segoe UI',10))
        self.client_picker.pack(side='left',fill='x',expand=True)
        self.client_picker.bind('<<ComboboxSelected>>',lambda event:self.client_changed())
        ActionButton(left,text='↑  Upload invoices',style='Upload.TButton',command=self.upload).pack(fill='x',pady=6)
        ttk.Label(left,text='PDF, PNG, JPG, JPEG',style='Muted.TLabel').pack(anchor='center')
        self.drop=tk.Canvas(upload,width=1,height=150,bg='white',highlightthickness=0,cursor='hand2')
        self.drop.grid(row=0,column=1,sticky='nsew')
        self.drop.bind('<Configure>',self.draw_drop)
        self.drop.bind('<Button-1>',lambda event:self.upload())
        self.drop_supported=False
        try:
            from tkinterdnd2 import DND_FILES
            self.drop.drop_target_register(DND_FILES);self.drop.dnd_bind('<<Drop>>',self.drop_files);self.drop_supported=True
        except (ImportError,AttributeError,tk.TclError):pass
        stats=ttk.Frame(self.content);stats.grid(row=2,column=0,sticky='ew',pady=(0,10));self.count_labels=[]
        for i,(title,tint,accent) in enumerate([('Uploaded invoices','#edf4ff',BLUE),('Awaiting processing','#fff8e6','#ba7b00'),('Needs review','#fff0f1','#d3334c'),('XML prepared','#eaf9f0','#13823e')]):
            stats.columnconfigure(i,weight=1)
            surface=tk.Canvas(stats,bg=BG,height=60,highlightthickness=0);surface.grid(row=0,column=i,sticky='ew',padx=(0,8 if i<3 else 0))
            box=tk.Frame(surface,bg=tint);item=surface.create_window(12,7,window=box,anchor='nw')
            def stat_background(event,canvas=surface,color=tint,edge=accent,window_item=item):
                canvas.delete('background');rounded_box(canvas,1,1,event.width-2,58,r=12,fill=color,outline=edge,tags='background');canvas.tag_lower('background')
                canvas.itemconfigure(window_item,width=max(20,event.width-24))
            surface.bind('<Configure>',stat_background)
            tk.Label(box,text=title,font=('Segoe UI',9),bg=tint,fg=INK).pack(anchor='w')
            count=tk.Label(box,text='0',font=('Segoe UI',15),bg=tint,fg=INK);count.pack(anchor='w');self.count_labels.append(count)
        processing=self.card(3);ttk.Label(processing,text='Invoice processing',style='Heading.TLabel').pack(anchor='w')
        buttons=ttk.Frame(processing,style='Card.TFrame');buttons.pack(fill='x',pady=6)
        for text,command,style in [('Process this invoice',self.analyse_one_pdf,'Primary.TButton'),('Process selected invoices',self.analyse_selected,'TButton'),('Process all client invoices',lambda:self.read_gemini_batch('Groq'),'TButton')]:
            ActionButton(buttons,text=text,command=command,style=style).pack(side='left',padx=(0,7))
        ActionButton(buttons,text='■  Stop processing',command=self.stop_ai,style='Stop.TButton').pack(side='right')
        notes=ttk.Frame(processing,style='Card.TFrame');notes.pack(fill='x')
        self.selection_label=ttk.Label(notes,text='No invoice selected',style='Card.TLabel');self.selection_label.pack(side='left',padx=(0,12))
        ttk.Label(notes,text='AI starts only after confirmation. Uploading uses no AI credits.',style='Muted.TLabel').pack(side='left')
        tally=self.card(4)
        line=ttk.Frame(tally,style='Card.TFrame');line.pack(fill='x',pady=6)
        ttk.Label(line,text='Tally & XML',style='Heading.TLabel').pack(side='left')
        ttk.Label(line,text='Choose the company in each action',style='Muted.TLabel').pack(side='left',padx=14)
        actions=ttk.Frame(tally,style='Card.TFrame');actions.pack(fill='x',pady=(2,8))
        ActionButton(actions,text='Import all to Tally',command=self.import_tally,style='Primary.TButton').pack(side='left',padx=(0,8))
        ActionButton(actions,text='Import masters from Tally',command=self.import_masters_from_tally).pack(side='left',padx=(0,8))
        ActionButton(actions,text='View XML',command=self.view_xml).pack(side='left',padx=(0,8))
        ActionButton(actions,text='Open XML folder',command=self.open_output).pack(side='left')
        ttk.Label(tally,text='To Tally: Units → Masters → Sales vouchers     ·     From Tally: ledgers, inventory & units for review',style='Muted.TLabel').pack(anchor='w')
        workspace=self.card(5);workspace.columnconfigure(0,weight=4,uniform='workspace');workspace.columnconfigure(1,weight=1,uniform='workspace')
        tools=ttk.Frame(workspace,style='Card.TFrame');tools.grid(row=0,column=0,sticky='ew',pady=(0,8))
        ttk.Label(tools,text='Invoice workspace',style='Heading.TLabel').pack(side='left')
        ActionButton(tools,text='Refresh list',command=self.start).pack(side='right',padx=5)
        ttk.Combobox(tools,textvariable=self.filter_status,values=['All statuses','Awaiting processing','Needs review','XML prepared'],state='readonly',width=19).pack(side='right',padx=5)
        ttk.Entry(tools,textvariable=self.search,width=25).pack(side='right')
        table_frame=ttk.Frame(workspace,style='Card.TFrame');table_frame.grid(row=1,column=0,sticky='nsew')
        self.table=ttk.Treeview(table_frame,columns=('client','invoice','seller','total','quantity_unit','status'),show='headings',height=6)
        for field,title,width in [('client','Client',90),('invoice','Invoice number',170),('seller','Seller',190),('total','Total (₹)',110),('quantity_unit','Quantity / unit',205),('status','Status',180)]:
            self.table.heading(field,text=title);self.table.column(field,width=width,minwidth=80,anchor='e' if field=='total' else 'w')
        self.table.grid(row=0,column=0,sticky='nsew');table_frame.columnconfigure(0,weight=1)
        ybar=ttk.Scrollbar(table_frame,orient='vertical',command=self.table.yview);ybar.grid(row=0,column=1,sticky='ns')
        xbar=ttk.Scrollbar(table_frame,orient='horizontal',command=self.table.xview);xbar.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        self.table.bind('<<TreeviewSelect>>',self.details);self.table.bind('<Control-a>',self.select_all);self.table.bind('<Double-1>',lambda event:self.review())
        self.selected_panel=ttk.Frame(workspace,style='Card.TFrame',padding=(14,0,0,0));self.selected_panel.grid(row=0,column=1,rowspan=2,sticky='nsew')
        ttk.Label(self.selected_panel,text='Selected invoice',style='Heading.TLabel').pack(anchor='w')
        self.selected_text=ttk.Label(self.selected_panel,text='Select an invoice to see its details.',style='Card.TLabel',wraplength=220,justify='left');self.selected_text.pack(fill='x',pady=12)
        self.selected_panel.bind('<Configure>',lambda event:self.selected_text.config(wraplength=max(130,event.width-20)))
        ActionButton(self.selected_panel,text='View invoice',command=self.open_source).pack(fill='x',pady=3)
        ActionButton(self.selected_panel,text='Review invoice',command=self.review,style='Primary.TButton').pack(fill='x',pady=3)
        activity=self.card(6);self.heading(activity,'Recent activity')
        self.status=ActivityLabel(activity,self,text='PDF listing only. Uploading never starts AI.',style='Muted.TLabel',wraplength=1150);self.status.pack(fill='x',pady=4)
        self.activity_text=ttk.Label(activity,text='',style='Muted.TLabel',wraplength=1000,justify='left');self.activity_text.pack(anchor='w')
        ActionButton(activity,text='View activity history',command=self.activity_history).pack(anchor='e',pady=(4,0))
        footer=ttk.Frame(self.content);footer.grid(row=7,column=0,sticky='ew')
        ttk.Checkbutton(footer,text='Auto-fill units',variable=self.auto_units,command=self.reset).pack(side='left')
        ActionButton(footer,text='Settings',command=self.settings).pack(side='right')
        # Keep the original controller's complete detail output in a local widget.
        self.detail=tk.Text(window,wrap='word',font=('Segoe UI',10))
        self.search.trace_add('write',lambda *args:self.apply_filter())
        self.filter_status.trace_add('write',lambda *args:self.apply_filter())
        self.refresh_clients();window.after(0,self.start);window.after(200,self.tick)

    def scroll_workspace(self,event):
        if event.widget.winfo_toplevel()!=self.window or isinstance(event.widget,(ttk.Treeview,tk.Text,ttk.Combobox)):
            return
        self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units')

    def card(self,row):
        surface=tk.Canvas(self.content,bg=BG,highlightthickness=0,height=80)
        surface.grid(row=row,column=0,sticky='ew',pady=(0,6))
        panel=ttk.Frame(surface,style='Card.TFrame',padding=10)
        item=surface.create_window(8,8,window=panel,anchor='nw')
        def redraw(event=None):
            width=max(100,surface.winfo_width());height=panel.winfo_reqheight()+16
            if int(surface.cget('height'))!=height:surface.configure(height=height)
            surface.itemconfigure(item,width=width-16)
            surface.delete('background')
            r=16;x=1;y=1;w=width-2;h=height-2
            surface.create_polygon(x+r,y,w-r,y,w,y,w,y+r,w,h-r,w,h,w-r,h,x+r,h,x,h,x,h-r,x,y+r,x,y,smooth=True,fill='white',outline=BORDER,tags='background')
            surface.tag_lower('background')
        surface.bind('<Configure>',redraw);panel.bind('<Configure>',redraw)
        return panel

    def heading(self,parent,text):
        ttk.Label(parent,text=text,style='Heading.TLabel').pack(anchor='w')
        ttk.Separator(parent,orient='horizontal').pack(fill='x',pady=(5,0))

    def draw_drop(self,event=None):
        self.drop.delete('all');width=self.drop.winfo_width();height=self.drop.winfo_height()
        rounded_box(self.drop,1,1,width-2,height-2,r=16,fill='#eff5ff',outline='#6b98ff')
        self.drop.create_text(width/2,height/2-38,text='↑',font=('Segoe UI',27),fill=BLUE)
        self.drop.create_text(width/2,height/2+1,text='Drag invoices here',font=('Segoe UI',11),fill=INK)
        self.drop.create_text(width/2,height/2+28,text='or browse files',font=('Segoe UI',9),fill=BLUE)
        self.drop.create_text(width/2,height/2+53,text='PDF, PNG, JPG and JPEG · Multiple files supported',font=('Segoe UI',9),fill=MUTED)

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
            messagebox.showinfo('Upload invoices','Select a client first, or choose Add client.');return
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
        super().tick()
        if not self.closing:
            self.update_summary();self.apply_filter()

    def details(self,event=None):
        super().details(event)
        selected=self.table.selection();self.selection_label.config(text=f'{len(selected)} invoice(s) selected')
        row=self.selected()
        if not row:return
        inv=row.get('invoice') or {}
        lines=[str(inv.get('number') or Path(row['path']).name),'', 'Seller: '+str(inv.get('seller_name') or 'Awaiting processing'),'Buyer: '+str(inv.get('buyer_name') or '—'),'Total: '+str(inv.get('total') or '—'),'Quantity / unit: '+quantity_unit_summary(inv),'',invoice_status(row)]
        warnings=list(dict.fromkeys(row.get('errors',[])+row.get('tally_review_warnings',[])))
        if warnings:lines+=['', 'Review: '+warnings[0]]
        self.selected_text.config(text='\n'.join(lines))

    def update_summary(self):
        counts=[len(self.records),sum(bool(r.get('listing_only')) for r in self.records),sum(bool(r.get('errors') or r.get('tally_review_warnings')) for r in self.records),sum(bool(r.get('output_path')) for r in self.records)]
        for label,value in zip(self.count_labels,counts):label.config(text=str(value))
        self.test_badge.config(text='  Test mode · Fictional data  ' if self.demo.get() else '  Real invoices  ',background='#fff0bf' if self.demo.get() else '#dff6e8')

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

    def import_masters_from_tally(self):
        if self.busy:
            messagebox.showinfo('Tally masters','Finish the current operation before reading Tally masters.',parent=self.window);return
        def saved(snapshot,path):
            counts=snapshot['counts']
            self.status.config(text=f"Tally review copy saved: {counts['ledgers']} ledgers, {counts['stock_items']} inventory items, {counts['units']} units from {snapshot['company']}. Invoice processing unchanged.")
        TallyMasterDialog(self.window,self.root,on_saved=saved)

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

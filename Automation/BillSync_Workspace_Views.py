"""Client and dashboard presentation. Listing never reads invoice contents."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from BillSync_Theme import header,PRIMARY,INK,MUTED,BG
from BillSync_Controls import RoundedCard


def shell(app,title,subtitle,width=860,height=610):
    top=tk.Toplevel(app.window);top._billsync_custom=True;top.title(title);top.configure(bg='white');top.geometry(f'{width}x{height}');top.transient(app.window)
    header(top,title,subtitle)
    return top


def ask_client_name(app):
    top=shell(app,'New client','Create a dedicated space for this client’s documents.',580,360);top.resizable(False,False)
    panel=ttk.Frame(top,style='Dialog.TFrame',padding=(24,0,24,22));panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='Client name',style='Dialog.TLabel',foreground=MUTED).pack(anchor='w',pady=(10,8))
    value=tk.StringVar();entry=ttk.Entry(panel,textvariable=value);entry.pack(fill='x')
    ttk.Label(panel,text='Invoices and saved reviews stay organised by client.',style='Dialog.TLabel',foreground=MUTED).pack(anchor='w',pady=14)
    result=[None]
    def done(name):result[0]=name;top.destroy()
    footer=ttk.Frame(panel,style='Dialog.TFrame');footer.pack(side='bottom',fill='x')
    ttk.Button(footer,text='Create client',style='Primary.TButton',command=lambda:done(value.get())).pack(side='right')
    ttk.Button(footer,text='Cancel',command=lambda:done(None)).pack(side='right',padx=10)
    top.protocol('WM_DELETE_WINDOW',lambda:done(None));top.bind('<Escape>',lambda e:done(None));entry.bind('<Return>',lambda e:done(value.get()))
    previous=top.grab_current();top.grab_set();entry.focus_set();top.wait_window()
    if previous and previous.winfo_exists():previous.grab_set()
    return result[0]


def clients_view(app):
    top=shell(app,'Clients','A dedicated workspace for every business you manage.');top.minsize(700,480)
    panel=ttk.Frame(top,style='Dialog.TFrame',padding=(24,0,24,24));panel.pack(fill='both',expand=True)
    tools=ttk.Frame(panel,style='Dialog.TFrame');tools.pack(fill='x',pady=(0,16))
    search=tk.StringVar();entry=ttk.Entry(tools,textvariable=search,width=32);entry.pack(side='left',fill='x',expand=True)
    ttk.Label(tools,text='Search by client name',style='Dialog.TLabel',foreground=MUTED).pack(side='left',padx=12)
    table=ttk.Treeview(panel,columns=('name','documents','state'),show='headings',selectmode='browse')
    for name,label,width in [('name','CLIENT NAME',360),('documents','DOCUMENTS',130),('state','WORKSPACE',180)]:table.heading(name,text=label);table.column(name,width=width)
    def refresh(*args):
        table.delete(*table.get_children())
        for name in app.client_picker.cget('values'):
            if name=='All clients' or search.get().casefold() not in str(name).casefold():continue
            folder=app.root/str(name)
            count=sum(1 for p in folder.glob('*.pdf') if p.is_file()) if folder.is_dir() else 0
            table.insert('','end',values=(name,str(count),'Selected' if app.client_display.get()==name else 'Ready'))
    def create():app.add_client();refresh()
    ttk.Button(tools,text='+ New client',style='Primary.TButton',command=create).pack(side='right')
    table.pack(fill='both',expand=True);refresh();search.trace_add('write',refresh)
    bottom=ttk.Frame(panel,style='Dialog.TFrame');bottom.pack(fill='x',pady=(18,0))
    ttk.Label(bottom,text='Select a client to open its invoice workspace.',style='Dialog.TLabel',foreground=MUTED).pack(side='left')
    def open_client(event=None):
        chosen=table.selection()
        if not chosen:return
        app.client_display.set(table.item(chosen[0],'values')[0]);app.client_changed();top.destroy()
    ttk.Button(bottom,text='Open workspace',style='Primary.TButton',command=open_client).pack(side='right')
    table.bind('<Double-1>',open_client);table.bind('<Return>',open_client)
    top.client_table=table;top.client_search=search


def dashboard_view(app):
    top=shell(app,'Workspace overview','A clear view of your invoice workflow.',840,520)
    panel=ttk.Frame(top,padding=(24,4,24,24),style='Dialog.TFrame');panel.pack(fill='both',expand=True)
    for i,(label,value,color) in enumerate(zip(('Uploaded invoices','Awaiting processing','Needs review','XML ready'),app.count_labels,('#315ee7','#a27730','#b56868','#386fc1'))):
        panel.columnconfigure(i%2,weight=1)
        card=RoundedCard(panel,fill='#f2f5fc',border='#c7d3e9',minheight=120);card.grid(row=i//2,column=i%2,sticky='ew',padx=(0,12),pady=(0,12))
        tk.Label(card.panel,text=label,font=('Segoe UI',11),bg='#f2f5fc',fg=MUTED).pack(anchor='w',pady=5)
        tk.Label(card.panel,text=value.cget('text'),font=('Segoe UI',29),bg='#f2f5fc',fg=color).pack(anchor='w')
    ttk.Label(panel,text='Counts reflect the current list. Prepared XML is ready for review; import results come from Tally.',style='Dialog.TLabel',foreground=MUTED,wraplength=740).grid(row=2,column=0,columnspan=2,sticky='w',pady=12)


def settings_view(app):
    top=shell(app,'Settings','Your preferences. Your processing decisions.',790,650)
    panel=ttk.Frame(top,style='Dialog.TFrame',padding=(24,0,24,24));panel.pack(fill='both',expand=True)
    tabs=ttk.Notebook(panel);tabs.pack(fill='both',expand=True)
    preferences=ttk.Frame(tabs,style='Dialog.TFrame',padding=(4,20));tabs.add(preferences,text='Preferences')
    for title,note,var in [('Test invoices (fictional data)','Keep enabled for sample documents; turn off for real invoices.',app.demo),('Auto-fill units','Retain the existing unit inference and review workflow.',app.auto_units),('Watch for new PDFs (list only)','New files appear in the list. AI runs only when you choose Process.',app.auto)]:
        row=ttk.Frame(preferences,style='Dialog.TFrame',padding=(12,10));row.pack(fill='x',pady=3)
        ttk.Checkbutton(row,text=title,variable=var,command=app.reset).pack(anchor='w')
        ttk.Label(row,text=note,style='Dialog.TLabel',foreground=MUTED,wraplength=640).pack(anchor='w',padx=25)
    tools=ttk.Frame(tabs,style='Dialog.TFrame',padding=(16,24));tabs.add(tools,text='Tools & storage')
    ttk.Label(tools,text='Workspace tools',style='Heading.TLabel').pack(anchor='w',pady=(0,12))
    for text,command in [('Re-read selected PDFs',app.reread),('Save supplier layout',app.supplier_layout),('Use existing invoice storage…',app.choose)]:ttk.Button(tools,text=text,command=command).pack(fill='x',pady=5)
    ttk.Label(tools,text='Invoice storage',style='Dialog.TLabel',foreground=MUTED).pack(anchor='w',pady=(24,5))
    ttk.Label(tools,text=str(app.root),style='Dialog.TLabel',wraplength=640).pack(anchor='w')
    bottom=ttk.Frame(panel,style='Dialog.TFrame');bottom.pack(fill='x',pady=(18,0))
    ttk.Label(bottom,text='Uploading and opening this window use no AI credits.',style='Dialog.TLabel',foreground=MUTED).pack(side='left')
    ttk.Button(bottom,text='Done',style='Primary.TButton',command=top.destroy).pack(side='right')

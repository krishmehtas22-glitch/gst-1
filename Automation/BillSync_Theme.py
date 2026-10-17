"""Shared presentation for the workspace and inherited dialogs; no business logic."""
import tkinter as tk
from tkinter import ttk,messagebox
from PIL import Image,ImageDraw,ImageTk
from BillSync_Controls import RoundedCard

BG='#f2f5fb';NAV='#111d35';PRIMARY='#315ee7';INK='#182641';MUTED='#687a96';LINE='#bfcde2'


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def install_theme(window):
    style=ttk.Style(window);style.theme_use('clam')
    window.option_add('*Font',('Segoe UI',10));window.option_add('*TCombobox*Listbox.font',('Segoe UI',10))
    window.option_add('*TCombobox*Listbox.background','white');window.option_add('*TCombobox*Listbox.selectBackground','#e3ebff')
    style.configure('.',font=('Segoe UI',10),background=BG,foreground=INK)
    for name in ('TFrame','Card.TFrame','Dialog.TFrame'):style.configure(name,background='white' if name!='TFrame' else BG)
    style.configure('TLabel',background=BG,foreground=INK)
    style.configure('Card.TLabel',background='white');style.configure('Dialog.TLabel',background='white')
    style.configure('Heading.TLabel',font=('Segoe UI',13,'bold'),background='white')
    style.configure('Muted.TLabel',foreground=MUTED,background='white')
    style.configure('Section.TLabel',font=('Segoe UI',9,'bold'),foreground=MUTED,background='white')
    style.configure('TButton',padding=(12,5),background='white',foreground=INK,borderwidth=0,focusthickness=0)
    style.map('TButton',foreground=[('disabled','#9aa5b9')])
    style.configure('Primary.TButton',background='white',foreground='white')
    style.map('Primary.TButton',foreground=[('disabled','#c7d5ff'),('!disabled','white')])
    style.configure('TEntry',padding=(9,6),fieldbackground='#ffffff',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,insertcolor=INK)
    style.configure('TCombobox',padding=(10,8),fieldbackground='#ffffff',background='#ffffff',bordercolor=LINE,arrowsize=14)
    style.map('TCombobox',fieldbackground=[('readonly','#ffffff')],selectbackground=[('readonly','#ffffff')],selectforeground=[('readonly',INK)])
    style.configure('Client.TCombobox',padding=(12,10),font=('Segoe UI',10))
    style.configure('Treeview',background='white',fieldbackground='white',font=('Segoe UI',10),rowheight=38,borderwidth=0)
    style.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),foreground=MUTED,background='#edf2fb',padding=(12,12),relief='flat',borderwidth=0)
    style.map('Treeview',background=[('selected','#e7edff')],foreground=[('selected',INK)])
    style.configure('TNotebook',background='white',bordercolor=LINE,lightcolor='white',darkcolor='white',borderwidth=0,tabmargins=(0,4,0,8))
    style.configure('TNotebook.Tab',padding=(20,12),background='#eef2fb',foreground=MUTED,borderwidth=0)
    style.map('TNotebook.Tab',background=[('selected','white'),('active','white')],foreground=[('selected','white')])
    style.configure('TLabelframe',background='white',bordercolor=LINE,relief='solid',borderwidth=1)
    style.configure('TLabelframe.Label',background='white',foreground=INK,font=('Segoe UI',11,'bold'))
    style.configure('TCheckbutton',background='white',padding=(2,8));style.map('TCheckbutton',background=[('active','white')])
    style.configure('Vertical.TScrollbar',background='#c1cde2',troughcolor='#f2f5fb',borderwidth=0,arrowsize=12)
    style.configure('Horizontal.TScrollbar',background='#c1cde2',troughcolor='#f2f5fb',borderwidth=0,arrowsize=12)
    style.configure('TSeparator',background=LINE)
    images=[]
    def pill(fill,outline):
        image=Image.new('RGBA',(144,120));draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((2,2,141,117),radius=15,fill=fill,outline=outline,width=3)
        result=ImageTk.PhotoImage(image.resize((48,40),Image.Resampling.LANCZOS),master=window);images.append(result);return result
    for name,fill,hover,edge in [('Soft','white','#edf3ff',LINE),('Primary',PRIMARY,'#2248b5',PRIMARY)]:
        normal=pill(fill,edge);active=pill(hover,edge);disabled=pill('#edf0f7',LINE)
        element='BillSync'+name+'.border'
        style.element_create(element,'image',normal,('disabled',disabled),('pressed',active),('active',active),border=7,sticky='nsew')
        style.layout('Primary.TButton' if name=='Primary' else 'TButton',[(element,{'sticky':'nswe','children':[('Button.padding',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})])
    normal=pill('#ffffff',LINE);focus=pill('white','#7195f5')
    style.element_create('BillSyncEntry.field','image',normal,('focus',focus),border=5,sticky='nsew')
    def substitute(nodes,old,new):
        return [(new if name==old else name,{key:substitute(value,old,new) if key=='children' else value for key,value in options.items()}) for name,options in nodes]
    style.layout('TEntry',substitute(style.layout('TEntry'),'Entry.field','BillSyncEntry.field'))
    style.layout('TCombobox',substitute(style.layout('TCombobox'),'Combobox.field','BillSyncEntry.field'))
    style.layout('Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    inactive=pill('#eef2fb','#eef2fb');selected=pill(PRIMARY,PRIMARY)
    style.element_create('BillSyncTab.border','image',inactive,('selected',selected),border=6,sticky='nsew')
    style.layout('TNotebook.Tab',[('BillSyncTab.border',{'sticky':'nswe','children':[('Notebook.padding',{'sticky':'nswe','children':[('Notebook.label',{'sticky':'nswe'})]})]})])
    style.configure('TNotebook.Tab',padding=(14,6));style.map('TNotebook.Tab',expand=[('selected',(0,0,0,0))])
    def toggle(selected):
        source=Image.new('RGBA',(120,66));draw=ImageDraw.Draw(source)
        draw.rounded_rectangle((1,1,118,64),radius=31,fill=PRIMARY if selected else '#dbe2f1')
        left=61 if selected else 7;draw.ellipse((left,7,left+50,57),fill='white')
        result=ImageTk.PhotoImage(source.resize((40,22),Image.Resampling.LANCZOS),master=window);images.append(result);return result
    off,on=toggle(False),toggle(True)
    style.element_create('BillSyncToggle.indicator','image',off,('selected',on),width=46,sticky='w')
    style.layout('TCheckbutton',substitute(style.layout('TCheckbutton'),'Checkbutton.indicator','BillSyncToggle.indicator'))
    style.configure('Header.TFrame',background=NAV)
    panel_image=pill('white',LINE)
    style.element_create('BillSyncPanel.border','image',panel_image,border=7,sticky='nsew')
    style.layout('Inset.TFrame',[('BillSyncPanel.border',{'sticky':'nswe'})])
    style.configure('Inset.TFrame',background='white',padding=8)
    window._theme_images=images
    return style


def header(parent,title,subtitle='',before=None):
    bar=ttk.Frame(parent,style='Header.TFrame',padding=(24,20,24,18))
    bar.pack(fill='x',**({'before':before} if before else {}))
    ttk.Label(bar,text='BILLSYNC  /  WORKSPACE',style='Dialog.TLabel',background=NAV,foreground='#ffc974',font=('Segoe UI',9,'bold')).pack(anchor='w')
    ttk.Label(bar,text=title,style='Dialog.TLabel',background=NAV,foreground='white',font=('Segoe UI',21,'bold')).pack(anchor='w',pady=(7,4))
    if subtitle:ttk.Label(bar,text=subtitle,style='Dialog.TLabel',background=NAV,foreground='#b9c9e9',wraplength=520).pack(anchor='w')
    return bar


class DialogPresentation:
    def __init__(self,app):
        self.app=app;self.root=app.window
        self.root.option_add('*Menu.font',('Segoe UI',10))
        self.root.option_add('*Menu.background','white');self.root.option_add('*Menu.activeBackground','#e7edff')
        self.root.bind_all('<Map>',self.mapped,add='+')
        # Keep native messagebox return semantics while using the app's design.
        self.native_show=messagebox._show
        messagebox._show=self.show_message
        def restore(event):
            if event.widget is self.root and messagebox._show==self.show_message:messagebox._show=self.native_show
        self.root.bind('<Destroy>',restore,add='+')
    def mapped(self,event):
        widget=event.widget
        if isinstance(widget,tk.Toplevel) and not getattr(widget,'_billsync_decorated',False):
            widget._billsync_decorated=True;widget.after_idle(lambda:self.decorate(widget))
        elif isinstance(widget,ttk.LabelFrame) and getattr(widget,'_presentation_copy',False) and widget.winfo_toplevel().title()=='Review invoice against the original PDF':
            widget.after_idle(lambda:self.item_card(widget))
    def decorate(self,top):
        if not top.winfo_exists() or getattr(top,'_billsync_custom',False):return
        top.configure(bg='white')
        if top.title()=='Review invoice against the original PDF':
            self.review_layout(top)
        else:
            children=top.winfo_children()
            if children and all(w.winfo_manager() in ('pack','') for w in children):
                for widget in descendants(top):
                    if isinstance(widget,ttk.Label) and str(widget.cget('text'))==top.title() and widget.winfo_manager()=='pack':widget.pack_forget()
                header(top,top.title(),{'Import existing XML to Tally':'Choose the destination company and review the import results.','Import masters from Tally':'Read your company’s ledgers, inventory items and units.','Currency / exchange rate':'Review the source currency and its conversion to Indian rupees.','Export IGST refund review':'Review the invoice estimate and retain your claim notes.','Review buyer ledger':'Choose the party ledger used by this invoice.','OCR reading evidence':'Compare uncertain readings with the source document.','Prepared XML — read only':'Inspect the generated units, masters and sales vouchers.','Activity history and selected invoice details':'Review recent actions and the selected invoice.','Tally master assignments':'Review the company-specific ledger, item and unit assignments.'}.get(top.title(),'Review details and update your workspace.'),before=children[0])
                # Retain content space after adding the consistent page heading.
                top.geometry(str(min(max(top.winfo_width(),650),self.root.winfo_screenwidth()-70))+'x'+str(min(top.winfo_height()+110,self.root.winfo_screenheight()-95)))
        for widget in descendants(top):
            try:
                if isinstance(widget,ttk.Frame):
                    if widget.cget('style')!='Header.TFrame':
                        boxed=any(isinstance(w,(ttk.Entry,ttk.Combobox)) for w in widget.winfo_children())
                        widget.configure(style='Inset.TFrame' if boxed else 'Dialog.TFrame')
                elif isinstance(widget,ttk.Label):
                    if isinstance(widget.master,ttk.Frame) and widget.master.cget('style')=='Header.TFrame':continue
                    widget.configure(style='Dialog.TLabel')
                elif isinstance(widget,tk.Text):widget.configure(bg='#f7f9ff',fg=INK,insertbackground=PRIMARY,relief='flat',borderwidth=0,padx=16,pady=14,selectbackground='#dfe8ff',highlightthickness=1,highlightbackground=LINE,highlightcolor=PRIMARY)
                elif isinstance(widget,ttk.Button):
                    text=str(widget.cget('text')).lower()
                    if any(word in text for word in ('save','import all','use snapshot','connect /')):widget.configure(style='Primary.TButton')
            except tk.TclError:pass
        top.update_idletasks()
        x=max(0,self.root.winfo_rootx()+(self.root.winfo_width()-top.winfo_width())//2)
        y=max(0,min(self.root.winfo_screenheight()-top.winfo_height()-45,self.root.winfo_rooty()+30))
        top.geometry('+'+str(x)+'+'+str(y))
    def item_card(self,frame):
        if not frame.winfo_exists() or getattr(frame,'_billsync_item',False) or not str(frame.cget('text')).startswith('Item '):return
        frame._billsync_item=True;frame.configure(padding=18)
        children=frame.winfo_children()
        pairs=[]
        for widget in children:
            if isinstance(widget,ttk.Label):
                info=widget.grid_info()
                entry=next((w for w in children if isinstance(w,(ttk.Entry,ttk.Combobox)) and w.grid_info().get('row')==info.get('row') and w.grid_info().get('column')==info.get('column',0)+1),None)
                if entry:pairs.append((widget,entry))
        for i,(label,entry) in enumerate(pairs):
            label.grid_forget();entry.grid_forget();row,col=divmod(i,3)
            label.grid(row=row*2,column=col,sticky='w',padx=(0,14),pady=(9,4));label.configure(style='Dialog.TLabel',foreground=MUTED,text={'Hsn':'HSN / SAC','Cgst Rate':'CGST rate','Sgst Rate':'SGST rate','Igst Rate':'IGST rate','Printed Cgst':'Printed CGST','Printed Sgst':'Printed SGST','Printed Igst':'Printed IGST'}.get(label.cget('text'),label.cget('text')))
            entry.grid(row=row*2+1,column=col,sticky='ew',padx=(0,14),pady=(0,5));frame.columnconfigure(col,weight=1,uniform='itemfields')
            entry.configure(width=20)
    def review_layout(self,top):
        from Invoice_Desktop import FIELDS
        canvas=next(w for w in top.winfo_children() if isinstance(w,tk.Canvas))
        form=next(w for w in canvas.winfo_children() if isinstance(w,ttk.Frame))
        original=form.winfo_children();pairs={}
        for index,field in enumerate(FIELDS):
            row,col=index//2+1,(index%2)*2
            pairs[field]=tuple(next(w for w in original if w.grid_info().get('row')==row and w.grid_info().get('column')==c) for c in (col,col+1))
        base=len(FIELDS)//2+3
        items=next(w for w in original if isinstance(w,ttk.Frame) and w.grid_info().get('row')==base)
        buttons=next(w for w in original if isinstance(w,ttk.Frame) and w.grid_info().get('row')==base+1)
        notices=[w for w in original if isinstance(w,ttk.Label)]
        for w in original:
            if w.winfo_manager()=='grid':w.grid_forget()
        for scroll in top.winfo_children():
            if isinstance(scroll,ttk.Scrollbar):scroll.pack_forget()
        canvas.configure(bg='white',highlightthickness=0);form.configure(style='Dialog.TFrame',padding=0)
        form.columnconfigure(0,weight=1);form.rowconfigure(2,weight=1)
        title=ttk.Frame(form,style='Header.TFrame',padding=(24,18));title.grid(row=0,column=0,sticky='ew')
        ttk.Label(title,text='INVOICE REVIEW',style='Dialog.TLabel',background=NAV,foreground='#ffc974',font=('Segoe UI',9,'bold')).pack(anchor='w')
        ttk.Label(title,text='Review & refine your invoice',style='Dialog.TLabel',background=NAV,foreground='white',font=('Segoe UI',23,'bold')).pack(anchor='w',pady=(5,0))
        summary=ttk.Frame(title,style='Header.TFrame');summary.pack(fill='x',pady=(14,0))
        top.review_summary_cards=[]
        for col,(caption,field,tint,edge) in enumerate([('INVOICE NUMBER','number','#edf3ff','#c2d3f5'),('BUYER','buyer_name','#eef1f8','#c2ccdf'),('INVOICE TOTAL','total','#fff6e7','#ecd5ac')]):
            summary.columnconfigure(col,weight=1,uniform='summary')
            card=RoundedCard(summary,fill=tint,border=edge,minheight=66);card.grid(row=0,column=col,sticky='nsew',padx=(0,10 if col<2 else 0));top.review_summary_cards.append(card)
            tk.Label(card.panel,text=caption,font=('Segoe UI',8,'bold'),fg=MUTED,bg=tint).pack(anchor='w')
            tk.Label(card.panel,textvariable=pairs[field][1].cget('textvariable'),font=('Segoe UI',12),fg=INK,bg=tint,wraplength=290,justify='left').pack(anchor='w',pady=(4,0))
        notice=ttk.Frame(form,style='Dialog.TFrame',padding=(24,0,24,10));notice.grid(row=1,column=0,sticky='ew')
        # Original notices remain intact, including test-data confirmation.
        for label in notices:
            if label not in [p[0] for p in pairs.values()]:
                label.grid(in_=notice,row=len(notice.grid_slaves()),column=0,sticky='w',pady=2);label.configure(wraplength=930,foreground=MUTED)
        tabs=ttk.Notebook(form);tabs.grid(row=2,column=0,sticky='nsew',padx=24)
        definitions=[('Invoice details',[('Document',['number','date','supply','classification','place_of_supply']),('Amounts & tax',['taxable','cgst','sgst','igst','round_off','total'])]),('Seller & buyer',[('Seller',['seller_name','seller_gstin','seller_state','seller_address']),('Buyer',['buyer_name','buyer_gstin','buyer_registration','buyer_state','buyer_address'])]),('Items',[]),('Export & currency',[('Export details',['buyer_country','export_mode','shipping_bill_port']),('Currency & exchange',['foreign_currency','exchange_rate','foreign_invoice_value'])])]
        top.review_tabs=tabs;top.review_fields={key:pair[1] for key,pair in pairs.items()}
        for field,(label,entry) in pairs.items():
            label.configure(text={'number':'Invoice number','date':'Invoice date','taxable':'Taxable amount','cgst':'CGST','sgst':'SGST','igst':'IGST','seller_gstin':'Seller GSTIN','buyer_gstin':'Buyer GSTIN','place_of_supply':'Place of supply','export_mode':'Export treatment'}.get(field,field.replace('_',' ').capitalize()))
        for name,groups in definitions:
            page=ttk.Frame(tabs,style='Dialog.TFrame',padding=(0,12,0,4));tabs.add(page,text=name)
            if name=='Items':
                scroller=tk.Canvas(page,bg='white',highlightthickness=0);scroller.pack(side='left',fill='both',expand=True)
                scrollbar=ttk.Scrollbar(page,command=scroller.yview);scrollbar.pack(side='right',fill='y');scroller.configure(yscrollcommand=scrollbar.set)
                host=ttk.Frame(scroller,style='Dialog.TFrame');item=scroller.create_window(0,0,window=host,anchor='nw')
                scroller.bind('<Configure>',lambda e,c=scroller,i=item:c.itemconfigure(i,width=e.width))
                host.bind('<Configure>',lambda e,c=scroller:c.configure(scrollregion=c.bbox('all')))
                copies={}
                def sync_items():
                    originals={str(w):w for w in items.winfo_children() if isinstance(w,ttk.LabelFrame)}
                    for key in list(copies):
                        if key not in originals:copies.pop(key).destroy()
                    for key,old_frame in originals.items():
                        if key in copies:continue
                        card=ttk.LabelFrame(host,text=old_frame.cget('text'));card._presentation_copy=True;card.pack(fill='x',pady=5);copies[key]=card
                        for index,old in enumerate(old_frame.winfo_children()):
                            info={'row':index//6,'column':index%6}
                            if isinstance(old,ttk.Label):widget=ttk.Label(card,text=old.cget('text'),style='Dialog.TLabel')
                            elif isinstance(old,(ttk.Entry,ttk.Combobox)):
                                options={'textvariable':old.cget('textvariable'),'width':24}
                                if isinstance(old,ttk.Combobox):options.update(values=old.cget('values'),state=old.cget('state'))
                                widget=type(old)(card,**options)
                            else:continue
                            widget.grid(row=info['row'],column=info['column'])
                        self.item_card(card)
                        def wheel(event,c=scroller):
                            if c.winfo_exists() and c.winfo_ismapped():c.yview_scroll(-1 if event.delta>0 or getattr(event,'num',None)==4 else 1,'units');return 'break'
                        for widget in [card,*descendants(card)]:
                            if not isinstance(widget,ttk.Combobox):widget.bind('<MouseWheel>',wheel,add='+')
                sync_items()
                for button in buttons.winfo_children():
                    if isinstance(button,ttk.Button) and button.cget('text') in ('Add item','Remove last item'):
                        original_command=button.cget('command')
                        def invoke(command=original_command):top.tk.call(command);sync_items()
                        button.configure(command=invoke)
                top.item_cards=copies
                continue
            viewport=tk.Canvas(page,bg='white',highlightthickness=0);viewport.pack(side='left',fill='both',expand=True)
            bar=ttk.Scrollbar(page,command=viewport.yview);bar.pack(side='right',fill='y');viewport.configure(yscrollcommand=bar.set)
            content=ttk.Frame(viewport,style='Dialog.TFrame');content_id=viewport.create_window(0,0,window=content,anchor='nw')
            viewport.bind('<Configure>',lambda e,c=viewport,i=content_id:c.itemconfigure(i,width=e.width))
            content.bind('<Configure>',lambda e,c=viewport:c.configure(scrollregion=c.bbox('all')))
            for col,(label,fields) in enumerate(groups):
                content.columnconfigure(col,weight=1,uniform='review')
                card=RoundedCard(content,fill='white',border='#bfcde2');card.grid(row=0,column=col,sticky='new',padx=(0 if col==0 else 9,9 if col==0 else 0))
                group=card.panel;group.columnconfigure(0,weight=1)
                tint,accent=('#edf3ff','#315dc5') if col==0 else ('#fff5e5','#a96918')
                band=tk.Frame(group,bg=tint);band.grid(row=0,column=0,sticky='ew',pady=(0,10))
                tk.Label(band,text='  '+label,font=('Segoe UI',12,'bold'),fg=accent,bg=tint,pady=11,anchor='w').pack(fill='x')
                for row,field in enumerate(fields):
                    original_label,original_entry=pairs[field]
                    label_widget=ttk.Label(group,text=original_label.cget('text'),style='Dialog.TLabel',foreground=MUTED)
                    options={'textvariable':original_entry.cget('textvariable'),'width':32}
                    if isinstance(original_entry,ttk.Combobox):options.update(values=original_entry.cget('values'),state=original_entry.cget('state'))
                    entry=type(original_entry)(group,**options)
                    top.review_fields[field]=entry
                    label_widget.grid(row=row*2+1,column=0,sticky='w',pady=(1,1))
                    entry.grid(row=row*2+2,column=0,sticky='ew',pady=(0,3))
                    if not isinstance(entry,ttk.Combobox):entry.bind('<MouseWheel>',lambda e,c=viewport:c.yview_scroll(-1 if e.delta>0 else 1,'units'),add='+')
        buttons.grid(row=3,column=0,sticky='ew',padx=24,pady=18)
        for child in buttons.winfo_children():
            if isinstance(child,ttk.Button):child.pack_configure(padx=(0,8),pady=0)
        h=min(890,self.root.winfo_screenheight()-90);top.geometry(f'1140x{h}');top.minsize(1000,640)
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(canvas.find_all()[0],width=e.width,height=e.height))
        # A presentation handle enables focused regression checks without new saves.
        for label,entry in pairs.values():label.lift();entry.lift()
        for label in notices:
            if label not in [p[0] for p in pairs.values()]:label.lift()
        buttons.lift()
        top._review_canvas=canvas
    def show_message(self,title=None,message=None,_icon=None,_type=None,**options):
        _type=options.get('type',_type)
        parent=options.get('parent') or self.root
        try:owned=parent.winfo_toplevel()==self.root or str(parent).startswith(str(self.root))
        except (AttributeError,tk.TclError):owned=False
        if not owned:return self.native_show(title,message,_icon,_type,**options)
        top=tk.Toplevel(parent);top._billsync_custom=True;top.title(title or 'BillSync');top.configure(bg='white');top.transient(parent)
        width=640;height=min(600,max(290,200+len(str(message or ''))//90*20));top.geometry(f'{width}x{height}');top.resizable(True,True)
        header(top,title or 'BillSync')
        body=tk.Text(top,wrap='word',bg='white',fg=INK,font=('Segoe UI',11),relief='flat',padx=24,pady=12,height=6)
        body.pack(fill='both',expand=True);body.insert('end',message or '');body.config(state='disabled')
        footer=ttk.Frame(top,style='Dialog.TFrame',padding=(24,14));footer.pack(fill='x')
        values={'yesno':[('Cancel','no'),('Continue','yes')],'yesnocancel':[('Cancel','cancel'),('No','no'),('Yes','yes')],'okcancel':[('Cancel','cancel'),('Continue','ok')],'retrycancel':[('Cancel','cancel'),('Retry','retry')],'abortretryignore':[('Abort','abort'),('Retry','retry'),('Ignore','ignore')]}.get(_type,[('OK','ok')])
        result=[values[0][1] if len(values)>1 else 'ok'];previous=top.grab_current()
        def done(value):result[0]=value;top.destroy()
        for i,(text,value) in enumerate(values):ttk.Button(footer,text=text,style='Primary.TButton' if i==len(values)-1 else 'TButton',command=lambda v=value:done(v)).pack(side='right',padx=5)
        cancel='cancel' if any(value=='cancel' for _,value in values) else 'no' if _type=='yesno' else 'ok'
        top.protocol('WM_DELETE_WINDOW',lambda:done(cancel));top.bind('<Escape>',lambda e:done(cancel));top.grab_set();top.wait_window()
        if previous and previous.winfo_exists():previous.grab_set()
        return result[0]

"""User-facing nested document, delivery, charges and source-evidence review."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk,messagebox
from Common_Rules.invoice_document import sync_record,to_legacy,validate,INVOICE_SCHEMA,field_label,get,put


def open_document_editor(parent,root,record,save,on_close=lambda:None):
    document=deepcopy(record.get('document') or sync_record(record))
    top=tk.Toplevel(parent);top._billsync_custom=True;top.title('Invoice details and source evidence')
    width=min(1120,top.winfo_screenwidth()-60);height=min(720,top.winfo_screenheight()-100)
    top.geometry(f'{width}x{height}+20+20');top.transient(parent);top.grab_set()
    footer=ttk.Frame(top,padding=12);footer.pack(side='bottom',fill='x')
    ttk.Label(top,text='Document, delivery & source evidence',font=('Segoe UI',17,'bold')).pack(anchor='w',padx=16,pady=12)
    ttk.Label(top,text='Changes are saved locally. No AI request or Tally import is sent.',wraplength=width-45).pack(anchor='w',padx=16,pady=(0,10))
    tabs=ttk.Notebook(top);tabs.pack(fill='both',expand=True,padx=12,pady=6)
    def page(title):
        frame=ttk.Frame(tabs);tabs.add(frame,text=title)
        canvas=tk.Canvas(frame,highlightthickness=0,background='white');canvas.pack(side='left',fill='both',expand=True)
        bar=ttk.Scrollbar(frame,orient='vertical',command=canvas.yview);bar.pack(side='right',fill='y');canvas.config(yscrollcommand=bar.set)
        body=ttk.Frame(canvas,padding=14);ident=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(ident,width=e.width))
        return body
    fields=page('Document & delivery');vars={}
    specifications=[('document_type','Document type',('tax_invoice','sales_invoice','bill_of_supply','credit_note','debit_note','proforma','quotation','challan','receipt','other')),
                    ('reverse_charge','Reverse charge',('No','Yes')),
                    ('invoice_date_raw','Printed date text',()),('invoice_date_iso','Invoice date (YYYY-MM-DD)',()),
                    ('totals.cess_total','Cess total',()),('export.country','Export destination country (source)',()),('export.printed_treatment','Printed export treatment',())]
    for index,(key,label,choices) in enumerate(specifications):
        ttk.Label(fields,text=label).grid(row=index,column=0,sticky='w',padx=5,pady=6)
        value=tk.StringVar(value=str(get(document['invoice'],key.split('.')) or ''));vars[key]=value
        widget=ttk.Combobox(fields,textvariable=value,values=choices,width=42) if choices else ttk.Entry(fields,textvariable=value,width=45)
        widget.grid(row=index,column=1,sticky='ew',padx=8)
    ttk.Label(fields,text='Ship to / consignee — separate from the buyer',font=('Segoe UI',11,'bold')).grid(row=len(specifications),column=0,columnspan=2,sticky='w',pady=(18,8))
    ship_vars={}
    for index,key in enumerate(('name','address','state','country','gstin'),len(specifications)+1):
        ttk.Label(fields,text=key.title()).grid(row=index,column=0,sticky='w',padx=5,pady=6)
        var=tk.StringVar(value=str(document['invoice'].get('ship_to',{}).get(key) or ''));ship_vars[key]=var
        ttk.Entry(fields,textvariable=var,width=60).grid(row=index,column=1,sticky='ew',padx=8)
    fields.columnconfigure(1,weight=1)
    charges=page('Charges & discounts');charge_rows=[]
    ttk.Label(charges,text='Keep charges separate from physical goods. Confirm whether each amount is included in the printed taxable total.',wraplength=width-90).pack(anchor='w',pady=(0,10))
    container=ttk.Frame(charges);container.pack(fill='x')
    def add_charge(value=None):
        value=value or {};frame=ttk.LabelFrame(container,text='Charge '+str(len(charge_rows)+1),padding=10);frame.pack(fill='x',pady=7)
        values={}
        for index,(key,label,choices) in enumerate((('label','Ledger description',()),('kind','Type',('freight','packing','insurance','discount','other','tcs')),('amount','Printed amount',()),('included_in_taxable_total','Included in taxable total?',('yes','no')))):
            ttk.Label(frame,text=label).grid(row=index,column=0,sticky='w',pady=5)
            var=tk.StringVar(value=str(value.get(key) or ''));values[key]=var
            widget=ttk.Combobox(frame,textvariable=var,values=choices,width=36) if choices else ttk.Entry(frame,textvariable=var,width=40)
            widget.grid(row=index,column=1,sticky='ew',padx=8)
        frame.columnconfigure(1,weight=1);charge_rows.append((deepcopy(value),values,frame))
    for row in document['invoice'].get('other_charges') or []:add_charge(row)
    actions=ttk.Frame(charges);actions.pack(fill='x',pady=8)
    ttk.Button(actions,text='Add charge',command=add_charge).pack(side='left')
    def remove():
        if charge_rows:charge_rows.pop()[2].destroy()
    ttk.Button(actions,text='Remove last charge',command=remove).pack(side='left',padx=10)
    ttk.Label(charges,text='TCS, reverse-charge treatment and non-unit price bases require further accounting review. They are not silently converted into ordinary sales.',wraplength=width-90).pack(anchor='w',pady=10)
    item_page=page('Item treatment');item_rows=[]
    ttk.Label(item_page,text='Review explicit discounts and rate bases. Change quantities, prices and ordinary item fields in the invoice editor.',wraplength=width-90).pack(anchor='w',pady=8)
    for index,item in enumerate(document['invoice'].get('items') or []):
        box=ttk.LabelFrame(item_page,text=str(index+1)+'. '+str(item.get('description') or 'Item'),padding=10);box.pack(fill='x',pady=7)
        values={}
        for row,(key,label,choices) in enumerate((('price_basis','Rate basis',('per_unit','per_100','tax_inclusive','unknown')),('discount','Printed discount',()),('discount_basis','Discount basis',('percent','amount','unknown')),('classification','Item tax classification',('taxable','exempt','nil_rated','non_gst')))):
            ttk.Label(box,text=label).grid(row=row,column=0,sticky='w',pady=5)
            var=tk.StringVar(value=str(item.get(key) or ''));values[key]=var
            widget=ttk.Combobox(box,textvariable=var,values=choices,width=40) if choices else ttk.Entry(box,textvariable=var,width=42)
            widget.grid(row=row,column=1,sticky='ew',padx=8)
        box.columnconfigure(1,weight=1);item_rows.append(values)
    evidence=ttk.Frame(tabs,padding=12);tabs.add(evidence,text='Source evidence')
    evidence.columnconfigure(0,weight=1);evidence.rowconfigure(1,weight=1)
    ttk.Label(evidence,text='Source-observed means a matching quote was found; it is not independent proof of correctness.',wraplength=width-70).grid(row=0,column=0,sticky='w',pady=(0,8))
    table=ttk.Treeview(evidence,columns=('field','value','status'),show='headings',height=7)
    for key,label,w in [('field','Field',230),('value','Value',330),('status','Review status',170)]:table.heading(key,text=label);table.column(key,width=w)
    table.grid(row=1,column=0,sticky='nsew');bar=ttk.Scrollbar(evidence,orient='vertical',command=table.yview);bar.grid(row=1,column=1,sticky='ns');table.config(yscrollcommand=bar.set)
    details=tk.Text(evidence,height=5,wrap='word');details.grid(row=2,column=0,sticky='ew',pady=8)
    entries=list(document.get('field_status',{}).items())
    statuses={'source_observed':'Found in source','uncertain':'Check source','unverified':'Needs review','missing':'Missing','derived':'Derived','human_reviewed':'Reviewed by you','human_corrected':'Corrected by you'}
    for index,(field,row) in enumerate(entries):table.insert('','end',iid=str(index),values=(field_label(field),row.get('value'),statuses.get(row.get('status'),row.get('status'))))
    def show(event=None):
        selected=table.selection()
        if not selected:return
        field,row=entries[int(selected[0])];text='Quote: '+str(row.get('quote') or 'No source quote retained')+'\nAI page hint (not independently verified): '+str(row.get('page') or 'Not retained')+'\nOrigin: '+str(row.get('origin') or 'Unknown')
        details.config(state='normal');details.delete('1.0','end');details.insert('end',text);details.config(state='disabled')
    table.bind('<<TreeviewSelect>>',show)
    def close():
        top.destroy();on_close()
    def commit():
        changed=deepcopy(document)
        for key,var in vars.items():put(changed['invoice'],key.split('.'),var.get().strip() or None)
        changed['invoice']['ship_to']={**changed['invoice'].get('ship_to',{}),**{key:var.get().strip() or None for key,var in ship_vars.items()}}
        changed['invoice']['other_charges']=[{**old,**{key:var.get().strip() or None for key,var in values.items()}} for old,values,frame in charge_rows]
        for item,values in zip(changed['invoice'].get('items') or [],item_rows):item.update({key:var.get().strip() or None for key,var in values.items()})
        try:
            validate(changed['invoice'],INVOICE_SCHEMA)
            edited=to_legacy(changed,record['invoice']);edited['_document_v2']=changed
            save(record,edited)
        except (ValueError,OSError) as exc:messagebox.showerror('Invoice review',str(exc),parent=top);return
        close()
    def source():
        from Workflow_Review_Dialog import open_source_document
        try:open_source_document({'source':record.get('source_path') or record['path'],'root':str(root)})
        except (ValueError,OSError) as exc:messagebox.showerror('Source document',str(exc),parent=top)
    ttk.Button(footer,text='Open source PDF / image',command=source).pack(side='left')
    ttk.Button(footer,text='Save changes to XML',style='Primary.TButton',command=commit).pack(side='right')
    ttk.Button(footer,text='Cancel',command=close).pack(side='right',padx=10)
    top.protocol('WM_DELETE_WINDOW',close)
    return top

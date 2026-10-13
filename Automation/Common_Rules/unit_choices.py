"""Per-item unit choices, without re-entering the invoice's extracted fields."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox
from .desktop import UNITS, save_review
from .source_documents import verify_source


def missing_units(records):
    rows=[]
    known={unit.casefold() for unit in UNITS}
    for record in records:
        for index,item in enumerate(record.get('invoice',{}).get('items',[])):
            if str(item.get('unit','')).casefold() not in known:
                rows.append((record,index))
    return rows


def save_unit_choices(root,choices):
    """Persist explicit choices only; tax/identity/OCR warnings stay unresolved."""
    updates={}
    for record,index,unit in choices:
        if not unit:continue
        if unit not in record.get('available_units',UNITS):raise ValueError('Choose a configured quantity unit: '+unit)
        verify_source(root,record)
        key=record['digest']
        if key not in updates:
            updates[key]=(record,deepcopy(record['invoice']),{})
        previous=updates[key][2].get(index)
        if previous and previous!=unit:raise ValueError('Copies of the same invoice must use the same item unit')
        updates[key][2][index]=unit
        edited=updates[key][1]
        edited['items'][index].update(unit=unit,unit_origin='manual',unit_auto=False,unit_correction_reviewed=True)
        if edited['items'][index].get('quantity_assumed'):edited['items'][index]['quantity_confirmed']=True
    for record,edited,_ in updates.values():save_review(root,record,edited,resolve_warnings=False)
    return len(updates)


def open_unit_choices(parent,root,records,on_done,selected_record=None):
    rows=[(record,index) for record in records for index,item in enumerate(record.get('invoice',{}).get('items',[]))]
    if not rows:
        messagebox.showinfo('Quantity units','No item quantities are available in the visible invoices.',parent=parent)
        on_done(False);return
    top=tk.Toplevel(parent);top.title('Accept quantities and units');top.geometry('1200x650')
    top.transient(parent)
    ttk.Label(top,text='Check each printed quantity and its unit. Change units here; use Review to correct numbers. Acceptance confirms units only, leaving GST and other checks active.',padding=10).pack(anchor='w')
    canvas=tk.Canvas(top);bar=ttk.Scrollbar(top,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
    form=ttk.Frame(canvas,padding=10);canvas.create_window((0,0),window=form,anchor='nw')
    form.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
    for col,title in enumerate(('Accept','Client / invoice / page','Seller','Item','Quantity read','Unit evidence','Your unit')):
        ttk.Label(form,text=title).grid(row=0,column=col,sticky='w',padx=5)
    choices=[]
    marks=[]
    for row,(record,index) in enumerate(rows,1):
        inv=record['invoice'];item=inv['items'][index]
        number=record['client']+' / '+inv.get('number','')+(f" (p{record['page_number']})" if record.get('page_number') else '')
        note=item.get('unit_evidence') or item.get('unit') or inv.get('source_unit_note') or 'Not specified'
        mark=tk.BooleanVar(value=False);marks.append(mark)
        ttk.Checkbutton(form,variable=mark).grid(row=row,column=0)
        for col,value in enumerate((number,inv.get('seller_name',''),item.get('name',''),item.get('quantity',''),note),1):
            ttk.Label(form,text=str(value),wraplength=(170 if col in (1,2,3,5) else 100)).grid(row=row,column=col,sticky='w',padx=5,pady=5)
        variable=tk.StringVar(value=str(item.get('unit','')))
        picker=ttk.Combobox(form,textvariable=variable,values=tuple(record.get('available_units',UNITS)),state='readonly',width=10)
        picker.grid(row=row,column=6,padx=5)
        picker.bind('<<ComboboxSelected>>',lambda event,m=mark:m.set(True))
        choices.append((record,index,variable))
    def close(changed=False):top.destroy();on_done(changed)
    top.protocol('WM_DELETE_WINDOW',close)
    def save(mode):
        selected=[];unresolved=0
        for position,(record,index,var) in enumerate(choices):
            include=mode=='all' or (mode=='checked' and marks[position].get()) or (mode=='invoice' and record is invoice_records[invoice_choice.get()])
            if include:
                if var.get() in record.get('available_units',UNITS):selected.append((record,index,var.get()))
                else:unresolved+=1
        if not selected:
            messagebox.showinfo('Accept quantities and units','Select an item or choose a unit first.',parent=top);return
        if mode=='all' and not messagebox.askyesno('Accept all shown units',f'Confirm the displayed quantities and current units for {len(selected)} item rows? Numeric quantities are unchanged. {unresolved} rows with missing/unmapped units remain unresolved. GST, seller details and history checks remain active.',parent=top):return
        try:changed=save_unit_choices(root,selected)
        except (ValueError,OSError,IndexError,KeyError) as exc:
            messagebox.showerror('Quantity units',str(exc),parent=top);return
        close(bool(changed))
    buttons=ttk.Frame(top,padding=10);buttons.pack(fill='x')
    invoice_records={str(index+1)+': '+record['client']+' / '+str(record['invoice'].get('number','')):record for index,record in enumerate(records) if record['invoice'].get('items')}
    initial=next((label for label,record in invoice_records.items() if record is selected_record),next(iter(invoice_records)))
    invoice_choice=tk.StringVar(value=initial)
    ttk.Combobox(buttons,textvariable=invoice_choice,values=list(invoice_records),state='readonly',width=30).pack(side='left')
    ttk.Button(buttons,text='Accept this invoice',command=lambda:save('invoice')).pack(side='left',padx=5)
    ttk.Button(buttons,text='Accept checked items',command=lambda:save('checked')).pack(side='left',padx=5)
    ttk.Button(buttons,text='Accept all shown invoices',command=lambda:save('all')).pack(side='left',padx=5)
    ttk.Button(buttons,text='Cancel',command=lambda:close(False)).pack(side='left',padx=10)
    return top

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
    for record,edited,_ in updates.values():save_review(root,record,edited,resolve_warnings=False)
    return len(updates)


def open_unit_choices(parent,root,records,on_done):
    rows=[(record,index) for record in records for index,item in enumerate(record.get('invoice',{}).get('items',[]))]
    if not rows:
        messagebox.showinfo('Quantity units','No item quantities are available in the visible invoices.',parent=parent)
        on_done(False);return
    top=tk.Toplevel(parent);top.title('Check or change invoice units');top.geometry('1100x650')
    top.transient(parent)
    ttk.Label(top,text='Check printed or estimated units. Change any wrong unit, then save. Quantities and prices stay unchanged.',padding=10).pack(anchor='w')
    canvas=tk.Canvas(top);bar=ttk.Scrollbar(top,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
    form=ttk.Frame(canvas,padding=10);canvas.create_window((0,0),window=form,anchor='nw')
    form.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
    for col,title in enumerate(('Invoice / page','Seller','Item','Quantity','Unit evidence','Your unit')):
        ttk.Label(form,text=title).grid(row=0,column=col,sticky='w',padx=5)
    choices=[]
    for row,(record,index) in enumerate(rows,1):
        inv=record['invoice'];item=inv['items'][index]
        number=inv.get('number','')+(f" (p{record['page_number']})" if record.get('page_number') else '')
        note=item.get('unit_evidence') or item.get('unit') or inv.get('source_unit_note') or 'Not specified'
        for col,value in enumerate((number,inv.get('seller_name',''),item.get('name',''),item.get('quantity',''),note)):
            ttk.Label(form,text=str(value),wraplength=(190 if col in (1,2,4) else 150)).grid(row=row,column=col,sticky='w',padx=5,pady=5)
        variable=tk.StringVar(value=str(item.get('unit','')))
        ttk.Combobox(form,textvariable=variable,values=tuple(record.get('available_units',UNITS)),state='readonly',width=10).grid(row=row,column=5,padx=5)
        choices.append((record,index,variable))
    def close(changed=False):top.destroy();on_done(changed)
    top.protocol('WM_DELETE_WINDOW',close)
    def save():
        try:changed=save_unit_choices(root,[(record,index,var.get()) for record,index,var in choices])
        except (ValueError,OSError,IndexError,KeyError) as exc:
            messagebox.showerror('Quantity units',str(exc),parent=top);return
        close(bool(changed))
    buttons=ttk.Frame(top,padding=10);buttons.pack(fill='x')
    ttk.Button(buttons,text='Save chosen units and rescan',command=save).pack(side='left')
    ttk.Button(buttons,text='Cancel',command=lambda:close(False)).pack(side='left',padx=10)
    return top

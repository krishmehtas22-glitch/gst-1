"""Explicit local buyer correction; no provider request or Tally write."""
import tkinter as tk
from tkinter import ttk,messagebox
from Common_Rules.tally_master_matching import context,details,loaded_choices,save_choices,norm
from Common_Rules.buyer_ledger_guard import party_conflict


def save_party(root,record,ctx,ledger_id):
    catalog=details(ctx)
    if ledger_id:
        candidate=catalog.get(ledger_id)
        if not candidate or candidate['kind']!='ledgers':raise ValueError('Choose a ledger from this company snapshot.')
        conflict=party_conflict(candidate)
        if conflict:raise ValueError(conflict)
        inv=record['invoice'];gstin=norm(inv.get('buyer_gstin'));existing=norm(candidate['gstin'])
        if (gstin or existing) and gstin!=existing:raise ValueError('This ledger GSTIN does not match the invoice buyer. Correct the buyer details or choose another ledger.')
        if not gstin and norm(inv.get('buyer_name'))!=norm(candidate['name']):raise ValueError('Without GSTIN, the buyer name must match this ledger.')
        if not gstin and candidate['address'] and inv.get('buyer_address') and candidate['address']!=norm(inv['buyer_address']):raise ValueError('The buyer address conflicts with this ledger.')
        if candidate['country'] and inv.get('buyer_country') and norm(candidate['country'])!=norm(inv['buyer_country']):raise ValueError('The buyer country conflicts with this ledger.')
    choices=loaded_choices(root,record,ctx) or {'items':[]}
    offered=choices.pop('_offered_ids',[])
    choices['party']={'id':ledger_id,'confidence':1.0,'reason':'Explicit manual buyer ledger selection'} if ledger_id else None
    if ledger_id and ledger_id not in offered:offered.append(ledger_id)
    save_choices(root,record,ctx,record['invoice'],choices,offered=offered)


def open_buyer_review(app):
    record=app.selected()
    if app.busy or not record:return
    try:
        record=app.prepare_manual_review(record)
        if record is None:return
        ctx=context(app.root,record)
        if not ctx:raise ValueError('Read and select Tally masters for this client first.')
        catalog=details(ctx);choices=loaded_choices(app.root,record,ctx) or {}
    except (ValueError,OSError) as exc:messagebox.showerror('Review buyer ledger',str(exc),parent=app.window);return
    top=tk.Toplevel(app.window);top.title('Review buyer ledger');top.geometry('760x560');top.transient(app.window)
    panel=ttk.Frame(top,padding=20);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='Review buyer ledger',font=('Segoe UI',14,'bold')).pack(anchor='w')
    inv=record['invoice']
    ttk.Label(panel,text='Company: '+ctx['company']+'\nInvoice buyer: '+str(inv.get('buyer_name') or 'Missing')+'\nBuyer GSTIN: '+str(inv.get('buyer_gstin') or 'Not provided'),wraplength=710).pack(anchor='w',pady=10)
    current=catalog.get((choices.get('party') or {}).get('id'))
    if current:
        ttk.Label(panel,text='Selected: '+current['name']+' · Under: '+current['parent'],wraplength=710).pack(anchor='w')
        conflict=party_conflict(current)
        if conflict:ttk.Label(panel,text=conflict,foreground='#b52538',wraplength=710).pack(anchor='w',pady=8)
    fallback='Use invoice buyer — current creation method'
    options={fallback:None}
    for entry in catalog.values():
        if entry['kind']=='ledgers' and not party_conflict(entry):options[entry['name']+' · Under: '+entry['parent']+' · '+(entry['gstin'] or 'No GSTIN')]=entry['id']
    selected=tk.StringVar(value=next((label for label,id in options.items() if current and id==current['id']),fallback))
    ttk.Label(panel,text='Choose the correct party ledger').pack(anchor='w',pady=(12,4))
    ttk.Combobox(panel,textvariable=selected,values=list(options),state='readonly',width=95).pack(fill='x')
    ttk.Label(panel,text='Only verified Sundry Debtors/Creditors groups are offered. Custom subgroup ancestry is not included in the snapshot; use a verified party or the current creation method. A conflicting existing system ledger must be corrected in Tally, then masters refreshed.',wraplength=710).pack(anchor='w',pady=12)
    ttk.Label(panel,text='Saving prepares this client’s XML locally. No AI request or Tally write is sent.',wraplength=710).pack(anchor='w')
    def save():
        try:save_party(app.root,record,ctx,options[selected.get()])
        except (ValueError,OSError) as exc:messagebox.showerror('Review buyer ledger',str(exc),parent=top);return
        top.destroy();app.reset();app.revalidate(client_names=[record['client']])
    buttons=ttk.Frame(panel);buttons.pack(side='bottom',fill='x',pady=12)
    ttk.Button(buttons,text='Save buyer & prepare XML',command=save).pack(side='right')
    ttk.Button(buttons,text='Close',command=top.destroy).pack(side='right',padx=8)

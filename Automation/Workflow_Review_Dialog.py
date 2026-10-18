"""Main-thread review of source/master/destination differences before writes."""
import tkinter as tk
from tkinter import ttk


def open_workflow_review(parent,review,complete):
    previous=parent.grab_current()
    top=tk.Toplevel(parent);top.title('Invoice workflow review');top.geometry('1080x650');top.transient(parent);top.grab_set()
    frame=ttk.Frame(top,padding=20);frame.pack(fill='both',expand=True)
    blocking=any(row['blocking'] for row in review.issues)
    ttk.Label(frame,text='Correct required fields' if blocking else 'Review invoice and Tally differences',font=('Segoe UI',17,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Destination: '+review.company+' · No units, masters or vouchers have been sent for this company.',wraplength=1020).pack(anchor='w',pady=10)
    area=ttk.Frame(frame);area.pack(fill='both',expand=True)
    table=ttk.Treeview(area,columns=('invoice_number','field','invoice','master','reason'),show='headings')
    for key,label,width in [('invoice_number','Invoice',140),('field','Field',130),('invoice','Invoice value',190),('master','Tally value',190),('reason','Reason',350)]:
        table.heading(key,text=label);table.column(key,width=width,minwidth=85)
    table.grid(row=0,column=0,sticky='nsew');area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
    scroll=ttk.Scrollbar(area,orient='vertical',command=table.yview);scroll.grid(row=0,column=1,sticky='ns');table.config(yscrollcommand=scroll.set)
    horizontal=ttk.Scrollbar(area,orient='horizontal',command=table.xview);horizontal.grid(row=1,column=0,sticky='ew');table.config(xscrollcommand=horizontal.set)
    for row in review.issues:table.insert('','end',values=tuple(row.get(k,'') for k in ('invoice_number','field','invoice','master','reason')))
    text=('Close this import, double-click the invoice, correct the required details and save changes to XML. Source changes require processing again.' if blocking else
          'Proceeding preserves the printed invoice values and current new-master fallback. Conflicting existing GSTINs are not overwritten. Tally may still reject invalid data. Your decision is recorded for this exact output and destination.')
    ttk.Label(frame,text=text,wraplength=1020).pack(anchor='w',pady=14)
    consent=tk.BooleanVar(value=False)
    if not blocking:ttk.Checkbutton(frame,text='I reviewed every listed difference and want to proceed with the invoice details.',variable=consent).pack(anchor='w')
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=(15,0));finished=[False]
    def close(answer=False):
        if finished[0]:return
        finished[0]=True;top.destroy()
        if previous is not None and previous.winfo_exists():previous.grab_set()
        complete(answer)
    ttk.Button(buttons,text='Close — review invoices',command=close).pack(side='right')
    if not blocking:
        button=ttk.Button(buttons,text='Proceed with invoice details',state='disabled',command=lambda:close(True))
        button.pack(side='right',padx=10)
        consent.trace_add('write',lambda *a:button.config(state='normal' if consent.get() else 'disabled'))
    top.protocol('WM_DELETE_WINDOW',close)
    return top

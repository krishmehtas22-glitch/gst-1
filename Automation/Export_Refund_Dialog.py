"""Manual export refund review stored separately from invoice values and XML."""
import tkinter as tk
from tkinter import ttk,messagebox
from Export_Refund_Review import summary,load_review,save_review,STATUSES,NOTICE


def open_refund_review(app):
    record=app.selected()
    if app.busy or not record:return
    info=summary(record)
    if not info['export']:
        messagebox.showinfo('Export refund review','Select an analysed export invoice first.',parent=app.window);return
    try:saved=load_review(app.root,record) or {}
    except ValueError as exc:messagebox.showerror('Export refund review',str(exc),parent=app.window);return
    top=tk.Toplevel(app.window);top.title('Export IGST refund review');top.geometry('740x610');top.transient(app.window)
    panel=ttk.Frame(top,padding=20);panel.pack(fill='both',expand=True)
    inv=record.get('invoice') or {}
    ttk.Label(panel,text='Export IGST refund review',font=('Segoe UI',14,'bold')).pack(anchor='w')
    for text in ['Invoice: '+str(inv.get('number') or '—'),'Export country: '+str(info['country'] or inv.get('buyer_country') or 'Required'),
                 'IGST per invoice (INR): '+str(info['estimate'] or 'Not estimated'),'Check: '+info['status']]:
        ttk.Label(panel,text=text,wraplength=690).pack(anchor='w',pady=3)
    ttk.Label(panel,text=NOTICE,wraplength=690,foreground='#78530d').pack(anchor='w',pady=10)
    if info['reason'] and info['reason']!=NOTICE:ttk.Label(panel,text=info['reason'],wraplength=690,foreground='#a02c3e').pack(anchor='w',pady=4)
    form=ttk.Frame(panel);form.pack(fill='x',pady=10);form.columnconfigure(1,weight=1)
    status=tk.StringVar(value=saved.get('status','Unreviewed'));claim=tk.StringVar(value=saved.get('claim_amount') or '')
    reference=tk.StringVar(value=saved.get('reference',''))
    for row,label in enumerate(('Review status','Reviewed claim amount (INR)','Claim / shipping bill reference')):ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
    ttk.Combobox(form,textvariable=status,values=STATUSES,state='readonly').grid(row=0,column=1,sticky='ew')
    ttk.Entry(form,textvariable=claim).grid(row=1,column=1,sticky='ew')
    ttk.Entry(form,textvariable=reference).grid(row=2,column=1,sticky='ew')
    ttk.Label(panel,text='Review notes / basis').pack(anchor='w')
    notes=tk.Text(panel,height=4,wrap='word',font=('Segoe UI',10));notes.pack(fill='both',expand=True,pady=(4,12));notes.insert('1.0',saved.get('notes',''))
    bottom=ttk.Frame(panel);bottom.pack(fill='x')
    def edit_invoice():top.destroy();app.review()
    def save():
        try:data=save_review(app.root,record,status.get(),claim.get(),reference.get(),notes.get('1.0','end').strip())
        except (ValueError,OSError) as exc:messagebox.showerror('Refund review',str(exc),parent=top);return
        from Export_Refund_Review import review_key
        app.refund_reviews[review_key(record)]=data
        app.apply_filter();app.status.config(text='Export refund review saved locally. No tax values, XML or Tally entries changed.');top.destroy()
    ttk.Button(bottom,text='Edit invoice / country',command=edit_invoice).pack(side='left')
    ttk.Button(bottom,text='Save review',command=save).pack(side='right')
    ttk.Button(bottom,text='Close',command=top.destroy).pack(side='right',padx=8)

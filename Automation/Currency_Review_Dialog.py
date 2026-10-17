"""Explicit local rate entry and preview; no AI requests or Tally writes."""
import tkinter as tk
from tkinter import ttk,messagebox
from Common_Rules.foreign_currency import CODES,convert,load_settings,save_settings,currency_code


def open_currency_review(app):
    record=app.selected()
    if app.busy or not record:return
    if record.get('listing_only'):
        try:record=app.prepare_manual_review(record)
        except (ValueError,OSError) as exc:
            messagebox.showerror('Currency / exchange rate',str(exc),parent=app.window);return
        if record is None:return
    inv=record.get('invoice') or {}
    try:saved=load_settings(app.root,record) or {}
    except (ValueError,OSError):saved={}
    raw=saved.get('currency') or inv.get('foreign_currency') or inv.get('currency') or ''
    try:raw=currency_code(raw) or ''
    except ValueError:pass
    top=tk.Toplevel(app.window);top.title('Currency / exchange rate');top.geometry('680x560');top.transient(app.window)
    panel=ttk.Frame(top,padding=20);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='Currency / exchange rate',font=('Segoe UI',14,'bold')).pack(anchor='w')
    ttk.Label(panel,text='Invoice: '+str(inv.get('number') or '—')).pack(anchor='w',pady=6)
    ttk.Label(panel,text='Original total: '+str(inv.get('total') or 'Not read')+' · currency: '+str(inv.get('currency') or 'Not read'),wraplength=620).pack(anchor='w')
    ttk.Label(panel,text='Enter the invoice rate as INR per ONE unit of foreign currency. Original amounts are retained. No AI credits are used.',wraplength=620).pack(anchor='w',pady=12)
    form=ttk.Frame(panel);form.pack(fill='x');form.columnconfigure(1,weight=1)
    code=tk.StringVar(value=raw);rate=tk.StringVar(value=saved.get('exchange_rate') or inv.get('exchange_rate') or '')
    if not saved and inv.get('exchange_rate'):
        from decimal import Decimal,InvalidOperation
        try:
            units=Decimal(str(inv.get('exchange_rate_units') or '1'));printed=Decimal(str(inv['exchange_rate']))
            direction=inv.get('exchange_rate_basis','INR_per_foreign')
            rate.set(format(units/printed if direction=='foreign_per_INR' else printed/units,'f') if direction in ('foreign_per_INR','INR_per_foreign') else '')
        except (ValueError,InvalidOperation,ArithmeticError):rate.set('')
    basis=tk.StringVar(value=saved.get('amounts_basis') or ('INR' if str(inv.get('currency')).upper()=='INR' else 'foreign'))
    for row,label in enumerate(('Invoice currency','INR per 1 foreign currency unit','Current source amounts are')):
        ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=(0,15),pady=8)
    ttk.Combobox(form,textvariable=code,values=sorted(CODES),width=25).grid(row=0,column=1,sticky='ew')
    ttk.Entry(form,textvariable=rate).grid(row=1,column=1,sticky='ew')
    ttk.Combobox(form,textvariable=basis,values=('foreign','INR'),state='readonly').grid(row=2,column=1,sticky='ew')
    ttk.Label(panel,text='foreign = convert the displayed source amounts; INR = already converted, do not multiply again.',wraplength=620).pack(anchor='w',pady=8)
    preview=tk.StringVar(value='Preview the INR amounts before saving.')
    ttk.Label(panel,textvariable=preview,wraplength=620,foreground='#244c87').pack(anchor='w',pady=12)
    def settings():return {'currency':currency_code(code.get()),'exchange_rate':rate.get(),'amounts_basis':basis.get()}
    def calculate():
        try:
            options=settings()
            if not options['currency']:raise ValueError('Choose the invoice currency.')
            result=convert(inv,options)
            preview.set('INR taxable: '+str(result.get('taxable','—'))+' · GST: CGST '+str(result.get('cgst','—'))+' / SGST '+str(result.get('sgst','—'))+' / IGST '+str(result.get('igst','—'))+'\nINR total: '+str(result.get('total','—')))
        except ValueError as exc:preview.set(str(exc))
    def save():
        try:save_settings(app.root,record,code.get(),rate.get(),basis.get())
        except (ValueError,OSError) as exc:messagebox.showerror('Currency / exchange rate',str(exc),parent=top);return
        top.destroy();app.reset();app.revalidate(client_names=[record['client']])
    buttons=ttk.Frame(panel);buttons.pack(side='bottom',fill='x',pady=12)
    ttk.Button(buttons,text='Preview INR',command=calculate).pack(side='left')
    ttk.Button(buttons,text='Save rate & prepare XML',command=save).pack(side='right')
    ttk.Button(buttons,text='Close',command=top.destroy).pack(side='right',padx=8)
    calculate()

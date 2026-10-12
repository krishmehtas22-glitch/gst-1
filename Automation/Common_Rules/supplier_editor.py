"""Desktop form for reusable PDF labels, sections and item header aliases."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox

from .extraction import FIELDS, HEADERS, text_from_pdf
from .supplier_layouts import load_layouts, new_layout, preview_layout, save_layout, remove_layout


def open_layout_editor(parent,root,record,demo,on_done):
    if record.get('source_invoice',record['invoice']).get('source_ocr'):
        messagebox.showinfo('Supplier layout','Scanned PDFs need per-invoice OCR review. Use a text PDF as the layout sample.',parent=parent)
        on_done(False)
        return
    try:
        text=text_from_pdf(record['path'])
        layouts=[layout for layout in load_layouts(root) if layout['seller_gstin']==str(record['invoice'].get('seller_gstin','')).upper() and layout['demo']==demo]
    except Exception as exc:
        messagebox.showerror('Supplier layout',str(exc),parent=parent)
        on_done(False)
        return
    current=next((layout for layout in layouts if layout['id']==record['invoice'].get('supplier_layout_id')),None)
    top=tk.Toplevel(parent);top.title('Save supplier layout');top.geometry('1300x740')
    top.transient(parent);top.grab_set()
    active={'layout':deepcopy(current) if current else new_layout(record,demo)}
    def close(changed=False):
        top.destroy();on_done(changed)
    top.protocol('WM_DELETE_WINDOW',close)
    controls=ttk.Frame(top,padding=8);controls.pack(fill='x')
    choices={'New layout':None}
    for layout in layouts:
        label=layout['name'];index=2
        while label in choices:
            label=layout['name']+' ('+str(index)+')';index+=1
        choices[label]=layout
    selected=tk.StringVar(value=next((label for label,layout in choices.items() if current and layout and layout['id']==current['id']),'New layout'))
    ttk.Label(controls,text='Saved layouts:').pack(side='left')
    picker=ttk.Combobox(controls,textvariable=selected,values=list(choices),state='readonly',width=32)
    picker.pack(side='left',padx=6)
    ttk.Label(controls,text='Dummy mode' if demo else 'Real invoice mode').pack(side='right')
    identity=ttk.Frame(top,padding=(8,0));identity.pack(fill='x')
    name=tk.StringVar();gstin=tk.StringVar();anchors=tk.StringVar()
    for label,variable,width in [('Layout name',name,30),('Seller GSTIN',gstin,20),('Layout headings (separate with ;)',anchors,45)]:
        ttk.Label(identity,text=label).pack(side='left',padx=4)
        ttk.Entry(identity,textvariable=variable,width=width).pack(side='left')
    ttk.Label(top,text='Read each new PDF using its printed labels. Leave recognized fields blank. Use headings/columns to separate seller and buyer.').pack(anchor='w',padx=10,pady=6)
    body=ttk.Panedwindow(top,orient='horizontal');body.pack(fill='both',expand=True,padx=8)
    source=ttk.Frame(body);body.add(source,weight=1)
    ttk.Label(source,text='Sample PDF text — select and copy labels/headings').pack(anchor='w')
    source_text=tk.Text(source,wrap='none',width=48,font=('Courier',8))
    vertical=ttk.Scrollbar(source,orient='vertical',command=source_text.yview)
    horizontal=ttk.Scrollbar(source,orient='horizontal',command=source_text.xview)
    source_text.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
    vertical.pack(side='right',fill='y');horizontal.pack(side='bottom',fill='x');source_text.pack(fill='both',expand=True)
    source_text.insert('1.0',text);source_text.config(state='disabled')
    notebook=ttk.Notebook(body);body.add(notebook,weight=2)
    fields_tab=ttk.Frame(notebook);items_tab=ttk.Frame(notebook,padding=8)
    notebook.add(fields_tab,text='Invoice fields');notebook.add(items_tab,text='Item columns')
    canvas=tk.Canvas(fields_tab)
    scrollbar=ttk.Scrollbar(fields_tab,orient='vertical',command=canvas.yview)
    xbar=ttk.Scrollbar(fields_tab,orient='horizontal',command=canvas.xview)
    canvas.configure(yscrollcommand=scrollbar.set,xscrollcommand=xbar.set)
    scrollbar.pack(side='right',fill='y');xbar.pack(side='bottom',fill='x');canvas.pack(fill='both',expand=True)
    form=ttk.Frame(canvas,padding=5);canvas.create_window((0,0),window=form,anchor='nw')
    form.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
    for col,label in enumerate(('Invoice field','PDF label','Start heading','End heading','Column','Read')):
        ttk.Label(form,text=label).grid(row=0,column=col,padx=3)
    variables={}
    for row,key in enumerate(FIELDS,1):
        ttk.Label(form,text=key.replace('_',' ').title()).grid(row=row,column=0,sticky='w',padx=3)
        values={field:tk.StringVar() for field in ('label','start','end','column','position')}
        variables[key]=values
        for col,field in enumerate(('label','start','end'),1):
            ttk.Entry(form,textvariable=values[field],width=17 if field=='label' else 14).grid(row=row,column=col,padx=2,pady=2)
        ttk.Combobox(form,textvariable=values['column'],values=('Both','Left','Right'),state='readonly',width=6).grid(row=row,column=4)
        ttk.Combobox(form,textvariable=values['position'],values=('After label','First line'),state='readonly',width=10).grid(row=row,column=5)
    ttk.Label(items_tab,text='Enter alternative printed header names, separated by ;.\nExample: Quantity → Pieces; Count. Keep blank for standard headers.').grid(row=0,column=0,columnspan=2,sticky='w',pady=6)
    item_variables={}
    for row,key in enumerate(HEADERS,1):
        ttk.Label(items_tab,text=key.replace('_',' ').title()).grid(row=row,column=0,sticky='w',padx=6)
        item_variables[key]=tk.StringVar()
        ttk.Entry(items_tab,textvariable=item_variables[key],width=44).grid(row=row,column=1,pady=3)
    result=tk.Text(top,height=7,wrap='word');result.pack(fill='x',padx=8,pady=6)
    def load():
        layout=active['layout'];name.set(layout['name']);gstin.set(layout['seller_gstin'])
        anchors.set('; '.join(layout.get('anchors',[])))
        for key,values in variables.items():
            rule=layout.get('fields',{}).get(key,{})
            for field,var in values.items():
                value=rule.get(field,'whole' if field=='column' else 'label' if field=='position' else '')
                if field=='column':value={'whole':'Both','left':'Left','right':'Right'}[value]
                if field=='position':value={'label':'After label','first_line':'First line'}[value]
                var.set(value)
        for key,var in item_variables.items():var.set('; '.join(layout.get('headers',{}).get(key,[])))
        result.delete('1.0','end')
    def choose(event=None):
        active['layout']=deepcopy(choices[selected.get()]) if choices[selected.get()] else new_layout(record,demo)
        load()
    picker.bind('<<ComboboxSelected>>',choose)
    def collect():
        layout=deepcopy(active['layout']);layout.update(name=name.get().strip(),seller_gstin=gstin.get().strip().upper(),anchors=[a.strip() for a in anchors.get().split(';') if a.strip()])
        layout['fields']={}
        for key,values in variables.items():
            position={'After label':'label','First line':'first_line'}.get(values['position'].get(),values['position'].get())
            if values['label'].get().strip() or position=='first_line':
                rule={field:var.get().strip() for field,var in values.items()}
                rule['position']=position
                rule['column']={'Both':'whole','Left':'left','Right':'right'}.get(rule['column'],rule['column'])
                layout['fields'][key]=rule
        layout['headers']={key:[alias.strip() for alias in var.get().split(';') if alias.strip()] for key,var in item_variables.items() if var.get().strip()}
        return layout
    def preview():
        result.delete('1.0','end')
        try:
            parsed,errors=preview_layout(text,collect(),demo)
            summary=' | '.join(str(parsed.get(key,'Missing '+key)) for key in ('seller_name','seller_gstin','number','date','buyer_name','total'))
            taxes=' | '.join(key.upper()+': '+str(parsed.get(key,'Missing')) for key in ('classification','taxable','cgst','sgst','igst'))
            items='\n'.join('Item '+str(i)+': '+' | '.join(key+': '+str(item.get(key,'Missing')) for key in ('name','hsn','quantity','unit','rate','value','cgst_rate','sgst_rate','igst_rate')) for i,item in enumerate(parsed.get('items',[]),1))
            result.insert('end',summary+'\n'+taxes+'\n'+items+'\n'+('\n'.join(errors) if errors else 'Sample balances. Compare these values with the original PDF before saving.'))
            return not errors
        except (ValueError,ArithmeticError,TypeError,KeyError) as exc:
            result.insert('end',str(exc));return False
    def save():
        if not preview():return
        try:
            save_layout(root,record,collect(),demo)
        except (ValueError,ArithmeticError,OSError,TypeError,KeyError) as exc:
            messagebox.showerror('Save supplier layout',str(exc),parent=top);return
        close(True)
    def remove():
        try:
            remove_layout(root,active['layout'])
        except (ValueError,OSError) as exc:
            messagebox.showerror('Remove layout',str(exc),parent=top);return
        close(True)
    buttons=ttk.Frame(top,padding=8);buttons.pack(fill='x')
    ttk.Button(buttons,text='Preview mapping',command=preview).pack(side='left')
    ttk.Button(buttons,text='Save supplier layout',command=save).pack(side='left',padx=8)
    ttk.Button(buttons,text='Remove saved layout',command=remove).pack(side='left')
    ttk.Button(buttons,text='Close',command=close).pack(side='right')
    load()

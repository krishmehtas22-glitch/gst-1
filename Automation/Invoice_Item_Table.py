"""Editable stock/GST table sharing the invoice editor's original variables."""
import tkinter as tk
from tkinter import ttk

COLS=(('name','Stock / service',28),('hsn','HSN / SAC',12),('quantity','Quantity',12),
      ('unit','Unit',12),('rate','Unit price',12),('value','Taxable value',14),
      ('cgst_rate','CGST %',10),('sgst_rate','SGST %',10),('igst_rate','IGST %',10),
      ('printed_total','Printed row total',16))


class InvoiceItemTable(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        ttk.Label(self,text='Editable stock, units, HSN and GST — shared with the detailed item fields below.').pack(anchor='w')
        area=ttk.Frame(self);area.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(area,height=140,highlightthickness=0,bg='white')
        self.canvas.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(area,orient='vertical',command=self.canvas.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(area,orient='horizontal',command=self.canvas.xview);horizontal.grid(row=1,column=0,sticky='ew')
        self.canvas.configure(xscrollcommand=horizontal.set,yscrollcommand=vertical.set)
        area.columnconfigure(0,weight=1);area.rowconfigure(0,weight=1)
        self.host=ttk.Frame(self.canvas);self.canvas.create_window(0,0,window=self.host,anchor='nw')
        self.host.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.rows={}
        for col,(_,caption,_) in enumerate(COLS):ttk.Label(self.host,text=caption).grid(row=0,column=col,sticky='w',padx=4,pady=5)

    def sync(self,originals):
        for key in list(self.rows):
            if key not in originals:
                for widget in self.rows.pop(key):widget.destroy()
        for row,(key,frame) in enumerate(originals.items(),1):
            if key not in self.rows:
                variables={}
                for widget in frame.winfo_children():
                    if isinstance(widget,ttk.Label):
                        label=widget.cget('text')
                        pos=widget.grid_info()
                        entry=next((w for w in frame.winfo_children() if isinstance(w,(ttk.Entry,ttk.Combobox)) and w.grid_info().get('row')==pos.get('row') and w.grid_info().get('column')==pos.get('column',0)+1),None)
                        if entry is not None:variables[label]=entry
                cells=[]
                for col,(field,_,width) in enumerate(COLS):
                    old=variables[field.replace('_',' ').title()]
                    options={'textvariable':old.cget('textvariable'),'width':width}
                    if isinstance(old,ttk.Combobox):options['values']=old.cget('values')
                    cell=type(old)(self.host,**options);cells.append(cell)
                self.rows[key]=cells
            for col,cell in enumerate(self.rows[key]):cell.grid(row=row,column=col,sticky='ew',padx=2,pady=2)

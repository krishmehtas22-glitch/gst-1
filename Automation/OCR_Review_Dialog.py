"""Show retained OCR evidence without re-reading a document or calling AI."""
import tkinter as tk
from tkinter import ttk,messagebox


def open_ocr_review(app):
    record=app.selected()
    if app.busy or not record:return
    evidence=(record.get('invoice') or {}).get('ocr_reading_evidence') or []
    if not evidence:
        messagebox.showinfo('OCR reading evidence','No retained OCR ambiguity evidence for this invoice. Saved older AI reads are reused; open Review to inspect the source.',parent=app.window);return
    top=tk.Toplevel(app.window);top.title('OCR reading evidence');top.geometry('930x620');top.transient(app.window)
    panel=ttk.Frame(top,padding=18);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='OCR readings — compare with the original invoice',font=('Segoe UI',13,'bold')).pack(anchor='w')
    ttk.Label(panel,text='Alternate readings are suggestions. Original text and manual corrections are retained; numbers and product codes are never automatically rewritten.',wraplength=880).pack(anchor='w',pady=8)
    content=tk.Text(panel,wrap='word',font=('Segoe UI',10));content.pack(fill='both',expand=True)
    scroll=ttk.Scrollbar(content,command=content.yview);scroll.pack(side='right',fill='y');content.configure(yscrollcommand=scroll.set)
    for row in evidence:
        content.insert('end','Page '+str(row.get('page','?'))+' · '+str(row.get('reason','Review required'))+'\nOriginal OCR: '+str(row.get('primary','—'))+'\n')
        for alternate in row.get('alternatives',[]):content.insert('end','Second read: '+str(alternate['text'])+'\n')
        if row.get('numeric_conflict'):content.insert('end','Numeric disagreement: alternate numbers were withheld from AI hints. Verify the source.\n')
        if row.get('retry_status'):content.insert('end',row['retry_status']+'\n')
        content.insert('end','\n')
    content.config(state='disabled');buttons=ttk.Frame(panel);buttons.pack(fill='x',pady=10)
    ttk.Button(buttons,text='Open source invoice',command=app.open_source).pack(side='left')
    def edit():top.destroy();app.review()
    ttk.Button(buttons,text='Edit invoice',command=edit).pack(side='left',padx=10)
    ttk.Button(buttons,text='Close',command=top.destroy).pack(side='right')

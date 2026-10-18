"""Source-linked import decisions, with actions visible on smaller displays."""
from pathlib import Path
import os,subprocess
import tkinter as tk
from tkinter import ttk,messagebox
from Common_Rules.workflow_validation import cannot_override


def open_source_document(row):
    path=Path(row.get('source') or '')
    root=Path(row.get('root') or '')
    if not row.get('source') or not row.get('root') or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Source document is unavailable. Restore the original file in the invoice folder, then refresh and process it again.')
    if os.name=='nt':os.startfile(str(path))
    else:subprocess.Popen(['xdg-open',str(path)])


def open_workflow_review(parent,review,complete):
    previous=parent.grab_current()
    top=tk.Toplevel(parent);top._billsync_custom=True
    top.title('Invoice workflow review');top.transient(parent)
    width=min(1120,top.winfo_screenwidth()-60);height=min(650,top.winfo_screenheight()-100)
    top.geometry(f'{width}x{height}+{max(0,(top.winfo_screenwidth()-width)//2)}+20')
    top.minsize(min(760,width),min(460,height));top.grab_set()
    top.columnconfigure(0,weight=1);top.rowconfigure(1,weight=1)
    banner=ttk.Frame(top,padding=(18,12),style='Header.TFrame');banner.grid(row=0,column=0,sticky='ew')
    tk.Label(banner,text='Review before importing',bg='#101d35',fg='white',font=('Segoe UI',17,'bold')).pack(anchor='w')
    tk.Label(banner,text='Destination: '+review.company+' · This group has not been sent.',bg='#101d35',fg='#c6d3ee').pack(anchor='w',pady=(4,0))
    body=ttk.Frame(top,padding=(16,10));body.grid(row=1,column=0,sticky='nsew');body.columnconfigure(0,weight=1);body.rowconfigure(1,weight=1)
    ttk.Label(body,text='Select an issue to view its source and next step. Closing this window cancels all remaining imports.').grid(row=0,column=0,sticky='w',pady=(0,8))
    area=ttk.Frame(body);area.grid(row=1,column=0,sticky='nsew');area.rowconfigure(0,weight=1);area.columnconfigure(0,weight=1)
    keys=('invoice_number','field','invoice','master','source','reason')
    table=ttk.Treeview(area,columns=keys,show='headings',height=5)
    for key,label,colwidth in zip(keys,('Invoice','Field','Invoice value','Tally value','Source document','Reason'),(135,145,170,170,230,400)):
        table.heading(key,text=label);table.column(key,width=colwidth,minwidth=85)
    table.grid(row=0,column=0,sticky='nsew')
    scroll=ttk.Scrollbar(area,orient='vertical',command=table.yview);scroll.grid(row=0,column=1,sticky='ns')
    horizontal=ttk.Scrollbar(area,orient='horizontal',command=table.xview);horizontal.grid(row=1,column=0,sticky='ew')
    table.config(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
    for index,row in enumerate(review.issues):
        table.insert('','end',iid=str(index),values=tuple(Path(row[k]).name if k=='source' and row.get(k) else row.get(k,'') for k in keys))
    detail=tk.Text(body,height=4,wrap='word',font=('Segoe UI',10),relief='flat',background='#f1f5ff',padx=10,pady=8)
    detail.grid(row=2,column=0,sticky='ew',pady=(8,0))
    def selected():
        ids=table.selection()
        return review.issues[int(ids[0])] if ids else {}
    def describe(event=None):
        row=selected();text=row.get('reason','')+'\nSource: '+str(row.get('source') or 'Unavailable — re-process this invoice to link its source.')
        text+='\nNext step: '+('Restore/re-process the source and prepare fresh XML.' if cannot_override(row) else 'Open the source to compare. Edit invoice to correct it, or acknowledge the listed issues and import the unchanged XML.')
        detail.config(state='normal');detail.delete('1.0','end');detail.insert('1.0',text);detail.config(state='disabled')
        for b in source_buttons:b.config(state='normal' if row.get('source') else 'disabled')
    footer=ttk.Frame(top,padding=(16,10));footer.grid(row=2,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
    blocked=any(cannot_override(p) for p in review.issues)
    text=('Import unavailable: source, saved review, extraction or master snapshot needs updating. Select the issue for instructions.' if blocked else
          'Import anyway keeps these values, including missing/invalid fields. Tally may reject them. Your decision is recorded; no values are invented.')
    explanation=ttk.Label(footer,text=text,wraplength=width-40);explanation.grid(row=0,column=0,sticky='ew',pady=(0,6))
    consent=tk.BooleanVar(value=False)
    ttk.Checkbutton(footer,text='I reviewed the issues and authorise importing these invoice values.',variable=consent,state='disabled' if blocked else 'normal').grid(row=1,column=0,sticky='w')
    buttons=ttk.Frame(footer);buttons.grid(row=2,column=0,sticky='ew',pady=(10,0))
    finished=[False]
    def close(answer=False):
        if finished[0]:return
        finished[0]=True;top.destroy()
        if previous is not None and previous.winfo_exists():previous.grab_set()
        complete(answer)
    def view():
        try:open_source_document(selected())
        except (OSError,ValueError) as exc:messagebox.showerror('Source document',str(exc),parent=top)
    source_buttons=[ttk.Button(buttons,text='Open source PDF / image',command=view),ttk.Button(buttons,text='Edit invoice',command=lambda:close({'action':'edit','issue':selected()}))]
    for button in source_buttons:button.pack(side='left',padx=(0,8))
    button=ttk.Button(buttons,text='Import to Tally anyway',state='disabled',style='Primary.TButton',command=lambda:close(True));button.pack(side='right')
    ttk.Button(buttons,text='Cancel import',command=close).pack(side='right',padx=8)
    consent.trace_add('write',lambda *a:button.config(state='normal' if consent.get() and not blocked else 'disabled'))
    table.bind('<<TreeviewSelect>>',describe)
    if review.issues:table.selection_set('0');table.focus('0')
    describe();top.protocol('WM_DELETE_WINDOW',close)
    return top

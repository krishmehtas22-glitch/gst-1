"""Small rounded presentation controls; no reader or accounting behavior."""
import tkinter as tk
from tkinter import ttk, font as tkfont


def rounded_box(canvas,x,y,w,h,r=7,**options):
    return canvas.create_polygon(x+r,y,w-r,y,w,y,w,y+r,w,h-r,w,h,w-r,h,x+r,h,x,h,x,h-r,x,y+r,x,y,smooth=True,splinesteps=24,**options)


class ActionButton(tk.Canvas):
    """Bordered rounded button with mouse, Tab, Return and Space activation."""
    def __init__(self,parent,text,command,style='TButton',width=None,**kwargs):
        primary=style in ('Primary.TButton','Upload.TButton')
        self.fill='#2460ed' if primary else '#fff4f4' if style=='Stop.TButton' else '#ffffff'
        self.ink='#ffffff' if primary else '#bd2838' if style=='Stop.TButton' else '#25364e'
        self.border='#2460ed' if primary else '#e7a5ac' if style=='Stop.TButton' else '#b8c7dc'
        self.hover='#164cd0' if primary else '#ffe9eb' if style=='Stop.TButton' else '#eef4ff'
        self.text=text;self.command=command;self.over=False;self.pressed=False
        self.text_font=tkfont.Font(family='Segoe UI',size=11 if style=='Upload.TButton' else 9)
        parent_style=parent.cget('style') if isinstance(parent,ttk.Frame) else ''
        background=ttk.Style(parent).lookup(parent_style or 'TFrame','background') or '#f3f6fc'
        super().__init__(parent,width=width or self.text_font.measure(text)+28,height=44 if style=='Upload.TButton' else 33,bg=background,highlightthickness=0,takefocus=True,cursor='hand2',**kwargs)
        self.bind('<Configure>',self.draw)
        self.bind('<Enter>',lambda e:self.hovered(True));self.bind('<Leave>',lambda e:self.hovered(False))
        self.bind('<ButtonPress-1>',self.press);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<Return>',lambda e:self.invoke());self.bind('<space>',lambda e:self.invoke())
        self.bind('<FocusIn>',self.draw);self.bind('<FocusOut>',self.draw)
        self.after_idle(self.draw)

    def draw(self,event=None):
        self.delete('all');w=self.winfo_width()-2;h=self.winfo_height()-2
        rounded_box(self,1,1,w,h,r=12,fill=self.hover if self.over else self.fill,outline='#4678dd' if self.focus_get() is self else self.border,width=2 if self.focus_get() is self else 1)
        self.create_text((w+2)/2,(h+2)/2,text=self.text,font=self.text_font,fill=self.ink)

    def hovered(self,value):self.over=value;self.draw()
    def press(self,event):self.pressed=True;self.focus_set();self.draw()
    def release(self,event):
        pressed=self.pressed;self.pressed=False
        if pressed and 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height():self.invoke()
    def invoke(self):return self.command()

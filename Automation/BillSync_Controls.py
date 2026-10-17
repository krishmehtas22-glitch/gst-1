"""Rounded presentation controls; no reader or accounting behavior."""
import tkinter as tk
from tkinter import ttk, font as tkfont


def rounded_box(canvas,x,y,w,h,r=12,**options):
    r=max(0,min(r,(w-x)/2,(h-y)/2))
    return canvas.create_polygon(x+r,y,w-r,y,w,y,w,y+r,w,h-r,w,h,w-r,h,x+r,h,x,h,x,h-r,x,y+r,x,y,smooth=True,splinesteps=32,**options)


def draw_icon(canvas,name,x,y,size,color):
    """Small vector icons avoid external font/image dependencies in the EXE."""
    s=size;line={'fill':color,'width':1.6,'capstyle':'round','joinstyle':'round'}
    if name=='document':
        canvas.create_rectangle(x+3,y,x+s-3,y+s,outline=color,width=1.6)
        for k in (.35,.55,.75):canvas.create_line(x+7,y+s*k,x+s-7,y+s*k,**line)
    elif name in ('check','clock','alert','settings'):
        canvas.create_oval(x,y,x+s,y+s,outline=color,width=1.6)
        if name=='check':canvas.create_line(x+s*.22,y+s*.52,x+s*.43,y+s*.73,x+s*.8,y+s*.27,**line)
        elif name=='clock':canvas.create_line(x+s*.5,y+s*.22,x+s*.5,y+s*.52,x+s*.75,y+s*.62,**line)
        elif name=='alert':
            canvas.create_line(x+s*.5,y+s*.24,x+s*.5,y+s*.57,**line);canvas.create_oval(x+s*.47,y+s*.74,x+s*.53,y+s*.8,fill=color,outline=color)
        else:canvas.create_oval(x+s*.32,y+s*.32,x+s*.68,y+s*.68,outline=color,width=1.6)
    elif name=='person':
        canvas.create_oval(x+s*.2,y,x+s*.65,y+s*.43,outline=color,width=1.6)
        canvas.create_arc(x,y+s*.42,x+s*.83,y+s*1.12,start=0,extent=180,style='arc',outline=color,width=1.6)
        canvas.create_line(x+s*.85,y+s*.2,x+s*.85,y+s*.6,**line);canvas.create_line(x+s*.66,y+s*.4,x+s*1.04,y+s*.4,**line)
    elif name=='upload':
        canvas.create_line(x+s*.5,y+s*.77,x+s*.5,y+s*.08,**line)
        canvas.create_line(x+s*.26,y+s*.32,x+s*.5,y+s*.08,x+s*.74,y+s*.32,**line)
        canvas.create_line(x+s*.12,y+s*.6,x+s*.12,y+s*.95,x+s*.88,y+s*.95,x+s*.88,y+s*.6,**line)
    elif name=='folder':
        canvas.create_line(x,y+s*.2,x+s*.38,y+s*.2,x+s*.5,y+s*.35,x+s,y+s*.35,x+s,y+s*.9,x,y+s*.9,x,y+s*.2,**line)
        canvas.create_line(x,y+s*.4,x+s,y+s*.4,**line)
    elif name=='refresh':
        canvas.create_arc(x,y,x+s,y+s,start=35,extent=285,style='arc',outline=color,width=1.6)
        canvas.create_line(x+s*.7,y,x+s,y+s*.2,x+s,y-s*.05,**line)
    elif name=='transfer':
        canvas.create_line(x,y+s*.3,x+s,y+s*.3,x+s*.75,y+s*.08,**line)
        canvas.create_line(x+s,y+s*.7,x,y+s*.7,x+s*.25,y+s*.92,**line)
    elif name=='bars':
        for i,h in enumerate((.45,.85,.65)):canvas.create_rectangle(x+i*s*.34,y+s*(1-h),x+i*s*.34+s*.17,y+s,outline=color,width=1.5)


class RoundedCard(tk.Canvas):
    """Measure inner content so DPI/font changes cannot cover or clip the border."""
    def __init__(self,parent,fill='white',border='#dce5f0',minheight=0):
        background=ttk.Style(parent).lookup('TFrame','background') or '#f4f5f1'
        super().__init__(parent,width=1,height=max(1,minheight),bg=background,highlightthickness=0)
        self.fill=fill;self.border=border;self.minheight=minheight
        self.panel=tk.Frame(self,bg=fill)
        self.item=self.create_window(14,12,window=self.panel,anchor='nw')
        self.bind('<Configure>',self.redraw);self.panel.bind('<Configure>',self.redraw)

    def redraw(self,event=None):
        width=max(40,self.winfo_width());height=max(self.minheight,self.panel.winfo_reqheight()+24)
        self.itemconfigure(self.item,width=width-28)
        if int(self.cget('height'))!=height:self.configure(height=height)
        self.delete('background')
        rounded_box(self,1,1,width-2,height-2,r=18,fill=self.fill,outline=self.border,tags='background')
        self.tag_lower('background')


class ActionButton(tk.Canvas):
    """Bordered rounded button with mouse, Tab, Return and Space activation."""
    def __init__(self,parent,text,command,style='TButton',width=None,icon=None,**kwargs):
        primary=style in ('Primary.TButton','Upload.TButton');nav=style in ('Nav.TButton','NavActive.TButton')
        self.fill='#216d59' if primary else '#fff4f4' if style=='Stop.TButton' else '#f1f6ee' if style=='Soft.TButton' else '#112b27' if nav else '#ffffff'
        if style=='NavActive.TButton':self.fill='#2a4b3d'
        self.ink='#ffffff' if primary or nav else '#b43345' if style=='Stop.TButton' else '#216d59' if style in ('Soft.TButton','Text.TButton') else '#1d302b'
        self.border=self.fill if primary or nav or style=='Text.TButton' else '#ead2d7' if style=='Stop.TButton' else '#d2e2ce' if style=='Soft.TButton' else '#dfe6dc'
        self.hover='#18523f' if primary else '#21483b' if nav else '#edf4ec'
        self.text=text;self.command=command;self.icon=icon;self.nav=nav;self.over=False;self.pressed=False
        self.text_font=tkfont.Font(family='Segoe UI',size=11 if style=='Upload.TButton' else 10)
        if isinstance(parent,ttk.Frame):background=ttk.Style(parent).lookup(parent.cget('style') or 'TFrame','background') or '#f4f5f1'
        else:background=parent.cget('bg')
        super().__init__(parent,width=width or self.text_font.measure(text)+28+(24 if icon else 0),height=48 if style=='Upload.TButton' else 43 if nav else 36,bg=background,highlightthickness=0,takefocus=True,cursor='hand2',**kwargs)
        self.bind('<Configure>',self.draw);self.bind('<Enter>',lambda e:self.hovered(True));self.bind('<Leave>',lambda e:self.hovered(False))
        self.bind('<ButtonPress-1>',self.press);self.bind('<ButtonRelease-1>',self.release)
        self.bind('<Return>',lambda e:self.invoke());self.bind('<space>',lambda e:self.invoke())
        self.bind('<FocusIn>',self.draw);self.bind('<FocusOut>',self.draw);self.after_idle(self.draw)

    def draw(self,event=None):
        self.delete('all');w=self.winfo_width()-2;h=self.winfo_height()-2
        focused=self.focus_get() is self
        rounded_box(self,2,2,w-1,h-1,r=14,fill=self.hover if self.over else self.fill,outline='#7ba88a' if focused else self.border,width=2 if focused else 1)
        total=self.text_font.measure(self.text)+(24 if self.icon and self.text else 0)
        left=16 if self.nav else (w-total)/2
        if self.icon:
            draw_icon(self,self.icon,left if self.text else w/2-8,h/2-8,16,self.ink)
            left+=26
        self.create_text(left if self.text else w/2,(h+2)/2,text=self.text,font=self.text_font,fill=self.ink,anchor='w' if self.text else 'center')

    def hovered(self,value):self.over=value;self.draw()
    def press(self,event):self.pressed=True;self.focus_set();self.draw()
    def release(self,event):
        pressed=self.pressed;self.pressed=False
        if pressed and 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height():self.invoke()
    def invoke(self):return self.command()

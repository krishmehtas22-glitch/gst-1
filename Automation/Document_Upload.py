"""Local document intake only. Existing invoice/AI/XML code receives unchanged PDFs."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from Common_Rules.engine import INBOX,invoice_paths

FORMATS={'.pdf','.png','.jpg','.jpeg'}


def client_folder(root,name,create=False):
    root=Path(root).resolve();name=str(name).strip()
    if not name or name.casefold() in ('.','..','common_rules','tests','all clients') or name.startswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]',name) or name.endswith(('.', ' ')):
        raise ValueError('Enter a simple client name without path separators or special characters.')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('This client name is reserved by Windows.')
    folder=root/name
    if folder.is_symlink() or not folder.resolve().is_relative_to(root):raise ValueError('Client folder must stay inside the app storage location.')
    if create:(folder/INBOX).mkdir(parents=True,exist_ok=True)
    return folder


def image_pdf(data):
    from PIL import Image,ImageOps
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.utils import ImageReader
    with Image.open(BytesIO(data)) as source:
        if getattr(source,'n_frames',1)!=1:raise ValueError('Use a single-frame invoice image or upload a PDF.')
        image=ImageOps.exif_transpose(source).convert('RGBA')
        background=Image.new('RGB',image.size,'white');background.paste(image,mask=image.getchannel('A'))
        width,height=image.size
        # One source pixel remains one PDF point; no crop, OCR or invoice inference.
        output=BytesIO();canvas=Canvas(output,pagesize=(width,height),invariant=1,pageCompression=1)
        canvas.drawImage(ImageReader(background),0,0,width=width,height=height)
        canvas.showPage();canvas.save()
        return output.getvalue()


def _store(directory,name,data,root):
    for candidate in (directory,*directory.parents):
        if candidate==root:break
        if candidate.is_symlink():raise ValueError('Upload storage must not contain linked directories.')
    if not directory.resolve().is_relative_to(root):raise ValueError('Upload storage escapes the app folder.')
    directory.mkdir(parents=True,exist_ok=True)
    if directory.is_symlink():raise ValueError('Upload destination must not be a linked folder.')
    stem=Path(name).stem;suffix=Path(name).suffix;index=1
    while True:
        path=directory/(name if index==1 else f'{stem} ({index}){suffix}')
        if path.is_symlink():raise ValueError('Upload destination must not be a linked file.')
        try:
            with path.open('xb') as stream:stream.write(data)
            return path,False
        except FileExistsError:
            if path.is_file() and sha256(path.read_bytes()).digest()==sha256(data).digest():return path,True
            index+=1


def upload_documents(root,client,paths):
    root=Path(root).resolve();folder=client_folder(root,client,create=True)
    destination=folder/INBOX;report={'uploaded':[],'reused':[],'errors':[]}
    for value in paths:
        source=Path(value)
        try:
            if not source.is_file() or source.suffix.lower() not in FORMATS:raise ValueError('Choose a PDF, PNG, JPG or JPEG file.')
            if source.stat().st_size>100*1024*1024:raise ValueError('File is larger than the 100 MB upload limit.')
            data=source.read_bytes()
            if not data:raise ValueError('The file is empty.')
            suffix=source.suffix.lower()
            if suffix=='.pdf':
                from PDF_Upload_Validation import validate_pdf
                validate_pdf(data)
                prepared=data;name=source.name
            else:
                prepared=image_pdf(data);name=source.name+'.pdf'
                originals=root/'.invoice_app'/'original_uploads'
                _store(originals,sha256(data).hexdigest()+suffix,data,root)
            digest=sha256(prepared).digest()
            duplicate=next((p for p in invoice_paths(folder) if not p.is_symlink() and p.resolve().is_relative_to(root) and p.stat().st_size==len(prepared) and sha256(p.read_bytes()).digest()==digest),None)
            target,reused=(duplicate,True) if duplicate is not None else _store(destination,name,prepared,root)
            report['reused' if reused else 'uploaded'].append({'name':source.name,'path':str(target),'source_sha256':sha256(data).hexdigest()})
        except Exception as exc:
            report['errors'].append({'name':source.name,'error':str(exc)})
    return report

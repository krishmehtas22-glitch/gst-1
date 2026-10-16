"""Exercise installer routing with small source payloads, without app/API startup."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import subprocess
import sys
import zlib

import pytest


BEFORE = "APP_VERSION='Reader 7.25'\n\ndef import_tally():\n    pass\n"
AFTER = BEFORE.replace('7.25', '7.27')


def installer(root):
    source=(Path(__file__).resolve().parents[2]/'Apply_AI_First_Reader_7_27.py').read_text()
    assignment=next(n for n in ast.parse(source).body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='DATA' for t in n.targets))
    data=[dict(path='Invoice_Desktop.py',text=AFTER,create=False,
               sha256=hashlib.sha256(AFTER.encode()).hexdigest(),
               before=[hashlib.sha256(BEFORE.encode()).hexdigest()])]
    encoded=repr(base64.b64encode(zlib.compress(json.dumps(data).encode())).decode())
    lines=source.splitlines(keepends=True)
    start=sum(map(len,lines[:assignment.value.lineno-1]))+assignment.value.col_offset
    end=sum(map(len,lines[:assignment.value.end_lineno-1]))+assignment.value.end_col_offset
    path=root/'Apply_AI_First_Reader_7_27.py';path.write_text(source[:start]+encoded+source[end:])
    return path


def app(root, text):
    root.mkdir(parents=True,exist_ok=True);(root/'Common_Rules').mkdir()
    path=root/'Invoice_Desktop.py';path.write_text(text);return path


@pytest.mark.parametrize('location',['flat','nested','both'])
def test_installer_updates_the_documented_app_when_two_copies_exist(tmp_path,location):
    flat=app(tmp_path,BEFORE) if location in ('flat','both') else None
    nested=app(tmp_path/'Automation',AFTER if location=='both' else BEFORE) if location in ('nested','both') else None
    result=subprocess.run([sys.executable,str(installer(tmp_path))],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    chosen=flat or nested
    assert chosen.read_text()==AFTER and 'Updating desktop source: '+str(chosen) in result.stdout
    if location=='both':assert nested.read_text()==AFTER


def test_an_unknown_flat_copy_does_not_fall_back_to_already_updated_nested_copy(tmp_path):
    flat=app(tmp_path,BEFORE+'\n# user edit\n');nested=app(tmp_path/'Automation',AFTER)
    before=flat.read_bytes()
    result=subprocess.run([sys.executable,str(installer(tmp_path))],capture_output=True,text=True)
    assert result.returncode!=0 and 'Unknown local source preserved' in result.stderr
    assert flat.read_bytes()==before and nested.read_text()==AFTER
    assert 'already installed' not in result.stdout


def test_already_installed_message_identifies_the_exact_flat_copy(tmp_path):
    flat=app(tmp_path,AFTER);nested=app(tmp_path/'Automation',BEFORE)
    result=subprocess.run([sys.executable,str(installer(tmp_path))],capture_output=True,text=True)
    assert result.returncode==0 and 'already installed at: '+str(flat) in result.stdout
    assert nested.read_text()==BEFORE

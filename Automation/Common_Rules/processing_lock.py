"""OS-released processing guards with recoverable, visible lock markers."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone

PROTOCOL='invoice-os-guard-v1'


@contextmanager
def guard(client):
    folder=Path(client)/'.automation';folder.mkdir(parents=True,exist_ok=True)
    stream=(folder/'run.lock.guard').open('a+b')
    acquired=False
    try:
        if stream.seek(0,os.SEEK_END)==0:stream.write(b'\0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            acquired=True
        except OSError as exc:
            raise ValueError('Client is locked by another active invoice process; wait for that run to finish') from exc
        yield folder
    finally:
        if acquired:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


def owner(lock):
    try:return json.loads((lock/'owner.json').read_text())
    except (OSError,ValueError):return {}


@contextmanager
def client_lock(client):
    with guard(client) as folder:
        lock=folder/'run.lock'
        if lock.exists():
            if lock.is_dir() and owner(lock).get('protocol')==PROTOCOL and {p.name for p in lock.iterdir()}=={'owner.json'}:
                # Acquiring the OS guard proves no holder of this protocol remains.
                (lock/'owner.json').unlink();lock.rmdir()
            else:
                raise ValueError('Client is locked by an old processing marker; close other invoice windows and use Recover processing lock once')
        lock.mkdir();token=uuid.uuid4().hex
        (lock/'owner.json').write_text(json.dumps({'protocol':PROTOCOL,'token':token,'pid':os.getpid()}))
        try:yield
        finally:
            if owner(lock).get('token')==token:
                (lock/'owner.json').unlink();lock.rmdir()


def recover_legacy_lock(client):
    """User confirms older app windows are closed; preserve the marker as backup."""
    with guard(client) as folder:
        lock=folder/'run.lock'
        if not lock.exists():return False
        backups=folder/'lock_backups';backups.mkdir(exist_ok=True)
        name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        lock.rename(backups/name)
        return True

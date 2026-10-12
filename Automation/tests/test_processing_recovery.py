"""Crash recovery and concurrent access preserve completed invoice output."""
from pathlib import Path
import os,subprocess,sys,shutil
import pytest
from Common_Rules.processing_lock import client_lock,recover_legacy_lock
from Common_Rules.desktop import process_sources


def test_active_guard_blocks_second_run_and_recovery(tmp_path):
 with client_lock(tmp_path):
  with pytest.raises(ValueError,match='active invoice process'):
   with client_lock(tmp_path):pass
  with pytest.raises(ValueError,match='active invoice process'):recover_legacy_lock(tmp_path)
 assert not (tmp_path/'.automation/run.lock').exists()
 with client_lock(tmp_path):pass


def test_crashed_guard_is_released_and_owned_marker_recovers(tmp_path):
 script='from pathlib import Path; from Common_Rules.processing_lock import client_lock; import os,sys\nwith client_lock(Path(sys.argv[1])): os._exit(17)'
 env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1])}
 child=subprocess.run([sys.executable,'-c',script,str(tmp_path)],env=env)
 assert child.returncode==17
 assert (tmp_path/'.automation/run.lock/owner.json').exists()
 with client_lock(tmp_path):assert (tmp_path/'.automation/run.lock/owner.json').exists()
 assert not (tmp_path/'.automation/run.lock').exists()


def test_unknown_legacy_lock_needs_explicit_recovery_and_is_backed_up(tmp_path):
 lock=tmp_path/'.automation/run.lock';lock.mkdir(parents=True)
 with pytest.raises(ValueError,match='Recover processing lock'):
  with client_lock(tmp_path):pass
 assert recover_legacy_lock(tmp_path)
 assert len(list((tmp_path/'.automation/lock_backups').iterdir()))==1
 with client_lock(tmp_path):pass


def test_busy_company_does_not_modify_retained_sources_or_export(tmp_path):
 shutil.copytree(Path(__file__).parent/'fixtures/client20',tmp_path/'Client')
 rows=process_sources(tmp_path);assert all(not r['errors'] for r in rows)
 company=Path(rows[0]['company_path']);output=Path(rows[0]['output_path'])
 before={str(p.relative_to(company)):p.read_bytes() for p in company.rglob('*') if p.is_file() and '.automation' not in p.parts}
 with client_lock(company):
  blocked=process_sources(tmp_path)
  assert len(blocked)==20 and all(any('locked' in e for e in r['errors']) for r in blocked)
  assert all(r['invoice']['seller_name']=='DEMO MERCANTILE PRIVATE LIMITED' for r in blocked)
  assert before=={str(p.relative_to(company)):p.read_bytes() for p in company.rglob('*') if p.is_file() and '.automation' not in p.parts}
 assert all(not r['errors'] for r in process_sources(tmp_path))

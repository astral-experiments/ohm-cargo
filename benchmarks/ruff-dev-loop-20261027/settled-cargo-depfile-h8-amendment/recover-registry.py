"""Reproduce the two original registry inventories without changing the retained store."""
import contextlib,fcntl,hashlib,json,os,shutil,sys
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028')
V=H/'private-registry-h8-v2';live=H/'cargo-home/.ohm-registry-json-v2'
expected={'workspace':[776,'92443ca50710ac497acdc037ff543f3253a607832f2d19abb511027852d51f30'],'test':[814,'7de26e5582a5ef0edf0e15d0b096f240171c32522e0cfb19bf8816e076cd533b']}

def raw_files(root):return sorted(p for p in root.rglob('*') if p.is_file())
def registry_id(root):
 g=worker();m={str(live/p.relative_to(root)):g['sha'](p) for p in raw_files(root)};return [len(m),g['dig'](m)]
def worker():
 src=(H/'whole-paths.py').read_text();old=sys.argv;sys.argv=[str(H/'whole-paths.py'),'h8','qualify'];g={}
 try:exec(compile(src[:src.rindex('os.umask(0o077)')],str(H/'whole-paths.py'),'exec'),g)
 finally:sys.argv=old
 return g
@contextlib.contextmanager
def activated(mode):
 prior=V/'retained-original';copy=V/mode
 assert live.is_dir() and not live.is_symlink() and not prior.exists() and copy.is_dir() and not copy.is_symlink();assert registry_id(live)==expected['test']
 live.rename(prior)
 try:
  copy.rename(live)
  try:yield
  finally:live.rename(copy)
 finally:prior.rename(live)
 assert registry_id(live)==expected['test']
def main():
 os.umask(0o077);os.sched_setaffinity(0,range(8));g=worker();q=H/'qualified-whole-v1';assert not any(q.glob('*/ir/*/record.json')) and not any(q.glob('*/wall/*/record.json'))
 with g['s'].LOCK.open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX);V.mkdir();cut=(q/'workspace/qual/anchor.json').stat().st_mtime_ns
  shutil.copytree(live,V/'test');ws=V/'workspace';ws.mkdir();os.chmod(ws,live.stat().st_mode & 0o777);files=raw_files(live)
  for f in files:
   if f.stat().st_ctime_ns<=cut:
    copy=ws/f.relative_to(live);copy.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,copy)
  before=registry_id(ws);assert before==[773,'25d544473cc17dbb3d5eed5de312ead62a98f2b7d526befa1170a7d9eb146817']
  assert registry_id(V/'test')==expected['test'];g['switch']('parent')
  with activated('workspace'):
   native=g['invoke'](V/'reconstruction-native','workspace','audit');actual=registry_id(live)
  result=dict(native=g['sha'](V/'reconstruction-native/record.json'),native_units=native['units'],native_physical=native['physical'],retained=registry_id(live),workspace_before=before,workspace_recreated=actual,cutoff_ns=cut,targets={k:g['sha'](q/k/'qual/anchor.json') for k in expected},original_zeros=not any(q.glob('*/ir/*/record.json')) and not any(q.glob('*/wall/*/record.json')))
  for k in expected:
   a=V/k;result[k+'_files']={str(x.relative_to(a)):g['sha'](x) for x in raw_files(a)}
  g['write'](V/'reconstruction.json',result);print({k:v for k,v in result.items() if not k.endswith('_files')},flush=True);assert actual==expected['workspace'] and result['retained']==expected['test']
if __name__=='__main__':main()

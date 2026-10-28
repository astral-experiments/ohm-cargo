"""Keep the completed private state as a verified immutable tar.zst before reusing limited tmp space."""
from pathlib import Path
import sys,os,json,subprocess,shutil,hashlib
import native3 as n
name=sys.argv[1];assert name in ('R-T','T-R');s=n.usr/name
assert s.parent==n.usr and s.is_dir() and not s.is_symlink()
assert len([p for p in n.repo.glob(name+'-*/result.json')])==10
for x in ('ruff','ty'):
 d=n.load(n.repo/(name+'-repeat-restore-'+x)/'result.json');assert d['fresh']==d['units']and not d['native']
n.guard();n.archive.mkdir(parents=True,exist_ok=True);t=n.archive/(name+'.tar.zst');assert not t.exists()
with (n.p/'native-measure.lock').open('rb') as lock:
 import fcntl;fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 old,_=n.manifests(s)
 n.monitored(['tar','-I','zstd -3 -T2','-cf',str(t),'-C',str(s.parent),name],n.repo/(name+'-tar.out'),n.repo/(name+'-tar.err'))
 n.monitored(['tar','-I','zstd -d -T1','--compare','-f',str(t),'-C',str(s.parent),name],n.repo/(name+'-compare.out'),n.repo/(name+'-compare.err'))
 assert t.stat().st_size>100_000_000 and n.manifests(s)[0]==old
 record={'state':name,'private_manifest':old,'tar_zst_sha256':n.sha(t),'bytes':t.stat().st_size,'verified_tar_against_all_current_files':True,'remaining':n.space(t)}
 n.dump(n.repo/(name+'-archive.json'),record);print(name,t.stat().st_size,record['tar_zst_sha256'],flush=True)
 shutil.rmtree(s);n.guard()

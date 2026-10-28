import importlib.util,fcntl,hashlib,os,shutil,subprocess,sys,json
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');spec=importlib.util.spec_from_file_location('f',H/'prepare-path-fixture.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
O=H/'observer-dot-d-control';src=O/'src';active=O/'active';bin=s.RT/'bin/cargo'
def one(arm,tag):
 d=O/arm/tag;d.mkdir(parents=True)
 e=s.env('library');e.update(CARGO_HOME=str(O/'home'),CARGO_TARGET_DIR=str(active/'target'),CARGO_BUILD_BUILD_DIR=str(active/'shared'))
 c=subprocess.run([s.CARGO,'+ohm','build','-p','hold_direct','--offline','--message-format=json'],env=e,cwd=src,capture_output=True)
 (d/'stdout').write_bytes(c.stdout);(d/'stderr').write_bytes(c.stderr);assert c.returncode==0,(tag,c.stderr[-900:])
 rows=[r for l in c.stdout.splitlines() if (r:=json.loads(l)).get('reason')=='compiler-artifact'];unit,=[r for r in rows if r['target']['name']=='hold_direct']
 proof,=[p for p in active.rglob('dep-bin-hold_direct') if p.read_bytes()[-41:-37]==b'OBS1'];raw=proof.read_bytes();(d/'encoded').write_bytes(raw)
 extern=active/'target/debug/hold_direct.d';data=extern.read_bytes();(d/'public.d').write_bytes(data);complete=raw[-33]
 marker=b'ohm-foreign-span-bytes' in data;assert marker==(not complete),(tag,marker,complete)
 r=dict(units=len(rows),fresh=unit['fresh'],complete=complete,marker=marker,exposed_hash=s.sha(extern),native=subprocess.check_output([unit['executable']]).decode().strip(),version=raw[5]);s.save(d/'row.json',r);return proof,r
with s.LOCK.open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);os.sched_setaffinity(0,range(8));O.mkdir();(O/'home').mkdir();shutil.copytree(H/'heldout-fixture',src);out={}
 for arm in ('parent','candidate'):
  tmp=bin.with_name('observer-next');shutil.copy2(H/'subjects'/('qualified-'+arm)/'cargo',tmp);os.replace(tmp,bin);active.mkdir()
  res={}
  for tag in ('first','train','settled','repeat'):
   p,res[tag]=one(arm,tag)
  assert res['first']['complete']==0 and res['train']['complete']==1 and res['settled']['fresh'] and res['repeat']['fresh']
  a=bytearray(p.read_bytes());a[-1]^=1;p.write_bytes(a)
  for tag in ('corrupt','retrain','recovered'):p,res[tag]=one(arm,tag)
  assert not res['corrupt']['fresh'] and res['recovered']['complete'] and res['recovered']['fresh']
  out[arm]=res;active.rename(O/(arm+'-retained-state'))
 assert out['parent']==out['candidate'],out
 s.save(O/'complete.json',out)

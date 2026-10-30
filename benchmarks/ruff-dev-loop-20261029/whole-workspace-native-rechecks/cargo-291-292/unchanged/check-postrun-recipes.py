"""Reopen the literal cached recipe arguments at the end of the uninterrupted six-command run."""
import collections,gzip,hashlib,json,os,runpy,stat
from pathlib import Path
import sys
base=Path(sys.argv[1]);out=Path(sys.argv[2])
role=runpy.run_path(str(base/'ops/argv-classifier-v2/role.py'))['role']
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pathsha(path):return hashlib.sha256(os.fsencode(path)).hexdigest()
body={'scope':'End of six commands. Content readback is independent of the earlier literal per-process pathname observation.','stages':{},'recipes':{}}
for arm in ('K','U'):
 d=base/'state'/arm
 body['stages'][arm]={}
 for phase in ['01-empty','02-first-unchanged','03-second-unchanged']:
  f=d/'evidence'/phase/'native-jobs.json.gz';jobs=json.loads(gzip.decompress(f.read_bytes()));counts=collections.Counter()
  for j in jobs:
   if j['kind'] not in ('rustc-full','rustc-cached','rustc-probe'):continue
   enabled,spelling,literal=role(j['args'])
   if not enabled:continue
   text,=literal
   guest=Path(text);assert guest.is_absolute()
   physical=None
   for n in ('target','shared'):
    if guest.is_relative_to(base/'view'/n):physical=d/n/guest.relative_to(base/'view'/n);break
   assert physical is not None and physical.is_relative_to(d)
   k=arm+'.'+pathsha(text);counts[k]+=1
   if k not in body['recipes']:
    rec={'argument_path_sha256':pathsha(text),'arm':arm,'relative_path_sha256':pathsha(physical.relative_to(d)),'exists_postrun':physical.is_file()}
    if physical.is_file():
     st=physical.lstat();assert stat.S_ISREG(st.st_mode) and not physical.is_symlink()
     with physical.open('rb') as fd:prefix=fd.read(16)
     rec.update(bytes=st.st_size,sha256=digest(physical),header_hex=prefix.hex())
    body['recipes'][k]=rec
  body['stages'][arm][phase]=dict(sorted(counts.items()))
with out.open('xb') as d,gzip.GzipFile(filename='',fileobj=d,mode='wb',mtime=0) as gz:gz.write(json.dumps(body,sort_keys=True,separators=(',',':')).encode()+b'\n')
print('recipe readback',len(body['recipes']),sum(r['exists_postrun'] for r in body['recipes'].values()),digest(out))
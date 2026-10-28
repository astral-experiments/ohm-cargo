"""Produce a compressed index of original profile names without changing the read-only donor."""
from pathlib import Path
import gzip,hashlib,io,json,re,subprocess,sys
from collections import defaultdict
r=Path('/home/dev-user/code/oss/ohm-ruff-current-20261021/work/release14-edge-shipping-v2-20261026/retained-base/rust/build');d=r/'opt-artifacts';tool=r/'x86_64-unknown-linux-gnu/stage1/lib/rustlib/x86_64-unknown-linux-gnu/bin/llvm-profdata';inst=d/'rustc-pgo.profdata';bolt=d/'rustc-bolt.profdata'
def h(p):
 with p.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
a=defaultdict(lambda:[0,0,0]);pg=defaultdict(lambda:[0,0]);pm=0;bm=0;count=0
p=subprocess.Popen([tool,'show','--all-functions','--counts',inst],stdout=subprocess.PIPE);current=None
for s in p.stdout:
 if s.startswith(b'  ') and not s.startswith(b'   ') and s.endswith(b':\n'):
  current=s[2:-2].decode();name=current.split(';',1)[-1];pg[name][0]+=1;pm+=1
 elif s.startswith(b'    Block counts: [') and current is not None:
  values=[int(x) for x in re.findall(rb'\d+',s)];pg[name][1]+=max(values,default=0);current=None;count+=1
assert p.wait()==0 and pm>100_000 and count>100_000,(pm,count)
with bolt.open('rb') as f:
 for l in f:
  v=l.split()
  if len(v)!=8: continue
  n=int(v[7]);bm+=1
  for sign,idx in [(v[0],1),(v[3],4)]:
   if sign==b'1':
    name=re.sub(r'/[0-9]+$','',v[idx].decode());a[name][0]+=1;a[name][1]+=n
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0,compresslevel=4) as gz:
 with io.TextIOWrapper(gz,encoding='utf-8') as w:
  w.write(json.dumps({'instrumented_profile_sha256':h(inst),'bolt_profile_sha256':h(bolt),'llvm_profdata_sha256':h(tool),'instrumentation_records':pm,'max_block_count_records':count,'bolt_branches':bm,'counts':'Record counts and sum of maximum block counts per instrumented function. Sum of both BOLT sampled branch endpoint weights per symbol; no timing estimate.'})+'\n')
  for n in sorted(pg.keys()|a.keys()):
   v=pg.get(n,(0,0));b=a.get(n,(0,0,0));w.write(json.dumps([n,*v,*b[:2]],separators=(',',':'))+'\n')

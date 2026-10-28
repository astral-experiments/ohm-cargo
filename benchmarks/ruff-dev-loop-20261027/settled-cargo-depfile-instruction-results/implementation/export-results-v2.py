"""Export every acquisition row, native receipts, and per-thread IR terminations without registry hostnames."""
import gzip,hashlib,json,os,re,shutil,sys
from pathlib import Path
H=Path('/home/dev-user/.cache/ohm-output-path-ruff-20261028');host=sys.argv[1];S=H/('qualified-whole-h8-v2' if host=='h8' else 'qualified-whole-v1');d=H/('portable-path-results-h8-v2' if host=='h8' else 'portable-path-results');d.mkdir();P=json.loads((H/'plan.json').read_text());raw='socket-'+'firewall-'+'registry'
def store(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def gz(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
def public_json(data):
 # Cargo emits manifest paths in the host's configured registry mirror. Preserve all other bytes and bind both copies.
 return re.sub(rb'socket-' rb'firewall-' rb'registry[.][A-Za-z0-9_.-]+-[a-f0-9]{16}',b'registry-fixture-hash',data)
def copy(f,to):
 b=f.read_bytes();n=public_json(b);assert raw.encode() not in n,(f,n[n.find(raw.encode())-16:n.find(raw.encode())+120]);gz(to,n);return dict(raw_sha256=sha(f),portable_sha256=hashlib.sha256(n).hexdigest())
modes=['library'] if host=='h7' else ['workspace','test'];out=[]
assert (S/'score.json').is_file()
for name in ('qualify.json','score.json'):shutil.copyfile(S/name,d/name)
for x in [H/'ready.json',H/'source-state.json',H/'subjects/qualified-pair.json']:
 copy(x,d/'subject-binding'/(x.name+'.gz'))
for mode in modes:
 root=S/mode;data=d/mode;data.mkdir();q=root/'qual';bind={}
 for arm in ('parent','candidate'):
  for name in (arm+'.json','trace-'+arm+'/record.json','trace-'+arm+'/stdout','trace-'+arm+'/stderr','recreate-'+arm+'/record.json','prepare-'+arm+'/record.json'):
   bind[name]=copy(q/name,data/'native'/(name+'.gz'))
  for p in sorted((q/('trace-'+arm)).glob('exec.*')):
   if p.stat().st_size>0:bind[str(p.relative_to(q))]=copy(p,data/'native'/(str(p.relative_to(q))+'.gz'))
 if host=='h8':
  for arm in ('parent','candidate'):
   prefix='isolation-'+arm
   for n in ['record.json','stdout','stderr']:
    bind[prefix+'/'+n]=copy(root/prefix/n,data/'native'/prefix/(n+'.gz'))
   for p in sorted((root/prefix).glob('exec.*')):
    if p.stat().st_size>0:bind[prefix+'/'+p.name]=copy(p,data/'native'/prefix/(p.name+'.gz'))
 anchor=json.loads((q/'anchor.json').read_bytes());bind['anchor.json']=copy(q/'anchor.json',data/'native/anchor.json.gz')
 for kind,n in [('ir',16),('wall',32)]:
  for i,order in enumerate(P['orders'][mode][kind]):
   for j,arm in enumerate(order):
    r=root/kind/f'{i:02}-{j}-{arm}';v=json.loads((r/'record.json').read_bytes());assert v['rc']==0 and not (r/'stdout').read_bytes();v.update(mode=mode,metric=kind,pair=i,position=j,arm=arm)
    v['stderr_fixture']=copy(r/'stderr',data/(str(r.relative_to(root))+'/stderr.gz'));v['source_record_sha256']=sha(r/'record.json')
    if kind=='ir':
     f,=r.glob('profile-*');assert sha(f)==v['count_sha256'];v['raw_report']=f.read_text();a,=r.glob('*-cargo.args');v['actual_argv_sha256']=sha(a)
    out.append(v)
  for n in ['record.json','stderr','stdout']:
   bind['post-'+kind+'/'+n]=copy(root/('post-'+kind)/n,data/'native'/('post-'+kind)/(n+'.gz'))
  for trace in sorted((root/('post-'+kind)).glob('exec.*')):
   if trace.stat().st_size:bind['post-'+kind+'/'+trace.name]=copy(trace,data/'native'/('post-'+kind)/(trace.name+'.gz'))
 store(data/'original-and-portable.json',bind)
 rows=[v for v in out if v['mode']==mode];assert len(rows)==96;store(data/'observations.json',rows)
 if host=='h7':
  for p in sorted((H/'package-controls-v3').glob('*/nonutf/stderr')):copy(p,data/'controls'/(str(p.relative_to(H/'package-controls-v3'))+'.gz'))
  shutil.copy2(H/'package-controls-v3/complete.json',data/'native/extra-path-controls.json')
names=sorted(p for p in d.rglob('*') if p.is_file());(d/'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(d))+'\n' for p in names));print(host,len(out),len(names),sha(d/'SHA256SUMS'))

from pathlib import Path
import json,hashlib,subprocess,statistics,os
from runpy import run_path
d=Path(__file__).resolve().parent
seal=d/'closure/reversed';m=json.loads((seal/'receipt.json').read_bytes());dest=d/'proof-cost-diagnostics';dest.mkdir()
api=run_path(str(d/'audit.py'));sha=lambda f:hashlib.file_digest(f.open('rb'),'sha256').hexdigest()
for name,packet in m['commands'].items():
 rows=[];input_paths=set();per=[]
 g=Path(packet['saved']).parent
 layout=api['decode_layout']((seal/(name+'.layout')).read_bytes())[0]
 for logical,archive,sl,temporary in layout:
  assert logical.startswith('/') and not temporary and '\n' not in logical and ' ' not in logical
  path=g/logical[1:]; assert path.is_file(),logical
  size=path.stat().st_size
  if not archive:lo,hi=0,size
  else:
   lo,hi,_=archive;assert 0<=lo<=hi<=size
  rows.append((lo,hi-lo,str(path)));input_paths.add(path)
 blob=d/'products/reversed'/name;assert sha(blob)==m['actual'][name]['actual_elf_sha256']
 for kind in ['selected','all-physical']:
  r=d/'closure/reversed/saved'
  # Current selected bytes even though the retained section/member map is given free.
  if kind=='selected':members=rows
  else:
   # All physical files saved for this load, not scripts emitted only to drive this experiment.
   members=[(0,f.stat().st_size,str(f)) for f in sorted(g.rglob('*')) if f.is_file() and not f.is_symlink() and f!=g/'run-with']
  segments=members+[(0,blob.stat().st_size,str(blob))]
  manifest=dest/(kind+'-'+name+'.txt');manifest.write_text(''.join(f'{a} {b} {c}\n' for a,b,c in segments))
  for t in (1,2,4,8):
   output=dest/(name+'.copy')
   a=[str(d/'proof-cost'),str(t),str(manifest),str(blob),str(output),'7']
   z=subprocess.run(a,capture_output=True,check=True); assert sha(output)==sha(blob)
   for line in z.stdout.decode().splitlines():
    width,rep,n,total,size,h,p,key=line.split(); assert int(width)==t
    per.append(dict(kind=kind,t=t,rep=int(rep),n=int(n),total=int(total),prior_bytes=int(size),hash_ms=int(h)/1e6,copy_ms=int(p)/1e6,combined_ms=(int(h)+int(p))/1e6,key=key))
   print(name,kind,t,round(statistics.median(x['hash_ms'] for x in per if x['kind']==kind and x['t']==t),2),round(statistics.median(x['copy_ms'] for x in per if x['kind']==kind and x['t']==t),2),flush=True)
 (dest/(name+'.json')).write_text(json.dumps(per,indent=2)+'\n')

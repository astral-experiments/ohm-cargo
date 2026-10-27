from pathlib import Path
import sys,shutil,subprocess as sp,json,hashlib
r=Path('/mnt/devbox-scratch/dev-user/ohm-mixed-interface-20261027');code=(Path(__file__).resolve().with_name('release-ruff.py')).read_text().split("if sys.argv[1]=='init':")[0];scope={};exec(code,scope);h=scope['home'];d=scope['d'];src=h/'pair';next=h/'forced';assert not next.exists();scope['space']();sp.run(['cp','-a','--reflink=auto',src,next],check=True)
arms=['pair','forced']
sha=scope['sha'];before=json.loads((h/'evidence/pair/edit2/result.json').read_bytes());files=[]
for l in (h/'evidence/pair/edit2/stdout').read_bytes().splitlines():
 a=json.loads(l)
 if a.get('reason')!='compiler-artifact':continue
 for raw in a['filenames']:
  p=Path(raw)
  for t in ['target','shared']:
   if not p.is_relative_to(d/t):continue
   rel=Path(t)/p.relative_to(d/t);f1=src/rel;f2=next/rel;assert (f1.stat().st_ino,f1.stat().st_dev)!=(f2.stat().st_ino,f2.stat().st_dev) and sha(f1)==sha(f2) and f1.stat().st_mtime_ns==f2.stat().st_mtime_ns
   files.append([str(rel),sha(f1)]);break
assert len(set(f for f,_ in files))==671;scope['write'](h/'forced-inputs.json',files)
def evict(rec):
 for l in (rec/'stdout').read_bytes().splitlines():
  a=json.loads(l)
  if a.get('reason')!='compiler-artifact' or a['target']['name'] not in ['ruff_wasm','ty_wasm']:continue
  p,=[Path(s) for s in a['filenames'] if s.endswith('.rmeta')];f=next/'target'/p.relative_to(d/'target').with_suffix('.rlink-cache.json');assert f.is_file();f.unlink()
last=h/'evidence/pair/edit2';out=[]
for mode,label,comp in [('original','forced-restore','restore'),('edited','forced-edit','edit2')]:
 evict(last);v=scope['one']('forced',mode,label);fresh=scope['one']('forced',mode,label+'-fresh');assert not fresh['procs']
 gold=json.loads((h/'evidence/pair'/comp/'result.json').read_bytes());eq={}
 for k in ['ruff_wasm','ty_wasm','ruff_python_parser']:
  x=gold['artifacts'][k][0][1];y=v['artifacts'][k][0][1]
  eq[k]={kk:x[kk]==y[kk] for kk in x if kk!='.rlib'};print(mode,k,eq[k],flush=True)
 out.append({'source':mode,'full':v['procs'],'guarded':gold['procs'],'same_outputs':eq});scope['write'](h/'forced-comparison.json',out)
 assert sorted((n,t) for _,n,t in v['procs'])==sorted([(x,'full') for x in ('ty_wasm','ruff_wasm','ruff_python_parser')])
 assert sorted((n,t) for _,n,t in gold['procs'])==sorted([('ruff_python_parser','full'),('ty_wasm','HIR-and-native-link'),('ruff_wasm','HIR-and-native-link')])
 assert all(all(row.values()) for row in eq.values()) and all(len(v['native'][x])==len(gold['native'][x])==2 for x in ('cc','collect2','ld.bfd'))
 last=h/'evidence/forced'/label

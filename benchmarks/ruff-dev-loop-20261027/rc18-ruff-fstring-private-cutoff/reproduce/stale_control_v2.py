from snapshot import *
import tempfile, time

def targeted(phase,name):
 arr=json.loads((Y/'receipts'/phase/'artifacts.json').read_text());row=[v for v in arr if v['local'] and v['target']==name and 'lib' in v['kind']];assert len(row)==1,(phase,name);return row[0]
def fixture(phase):
 out=Y/'stale-control-v2'/phase;out.mkdir();local=out/'local';local.mkdir();reg=set();dirs={}; names={};arts=json.loads((Y/'receipts'/phase/'artifacts.json').read_text());d=Y/'receipts'/phase
 for target in arts:
  for s,e in target['files'].items():
   p=Path(s)
   if p.suffix not in ('.rlib','.rmeta','.so'):continue
   if not target['local']:
    if not p.is_file() or sha(p)!=e['sha256']:
     alt=Y/'states/independent-clean'/p.relative_to(P);assert alt.is_file() and sha(alt)==e['sha256'],(phase,p);p=alt
    reg.add(str(p.parent));continue
   # Match the local release-derived metadata by the exact filename and full retained bytes.
   f=local/p.name;blob=Y/'objects'/e['sha256'];assert sha(blob)==e['sha256'];
   if f.exists():assert os.path.samefile(f,blob)
   else:os.link(blob,f)
   if p.suffix=='.rlib':
    meta=[Path(z) for z in target['files'] if z.endswith('.rmeta')]
    if meta:
     assert len(meta)==1;hashed=local/meta[0].with_suffix('.rlib').name
     if hashed.exists():assert os.path.samefile(hashed,blob)
     else:os.link(blob,hashed)
     f=hashed
    if target['target'] in ('ruff_python_ast','ruff_python_parser'):names[target['target']]=f
 native=sorted({j for x in map(json.loads,(d/'stdout.jsonl').read_text().splitlines()) if x['reason']=='build-script-executed' for j in x['linked_paths']});return local,sorted(reg),native,names

def call(label,phase,other,fixtures):
 local,reg,native,names=fixtures[phase];selected=dict(names);
 if other:
  borrowed=fixtures[other][3]['ruff_python_parser'];slot=Y/'stale-control-v2'/label;slot.mkdir();parser=slot/borrowed.name;os.link(borrowed,parser);selected['ruff_python_parser']=parser
 target=Y/'stale-control-v2'/('caller-'+label);cmd=[PROXY/'rustc','+ohm','--edition=2024','--crate-name','external_truthiness',Y/'caller.rs','-o',target];
 for n,f in sorted(selected.items()):cmd+=['--extern',n+'='+str(f)]
 for dep in [str(local),*reg]:cmd+=['-L','dependency='+dep]
 for p in native:cmd+=['-L',p]
 # Pin the normal Rust-facing mode. No Ohm-only rustc flag is added to this external consumer.
 q=sp.run(cmd,cwd=W,env=env(),capture_output=True);err=q.stderr.decode(errors='replace');(Y/'stale-control-v2'/(label+'.stderr')).write_text(err);result={'release_cargo':RELEASE_CARGO,'row':phase,'parser_from':other or phase,'selected':{n:sha(p) for n,p in selected.items()},'compile_status':q.returncode,'error_codes':sorted(set(re.findall(r'error\[(E[0-9]+)\]',err))),'stderr_sha256':dig(q.stderr),'output':None}
 if q.returncode==0:
  pr=sp.run([target],cwd=W,env=env(),capture_output=True,check=True);result['output']=pr.stdout.decode().splitlines();result['elf_sha256']=sha(target)
 return result

if __name__=='__main__':
 while not (Y/'terminal.json').exists():time.sleep(5)
 (Y/'stale-control-v2').mkdir(); phases=['settle-current','warm-reverse'];fixtures={p:fixture(p) for p in phases}; results={}
 for i,p in enumerate(phases):
  results[p]=call(p+'-matched',p,None,fixtures); baseline=json.loads((Y/'receipts'/p/'programs.json').read_text());assert results[p]['compile_status']==0 and results[p]['output']==baseline['external_output'],results[p]
  results[p+'-stale-parser']=call(p+'-stale-parser',p,phases[1-i],fixtures)
 write(Y/'stale-control-v2/results.json',results);assert not (Y/'stale-control/results.json').exists();write(Y/'stale-control/results.json',results)

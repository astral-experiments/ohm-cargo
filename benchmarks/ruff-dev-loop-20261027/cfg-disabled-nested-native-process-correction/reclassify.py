"""Use successful exec argv to repair the historical single-token native-fixture counter."""
from pathlib import Path
import ast,hashlib,json,re
q=Path('/dev/shm/ohm-stdlib-native-scout-20261027')
out={}
for p in q.glob('tiny-*-nested-*'):
 if not (p/'result.json').is_file():continue
 result=json.loads((p/'result.json').read_bytes());states={}
 for case,x in result['samples'].items():
  if not (p/case).is_dir():continue
  jobs=[];wild=[]
  for f in sorted((p/case).glob('exec.*')):
   for l in f.read_text(errors='replace').splitlines():
    m=re.match(r'execve\("([^"]*)", (\[.*\]), [^\n]*\) += 0$',l)
    if not m:continue
    exe,args=Path(m[1]),ast.literal_eval(m[2])
    if exe.name=='rustc' and '--crate-name' in args and args[args.index('--crate-name')+1]=='api':
     split=any(args[i:i+2]==['-Z','link-only'] for i in range(len(args)));combined='-Zlink-only' in args
     inputs=[Path(t).name for t in args if t.endswith('.rlink') or t.endswith('tests/api.rs')]
     assert len(inputs)==1 and (inputs[0].endswith('.rlink')==(split or combined))
     jobs.append({'pid':f.name,'mode':'link-only' if split or combined else 'full','separate_Z_link_only':split,'source_or_recipe':inputs[0]})
    if str(exe).endswith('/wild-ld/ld.bfd') and '-o' in args and Path(args[args.index('-o')+1]).name.startswith('api-'):
      wild.append({'pid':f.name,'output':Path(args[args.index('-o')+1]).name})
  assert len(jobs)==len(x['full']) and len(jobs)==len(wild),(p,case,jobs,wild)
  states[case]={'actual_api_jobs':jobs,'wild':wild,'exit':x['rc'],'prior_mode_label':x['full'],'marker':x.get('marker')}
 if len(states)==6:out[p.name]={'cargo':result['cargo'],'raw_summary_sha256':hashlib.sha256((p/'result.json').read_bytes()).hexdigest(),'phases':states}
assert any(n.startswith('tiny-baseline-') for n in out) and any(n.startswith('tiny-a9c-') for n in out) and any(n.startswith('tiny-a10c-') for n in out)
(q/'nested-actual-rustc-modes.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
for n,v in out.items(): print(n,{c: [j['mode'] for j in x['actual_api_jobs']] for c,x in v['phases'].items()})

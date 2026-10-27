"""Run one unscored real workspace invocation. Its physical trace excludes external validation commands."""
import sys, subprocess, json, os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from collections import Counter
from common import RUFF, FROZEN, SONAME, TARGET, CARGO_HOME, env, need, load, dump, sha
from novel_state import verify_plan, verify_view, PLAN, OUT, H
from state import WASM, recipes
from witness import audit_json, directory_inventory, trusted_ancestors
from processes import parse, qualify
from products import products
mode,arm,label,phase,name=sys.argv[1:]
need(mode in ('build','test') and arm in 'BC' and phase in ('cold','train','baseline','fresh','edit','restore'),'worker options')
st=OUT/'state'/mode/arm;d=OUT/'receipts'/mode/arm/name;d.mkdir()
verify_plan();verify_view(label,OUT/'fixture'); b=PLAN['subjects'][arm];host=load(H/'host-preflight.json');cfg=env()
need(sha(FROZEN/'bin/cargo')==b['cargo_sha256'] and sha(FROZEN/'lib'/SONAME)==b['driver_sha256'],'actual bound binaries')
need(sha(FROZEN/'bin/rustc')==PLAN['source_heads']['rustc_frontend'] and all(x['trusted'] for x in trusted_ancestors(CARGO_HOME)) and cfg['CARGO_BUILD_JOBS']=='8','frontend/registry/jobs')
registered=PLAN['primary_command' if mode=='build' else 'secondary_command'];cmd=[*registered,'--message-format=json']
known=st/'recorded-recipes.json'; paths=load(known) if known.is_file() else None
prior=recipes(paths)
with (d/'stdout').open('wb') as so,(d/'stderr').open('wb') as se:
    q=subprocess.run(['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat,prctl','-o',str(d/'exec'),*cmd],cwd=RUFF,env=cfg,stdin=subprocess.DEVNULL,stdout=so,stderr=se)
rec={'arm':arm,'mode':mode,'source_view':label,'phase':phase,'actual_cargo':b['cargo_sha256'],'actual_driver':b['driver_sha256'],'command':cmd,'status':q.returncode}
dump(d/'invocation.json',rec);need(q.returncode==0 and 'Blocking waiting' not in (d/'stderr').read_text(errors='replace'),('command failed',d,(d/'stderr').read_text(errors='replace')[-1000:]))
after=recipes(paths);t=parse(d,mode,prior,after);j=audit_json(d/'stdout',mode)
if not known.exists() and (arm=='B' or len(after)>=2):dump(known,sorted(after))
need(not set(j['executables']).intersection(p for _,p in t['images']),'test binary ran')
need(not any(any('crate-hash' in s or 'crate_hash' in s for s in args) for _,_,args in t['queries']),'extra standalone hash process')
jobs=t['jobs'];dirty=j['dirty'];rec.update(processes=t,recipe_before=prior,recipe_after=after,unit_count=j['units'],fresh_units=j['units']-len(dirty),elf_count=len(j['elf']),executable_count=len(j['executables']),process_totals=dict(Counter(x['kind'] for x in jobs)),native_totals={k:len(v) for k,v in t['native'].items()})
dump(d/'classified.json',{'dirty':dirty,**{k:rec[k] for k in ('unit_count','fresh_units','elf_count','executable_count','process_totals','native_totals')}})
if phase in ('baseline','fresh'): qualify(t,mode,arm,'fresh');need(not dirty,('freshness failed',arm,mode,label,dirty))
if phase=='cold':need(set(WASM)<=set(dirty) and any(x['kind']=='full' and x['crate']=='ruff_python_parser' for x in jobs),('nonempty seed',dirty))
if phase in ('edit','restore'):need(any(x['kind']=='full' and x['crate']=='ruff_python_parser' for x in jobs),('real parser source change missed',label,dirty))
rows=[json.loads(l) for l in (d/'stdout').read_bytes().splitlines() if l]
rich=phase in ('cold','baseline','edit','restore')
rec['product']=products(j,rows,False,rich,OUT/'retained-mixed')
normal=[r for r in rows if r.get('reason')=='compiler-artifact' and not r['profile']['test']]
ruff,={r['executable'] for r in normal if r['target']['name']=='ruff' and r['target']['kind']==['bin'] and r.get('executable')}
spec=PLAN['cli']; outcomes=[]
for i,source in enumerate([*spec['signed_sources'],spec['valid_indented_strings']]):
    q=subprocess.run([ruff,*spec['flags']],cwd=RUFF,env=cfg,capture_output=True,input=source.encode())
    actual=json.loads(q.stdout);outcomes.append({'input':source,'status':q.returncode,'stderr':q.stderr.decode(),'diagnostics':actual})
    dump(d/'cli.json',outcomes);need(not q.stderr,('unexpected CLI stderr',q.stderr))
    if label=='signed-pattern-diagnostic' or i==2:need(q.returncode==0 and actual==[],('signed pattern/strings runtime',label,outcomes[-1]))
    else:
        e=spec['original_signed'];need(q.returncode==e['exit'] and len(actual)==1,('missing signed-pattern error',label,outcomes[-1]));msg=actual[0]
        need((msg['code'],msg['message'],msg['location'],msg['end_location'])==(e['code'],e['message'],{'row':e['row'],'column':e['start_column']},{'row':e['row'],'column':e['end_columns'][i]}),('wrong signed error',msg))
rec['novel_cli']=outcomes
if phase=='fresh':
    from products import inputs_elf_key
    rec['raw_fresh_elf']={inputs_elf_key(p):sha(Path(p)) for p in j['elf']}
if phase=='cold':
    rec['manifest_proof']=directory_inventory(CARGO_HOME/'.ohm-registry-json-v1');need(rec['manifest_proof']['files']>0,'valid isolated registry cache')
dump(d/'receipt.json',rec)

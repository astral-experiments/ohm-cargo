"""Run one real, default-Ohm full workspace command and separately attest its outputs."""
from pathlib import Path
import argparse, os, subprocess, sys, time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import FROZEN, SONAME, RUFF, CARGO_HOME, dump, env, load, need, sha
from state import PLAN, WASM, recipes, verify_plan, verify_view
from products import products
from processes import parse, qualify
from witness import audit_json, trusted_ancestors, directory_inventory
cli=argparse.ArgumentParser(description=__doc__)
for key in ('out','manifest','binding'):cli.add_argument('--'+key,type=Path,required=True)
cli.add_argument('--arm',choices='ABC',required=True);cli.add_argument('--mode',choices=['build','test'],required=True)
cli.add_argument('--state',choices=['original','edited'],required=True)
cli.add_argument('--phase',choices=['cold','train','conditioning','fresh','detailed-fresh','edit','ordinary','settle','forced'],required=True)
cli.add_argument('--force-from',type=Path)
cli.add_argument('--known-recipes',type=Path)
a=cli.parse_args();out=a.out;out.mkdir();cfg=env();verify_plan();verify_view(a.state=='edited',load(a.manifest))
bind=load(a.binding); arm=bind['arms'][a.arm]
need(sha(FROZEN/'bin/cargo')==arm['cargo_sha256'] and sha(FROZEN/'lib'/SONAME)==arm['driver_sha256'],'wrong actual compiler or Cargo')
need(sha(FROZEN/'bin/rustc')==bind['host']['host_tools']['rustc_frontend']['sha256'],'wrong frontend')
need(cfg['CARGO_BUILD_JOBS']=='8' and all(x['trusted'] for x in trusted_ancestors(CARGO_HOME)), 'trusted isolated Cargo home')
known=load(a.known_recipes) if a.known_recipes else None
before=recipes(known)
if a.phase=='forced' and a.arm=='C':
    need(a.force_from is not None,'missing same-state reference');prior=load(a.force_from)['product']['mixed']
    for cr in WASM:
        f=Path(prior[cr]['metadata']).with_suffix('.rlink-cache.json');need(f.is_file() and not f.is_symlink(),('missing private forced manifest',cr,f))
        backup=out/('evicted-'+cr+'.rlink-cache.json');need(not backup.exists(),'unexpected archive');backup.write_bytes(f.read_bytes());f.unlink()
    dump(out/'pre-eviction-recipes.json',before)
normal=a.phase in ['ordinary','settle']
command=['cargo','+ohm',a.mode]+(['--no-run'] if a.mode=='test' else [])+['--locked','--offline']
exec_command=command if normal else ['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat,prctl','-o',str(out/'exec'),*command,'--message-format=json']
with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as err:
    start=time.monotonic_ns();p=subprocess.run(exec_command,stdin=subprocess.DEVNULL,stdout=so,stderr=err,cwd=RUFF,env=cfg);ns=time.monotonic_ns()-start
rec={'phase':a.phase,'state':a.state,'mode':a.mode,'arm':a.arm,'actual_cargo':arm['cargo_sha256'],'actual_driver':arm['driver_sha256'],'command':command,'elapsed_ns':ns,'status':p.returncode}
dump(out/'invocation.json',rec)
err=(out/'stderr').read_text(errors='replace');need(p.returncode==0 and 'Blocking waiting' not in err,('command failed',out,err[-1400:]))
after=recipes(known);rec.update(recipe_before=before,recipe_after=after)
if normal:
    need((out/'stdout').stat().st_size==0 and 'Finished' in err,('ordinary Cargo terminal',out))
    status=[line.strip() for line in err.splitlines() if line.lstrip().startswith(('Compiling ','Checking ','Linking '))]
    need(any('ruff_python_parser' in l for l in status),('historical producer did not compile',status))
    # A physical snapshot of the cached recipe accompanies EVERY ordinary edit.
    # Independent full traces, the actual changed native diagnostic, and immediate all-fresh checks
    # separately prevent an unchanged recipe on a no-op from being counted as a guarded job.
    for cr in WASM:
        old={p:s for p,s in before.items() if Path(p).stem.split('-')[0]==cr}; new={p:s for p,s in after.items() if Path(p).stem.split('-')[0]==cr}
        if a.arm=='C':need(len(old)==1 and old==new,('guarded recipe rewrote at ordinary edit',cr,old,new))
    rec['terminal_work']=status
else:
    rows=[__import__('json').loads(line) for line in (out/'stdout').read_bytes().splitlines() if line]
    j=audit_json(out/'stdout',a.mode)
    t=parse(out,a.mode,before,after);qualify(t,a.mode,a.arm, 'fresh' if a.phase=='detailed-fresh' else a.phase)
    need(not set(j['executables']).intersection(p for _,p in t['images']),'Cargo ran a test program')
    if a.phase in ('fresh','detailed-fresh'):need(not j['dirty'],('unexpected stale unit',j['dirty']))
    if a.phase in ('conditioning','edit','forced'):
        need(j['dirty'] and not [n for n in j['dirty'] if n=='ron'],'the edit caused unexpected observer retraining')
    if a.phase=='cold':need(set(WASM)<=set(j['dirty']) and any(x['kind'] in ('full','checked-full-fallback') and x['crate']=='ruff_python_parser' for x in t['jobs']),('cold inputs were reused',j['dirty']))
    rich=a.phase in ('cold','conditioning','edit','detailed-fresh','forced')
    rec.update(fresh_units=j['units']-len(j['dirty']),unit_count=j['units'],processes=t)
    rec['product']=products(j,rows,a.state=='edited',rich,out.parents[3]/'retained-mixed')
    if rich:
        rec['manifest_proof']=directory_inventory(CARGO_HOME/'.ohm-registry-json-v1')
        need(rec['manifest_proof']['files']>0,'manifest proof did not become eligible')
dump(out/'receipt.json',rec)


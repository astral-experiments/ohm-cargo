"""Compile a hash-off ordinary Rust bridge or its fresh external caller against the selected arm."""
import argparse, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import FROZEN, SONAME, RUFF, dump, env, load, need, sha
from state import WASM
from products import retain
p=argparse.ArgumentParser()
for k in ('root','out','details','binding','flags'):p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--arm',choices=['A','B','C'],required=True);p.add_argument('--crate',choices=WASM,required=True)
p.add_argument('--action',choices=['bridge','caller'],required=True)
a=p.parse_args();a.out.mkdir();working=a.root/'bridge-canonical';ref=load(a.details)['product']['mixed'][a.crate]
cfg=env();current=load(a.binding)['arms'][a.arm];need(sha(FROZEN/'lib'/SONAME)==current['driver_sha256'],'external compiler mismatch')
src=a.root/'bridge-src';rlib=Path(ref['metadata']).with_suffix('.rlib')
need(sha(rlib)==ref['archive']['sha256'],'bridge did not load the currently observed mixed .rlib')
search=load(a.flags)['processes']['extern_dirs'][a.crate]
common=['rustc','+ohm','--sysroot',str(FROZEN),'--edition=2024','-C','link-arg=-B'+str(FROZEN/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld'),'-L','dependency='+str(rlib.parent),*search]
if a.action=='bridge':
    artifact=working/'libordinary_bridge.rlib'
    cmd=[*common,'--crate-name','ordinary_bridge','--crate-type','rlib',str(src/(a.crate+'.rs')),'--extern',a.crate+'='+str(rlib),'-o',str(artifact)]
else:
    artifact=working/'ordinary_user'
    cmd=[*common,'--crate-name','ordinary_user',str(src/'caller.rs'),'--extern','ordinary_bridge='+str(a.root/'libordinary_bridge_input.rlib'),'-o',str(artifact)]
proc=subprocess.run(cmd,cwd=RUFF,env=cfg,capture_output=True);(a.out/'stderr').write_bytes(proc.stderr);(a.out/'stdout').write_bytes(proc.stdout);dump(a.out/'argv.json',cmd)
need(proc.returncode==0 and artifact.is_file(),('ordinary external transitive Rust compilation',a.crate,a.action,proc.stderr[-1500:]))
value=None
if a.action=='caller':
    value=subprocess.check_output([artifact],env=cfg,text=True).strip();need(value in ['93526150d','0.17.0'],('version runtime',value))
digest=retain(artifact,a.root/'retained-mixed')
dump(a.out/'bridge.json',{'arm':a.arm,'action':a.action,'crate':a.crate,'result_sha256':digest,'current_rlib_sha256':sha(rlib),'runtime':value,'public_hash_opt_in':False})
if a.action=='caller':
    need(artifact==working/'ordinary_user','private fixture caller');artifact.unlink()


"""Reproduce the foreign source-file regression with a released Ohm toolchain and no wrapper.

Usage: python3 reproduce.py /empty/or/new/output
Set RUSTUP_HOME so cargo +ohm and rustc +ohm resolve to Ohm 1.99.0-14.
Requires only the Python standard library and the native Rust toolchain.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

out = Path(sys.argv[1]).absolute()
out.mkdir(exist_ok=False)
ws = out / 'ws'
ws.mkdir()
shutil.copytree(Path(__file__).parent / 'original', ws, dirs_exist_ok=True)
env = dict(os.environ, CARGO_HOME=str(out / 'cargo-home'), CARGO_INCREMENTAL='1',
           CARGO_BUILD_JOBS='4', GIT_OPTIONAL_LOCKS='0')
for var in ('RUSTC','RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS'):
    env.pop(var,None)
versions = {}
for cmd in (['cargo','+ohm','-Vv'], ['rustc','+ohm','-vV']):
    v=subprocess.check_output(cmd,cwd=ws,env=env,text=True).strip()
    assert 'ohm-1.99.0-14' in v, v
    versions[cmd[0]]=v
(out/'versions.json').write_text(json.dumps(versions,indent=2)+'\n')

def build(stage, store):
    dest=out/stage
    dest.mkdir()
    e=dict(env, CARGO_TARGET_DIR=str(out/(store+'-target')), CARGO_BUILD_BUILD_DIR=str(out/(store+'-shared')))
    p=subprocess.run(['cargo','+ohm','build','--locked','--offline','--message-format=json','-p','app'],cwd=ws,env=e,capture_output=True)
    (dest/'cargo.stderr').write_bytes(p.stderr)
    (dest/'cargo.jsonl').write_bytes(p.stdout)
    msgs=[json.loads(row) for row in p.stdout.splitlines()]
    arts={m['target']['name']:m['fresh'] for m in msgs if m['reason']=='compiler-artifact'}
    panic=[m['message']['message'] for m in msgs if m['reason']=='compiler-message' and 'unstable fingerprints' in m['message']['message']]
    panic+= [l.strip() for l in p.stderr.decode().splitlines() if 'unstable fingerprints' in l]
    output=None
    if p.returncode==0:
        exe=next(m['executable']for m in msgs if m['reason']=='compiler-artifact' and m['target']['name']=='app')
        output=subprocess.check_output([exe],cwd=ws,env=e,text=True).splitlines()
    return dict(exit=p.returncode,fresh=arts,panic=panic,output=output)

rows={'prime':build('prime','incremental')}
f=ws/'leaf/src/lib.rs';f.write_text(f.read_text().replace('#[cfg(any())]', '#[cfg(all())]'))
rows['leaf_edit']=build('leaf_edit','incremental')
f=ws/'app/src/main.rs';s=f.read_text().replace('struct External;', 'struct External; #[derive(Debug)] struct Distinct;')
f.write_text(s.replace('bundle::nested(External','bundle::nested(Distinct').replace('x:7','x:11'))
rows['caller_edit']=build('caller_edit','incremental')
rows['empty_target_same_sources']=build('empty_target_same_sources','reference')
(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
assert rows['prime']['exit']==rows['leaf_edit']['exit']==rows['empty_target_same_sources']['exit']==0
assert rows['caller_edit']['exit']!=0 and rows['caller_edit']['panic'], rows['caller_edit']

"""Recheck both benchmark arms after a baseline StableCrateId diagnostic, retaining every receipt."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027'); name='revision-native-66815c41574c'
S=P/'parser-assets/stage2/revision-series'; R=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027')
F=P/'frozen-toolchain'; base=P/'reference-parser-v3'; state=P/(name+'-private-state')
parent='051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518'; candidate='3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2'
out=P/(name+'-check-diagnosis');out.mkdir(exist_ok=True); index=R/'Cargo.lock'
def sh(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
subjects={'candidate':(P/'subjects'/('driver-'+candidate),candidate,state/'target-candidate',state/'shared-candidate'), 'parent':(F/'.bench-components'/('driver-'+parent),parent,base/'parent-cold-target',base/'parent-cold-shared')}
with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX); assert sh(F/'bin/rustc')=='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
    assert not subprocess.check_output(['git','--no-optional-locks','-C',R,'status','--porcelain'])
    for arm,(driver,digest,target,shared) in subjects.items():
        assert sh(driver)==digest
        place=out/(arm+'-native-then-check');place.mkdir()
        env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(P/'registry-home'),CARGO_TARGET_DIR=str(P/'native-target'),CARGO_BUILD_BUILD_DIR=str(P/'shared'),CARGO_BUILD_JOBS='8',CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_TERM_COLOR='never')
        w=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp','--bind',str(place),str(place),'--bind',str(P/'registry-home'),str(P/'registry-home'),'--bind',str(P/'rustup'),str(P/'rustup'),'--bind',str(target),str(P/'native-target'),'--bind',str(shared),str(P/'shared'),'--ro-bind',str(P/'subjects/parent'),str(F/'bin/cargo'),'--ro-bind',str(driver),str(F/'lib/librustc_driver-774a793a844d5500.so'),'--chdir',str(R),'--','taskset','-c','0-23','strace','-ff','-qq','-s','2000','-e','trace=execve','-o',str(place/'exec'),'cargo','+ohm','check','--locked','--offline','--message-format=json']
        with (place/'stdout').open('wb') as o,(place/'stderr').open('wb') as e: rc=subprocess.run(w,env=env,stdout=o,stderr=e).returncode
        rows=[json.loads(l) for l in (place/'stdout').read_bytes().splitlines() if l.startswith(b'{')];arts=[r for r in rows if r['reason']=='compiler-artifact']; errors=[(r['target']['name'],r['message']['message']) for r in rows if r['reason']=='compiler-message' and r['message']['level']=='error']; assert rows[-1]['reason']=='build-finished'
        rec={'arm':arm,'driver':digest,'rc':rc,'units':len(arts),'fresh':sum(r['fresh'] for r in arts),'errors':errors,'pep440':[{'fresh':r['fresh'],'files':r['filenames'],'features':r['features']} for r in arts if r['target']['name']=='pep440_rs']};(place/'result.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec),flush=True)

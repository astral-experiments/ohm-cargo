"""Exercise the public historical-edit reproducer with the fixed Rust and Cargo releases."""
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from common import CARGO_HOME,FROZEN,P,PIN,RUFF,SHARED,SONAME,TARGET,git,sha,trace

here=Path(__file__).resolve().parent
root=here.parent
suite=root/'cargo-observer-ruff-fifo-fixed'
cargo_dir=root/'cargo-observer-fifo-qualification'
result=root/'corrected-toolchain-portable-rerun-v2'
hashes=json.loads((cargo_dir/'subjects.json').read_bytes())
driver=root/'drivers'/('driver-'+hashes['compiler_driver'])
cargo=cargo_dir/'guardv3'
assert sha(driver)==hashes['compiler_driver'] and sha(cargo)==hashes['candidate_cargo']
marker=root/'prefetch-fifo-qualified-v2/queue.rc'
while not marker.exists():
    for path in (root/'qualification-posobs4fmt-c3/failure.txt',root/'whole-ruff-observer-prefetch-fifo-v2/failure.txt'):
        if path.exists():raise SystemExit(f'Previous cohort failed: {path.parent.name}')
    time.sleep(30)
assert marker.read_text().strip()=='0'
assert json.loads((suite/'complete.json').read_bytes())['source_clean']
assert json.loads((root/'whole-ruff-observer-prefetch-fifo-v2/complete.json').read_bytes())['source_clean']
def save(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')

with (P/'native-measure.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    assert git('rev-parse','HEAD')==PIN and not git('status','--porcelain')
    index=Path(git('rev-parse','--path-format=absolute','--git-path','index'));initial=sha(index)
    result.mkdir()
    try:
        subprocess.run(['sha256sum','-c','SHA256SUMS'],cwd=here,check=True)
        out={}
        expected={('doc','build'):(2,2,3),('doc','test'):(4,16,19),('parser','build'):(3,6,8),('parser','test'):(6,62,67)}
        for (edit,mode),counts in expected.items():
            label=edit+'-'+mode
            state=suite/'state'/mode/'candidate'
            private=result/label;private.mkdir()
            raw=private/'raw-exec'
            cmd=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp']
            for src,dest in [(result,result),(RUFF,RUFF),(state/'target',TARGET),(state/'shared',SHARED),(state/'registry-home',CARGO_HOME),(P/'rustup',P/'rustup')]:
                cmd+=['--bind',str(src),str(dest)]
            for src,dest in [(cargo,FROZEN/'bin/cargo'),(driver,FROZEN/'lib'/SONAME)]:
                cmd+=['--ro-bind',str(src),str(dest)]
            env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(CARGO_HOME),GIT_OPTIONAL_LOCKS='0',CARGO_TERM_COLOR='never')
            argv=[sys.executable,'-B',here/'rerun-native-edit.py',RUFF,edit,mode,'--target',TARGET,'--shared-build',SHARED,'--expect-driver',hashes['compiler_driver'],'--expect-cargo',hashes['candidate_cargo'],'--trace-edit',raw]
            with (private/'stdout').open('wb') as so,(private/'stderr').open('wb') as se:
                r=subprocess.run([*cmd,'--','taskset','-c','0-23',*argv],cwd=RUFF,env=env,stdout=so,stderr=se)
            assert r.returncode==0,(label,(private/'stderr').read_text()[-900:])
            record=json.loads((private/'stdout').read_bytes())
            calls=trace(raw);kinds=Counter(k for _,k in calls['rustc'])
            assert record['source_restored'] and record['edit_seconds'] is None
            assert record['fresh_units']==(501 if mode=='build' else 619)
            assert (kinds['full'],kinds['link-only'],len(calls['linkers']))==counts,(label,calls['rustc'],calls['linkers'])
            assert sha(index)==initial and not git('status','--porcelain')
            out[label]={'cargo':record['toolchain']['cargo'],'driver':record['toolchain']['rustc_driver'],'fresh_units':record['fresh_units'],'source_restored':True,'rustcs':calls['rustc'],'linkers':[Path(l).name for l in calls['linkers']],'command':record['command']}
            save(result/'progress.json',out);print(label,dict(kinds),len(calls['linkers']),flush=True)
        save(result/'complete.json',{'reproducer_sha256':sha(here/'rerun-native-edit.py'),'source_clean':True,'pin':PIN,'index':initial,'outcomes':out})
    except BaseException:
        (result/'failure.txt').write_text(traceback.format_exc())
        raise

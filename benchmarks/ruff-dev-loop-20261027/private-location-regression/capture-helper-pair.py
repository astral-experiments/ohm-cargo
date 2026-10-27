"""Keep matched rustc headers and native archives from complete, independent Ruff workspace builds."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
B=Path.home()/'.cache/ohm-helper-offset-pairs-20261027'
R=Path('/home/dev-user/code/oss/ruff-ohm-whole-native-20261027')
F=P/'frozen-toolchain'
src=P/'source'
rel=Path('crates/ruff_linter/src/rules/ruff/helpers.rs')
driver_shas={'parent':'051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518','candidate':'3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2'}
arm=sys.argv[1]
cpus={'parent':'8-15','candidate':'16-23'}[arm]
out=B/arm
out.mkdir(parents=True)
target,shared=out/'target',out/'shared-build'
target.mkdir(); shared.mkdir()
driver=(F/'.bench-components' if arm=='parent' else P/'subjects')/('driver-'+driver_shas[arm])
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert sha(driver)==driver_shas[arm]
assert subprocess.check_output(['git','--no-optional-locks','-C',src,'status','--porcelain'])==b''
assert subprocess.check_output(['git','-C',src,'rev-parse','HEAD'],text=True).strip()=='93526150df078af7dd8fc4226cdcc469539d2001'
orig=(src/rel).read_bytes()
needle=b'/// return `true` if `func` represents a call to `dataclasses.field()`.'
assert orig.count(needle)==1
edited=out/'edited.rs'
edited.write_bytes(orig.replace(needle,needle.replace(b'dataclasses.field()', b'dataclass.field()')))
env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(P/'registry-home'),CARGO_BUILD_JOBS='6',CARGO_TARGET_DIR=str(P/'native-target'),CARGO_BUILD_BUILD_DIR=str(P/'shared'),CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST='all',CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST='all',CARGO_TERM_COLOR='never',LC_ALL='C.UTF-8',SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs')
assert not any(k.startswith('WILD_') or k in ('RUSTC_LOG','RUSTFLAGS','RUSTC_WRAPPER') for k in env)
for step in ('original','edited'):
    dest=out/step; dest.mkdir()
    if step=='edited':
        os.utime(edited,None)
    wrap=['bwrap','--ro-bind','/','/','--proc','/proc','--dev-bind','/dev','/dev','--bind','/tmp','/tmp','--bind',str(P/'registry-home'),str(P/'registry-home'),'--bind',str(P/'rustup'),str(P/'rustup'),
          '--bind',str(target),str(P/'native-target'),'--bind',str(shared),str(P/'shared'),'--ro-bind',str(src),str(R),
          '--ro-bind',str(P/'subjects/parent'),str(F/'bin/cargo'),'--ro-bind',str(driver),str(F/'lib/librustc_driver-774a793a844d5500.so')]
    if step=='edited':wrap+=['--ro-bind',str(edited),str(R/rel)]
    wrap+=['--chdir',str(R),'--','taskset','-c',cpus]
    with (dest/'cargo.jsonl').open('wb') as stdout,(dest/'cargo.stderr').open('wb') as stderr:
        p=subprocess.run([*wrap,'cargo','+ohm','build','--locked','--offline','--message-format=json'],env=env,stdout=stdout,stderr=stderr)
    assert p.returncode==0,(dest,(dest/'cargo.stderr').read_text()[-800:])
    rows=[json.loads(l) for l in (dest/'cargo.jsonl').read_bytes().splitlines() if l.startswith(b'{')]
    arts=[r for r in rows if r['reason']=='compiler-artifact']
    assert rows[-1]['success'] and len(arts)==501
    (unit,)=[r for r in arts if r['target']['name']=='ruff_linter' and not r['profile']['test']]
    assert not unit['fresh']
    files={}; report={}
    for name in unit['filenames']:
        path=Path(name)
        if path.suffix in ('.rlib','.rmeta'):
            real=target/path.relative_to(P/'native-target')
            dst=dest/('ruff_linter'+path.suffix)
            shutil.copyfile(real,dst); digest=sha(dst); assert digest==sha(real)
            files[path.suffix]=dict(sha256=digest,size=dst.stat().st_size,canonical=name)
            if path.suffix=='.rmeta':
                root=subprocess.check_output([*wrap,'rustc','+ohm','-Zls=root',name],env=env)
                (dest/'header.txt').write_bytes(root); report['header']=root.decode().splitlines()[:5]
    assert set(files)=={'.rmeta','.rlib'}
    report.update(files=files,step=step,arm=arm,source=sha(edited if step=='edited' else src/rel),units=len(arts),driver=driver_shas[arm])
    (dest/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(arm,step,report['header'],flush=True)
assert (src/rel).read_bytes()==orig

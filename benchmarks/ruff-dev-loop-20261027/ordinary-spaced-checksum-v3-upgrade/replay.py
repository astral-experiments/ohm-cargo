"""Upgrade fourteen retained ordinary checksum states with their logical names and released rustc held fixed."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import subprocess
import traceback

p=Path('/mnt/devbox-scratch/dev-user/ohm-spaced-ruff-20261027')
assets=p.parent/'ohm-observer-shipping-20261027'
sdk=assets/'assets/stock16-sdk'
candidate=assets/'subjects/raw-complete-v2'
o=p/'ordinary-binary-upgrade-v2'
expected='549d2ed1cb47a4810f334572fd3a56987a0695a24f7a7b79c1b6a3b11c357087'
sha=lambda b:hashlib.sha256(b).hexdigest()
def read(f):return json.loads(f.read_bytes())
def write(f,v):f.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def sumfile(f):
    with f.open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def job(group,case,root):
    history=read(root/'result.json')
    src,=[f for f in root.iterdir() if (f/'src/main.rs').is_file()]
    initial=history['cargo-upgrade'];clean=history['clean']
    original_diag=[x['message'] for v in (root/'clean/stdout').read_bytes().splitlines() if (x:=json.loads(v))['reason']=='compiler-message' and x['message']['level']=='error']
    t=o/group/case;t.mkdir()
    for name in ('target','shared','home','cargo'):
        subprocess.run(['cp','-a','--reflink=auto','--',root/name,t/name],check=True)
    env=dict(HOME=str(root/'home'),PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',
             CARGO_HOME=str(root/'cargo'),CARGO_TARGET_DIR=str(root/'target'),CARGO_BUILD_BUILD_DIR=str(root/'shared'),
             CARGO_BUILD_JOBS='2',CARGO_NET_OFFLINE='true',RUSTUP_HOME=str(p/'rustup'),RUSTUP_TOOLCHAIN='ohm',
             RUSTUP_AUTO_INSTALL='0',CARGO_TERM_COLOR='never',LANG='C.UTF-8',LC_ALL='C.UTF-8')
    br=['bwrap','--ro-bind','/','/','--dev','/dev','--proc','/proc','--tmpfs','/tmp',
        '--ro-bind',str(candidate),str(sdk/'bin/cargo')]
    for name in ('target','shared','home','cargo'):br+=['--bind',str(t/name),str(root/name)]
    br+=['--chdir',str(src),'--']
    frozen=sumfile(src/'src/main.rs')
    files=[(Path(x['path']),x['sha']) for x in initial['physical_files'].values() if Path(x['path']).name=='dep-bin-byte_reader']
    assert len(files)<=1
    for existing,h in files:
        x=t/existing.relative_to(root)
        assert sumfile(x)==sumfile(existing)==h and not x.samefile(existing)
    actual=subprocess.check_output([*br,'sha256sum',str(sdk/'bin/cargo')],env=env).split()[0].decode()
    assert actual==expected
    assert subprocess.check_output([*br,'sha256sum',str(sdk/'bin/rustc')],env=env).split()[0].decode()=='b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5'
    out=[]
    for phase in ('first','next'):
        dot=t/phase;dot.mkdir()
        z=subprocess.run([*br,*initial['cmd']],env=env,stdin=subprocess.DEVNULL,capture_output=True)
        (dot/'stdout').write_bytes(z.stdout);(dot/'stderr').write_bytes(z.stderr)
        assert z.returncode==clean['rc'],(group,case,phase,z.returncode,clean)
        rows=[json.loads(b) for b in z.stdout.splitlines()]
        assert rows[-1]=={'reason':'build-finished','success':z.returncode==0}
        diagnostics=[v['message'] for v in rows if v['reason']=='compiler-message' and v['message']['level']=='error']
        assert diagnostics==original_diag,(group,case,phase,'wrong diagnostics')
        runtime=None;elf=None
        arts=[v for v in rows if v['reason']=='compiler-artifact']
        if case.startswith('build-'):
            (art,)=arts;ex=Path(art['executable']);assert ex.is_relative_to(root/'target')
            pr=subprocess.run([*br,str(ex)],env=env,capture_output=True,check=True)
            assert pr.stdout==b'29\n' and not pr.stderr
            (dot/'program.stdout').write_bytes(pr.stdout);runtime=29;elf=sumfile(t/ex.relative_to(root))
            if phase=='first':assert not art['fresh']
            if phase=='next' and case=='build-ordinary':assert art['fresh']
        material={}
        for refer,leg in files:
            now=t/refer.relative_to(root)
            if now.is_file():
                b=now.read_bytes();(dot/'encoded').write_bytes(b)
                material=dict(old_sha=leg,old_version=refer.read_bytes()[5],new_sha=sha(b),version=b[5])
        row=dict(case=case,phase=phase,cargo=actual,cmd=initial['cmd'],rc=z.returncode,dirty=[v['target']['name'] for v in arts if not v['fresh']],
                 fresh=[v['fresh'] for v in arts],runtime=runtime,elf=elf,old_runtime=initial['runtime'],old_rc=initial['rc'],
                 old_fresh=initial['fresh'],errors=[(v.get('code') or {}).get('code') for v in diagnostics],
                 clean_diag_sha=sha(json.dumps(original_diag,sort_keys=True).encode()),encoded=material,
                 stdout=sha(z.stdout),stderr=sha(z.stderr),source=frozen)
        write(dot/'record.json',row);out.append(row)
    assert sumfile(src/'src/main.rs')==frozen and all(sumfile(f)==h for f,h in files)
    write(t/'result.json',out);return [[v['rc'],v['fresh'],v['runtime'],v['errors'],v['encoded'].get('version')] for v in out]

def main():
    assert socket.gethostname()=='charlie-ohm-cargo5-build-1025' and not o.exists() and sumfile(candidate)==expected
    assert shutil.disk_usage(p).free>50*2**30
    os.sched_setaffinity(0,{6,7});o.mkdir(mode=0o700);result={}
    for group,b in [('plain','ordinary-binary-include-v1'),('alias','ordinary-binary-alias-v2')]:
        source=p/b;(o/group).mkdir()
        for case in sorted(read(source/'complete.json')):
            label=group+'/'+case
            result[label]=job(group,case,source/case);write(o/'progress.json',result)
    write(o/'complete.json',result);print(json.dumps(result))

try:main()
except BaseException:
    if o.is_dir():(o/'failure.txt').write_text(traceback.format_exc())
    raise

"""Cold, unscored ordinary test builds with separate output stores and timestamped successful execs."""
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback

X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
PROTO=Path(__file__).resolve().parent
OUT=X/'early-tests-16-discovery-v1'
RAM=Path('/dev/shm/ohm-early-tests-16-discovery-v1')
OLD=X/'cfg-library-first-v1-campaign/state/check'
SUP=X/'first-occurrence-worker-v2'
sys.path.insert(0,str(SUP))
from common import CARGO_HOME,TARGET,SHARED,P,FROZEN,RUFF,sha,dump,git,elf
from namespace import skeleton
from witness import audit_json
expected={'cargo':'42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568','frontend':'b0c412a7a8010a768f00546419a0b1bcfca382d7e70191df3ae72e30ac1ef3e5','driver':'c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4','wild':'0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'}
log='cargo::compiler::ohm_early_tests=info,cargo::compiler::job_queue=debug'
def dump1(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def input_check(root):
    data={}
    for p in sorted((root/'registry/cache').glob('*/*.crate')):data[p.name]=sha(p)
    assert len(data)>300 and len(data)==len(list((root/'registry/cache').glob('*/*.crate')))
    return data
def capture(pipe,base,which):
    keys=[b'job_queue: start ',b'job_queue: end (',b'ohm_early_tests:',b'Compiling ',b'Finished ']
    with (base/(which+'.raw')).open('xb') as raw,(base/(which+'.clock.jsonl')).open('x') as idx:
        offset=0
        while line:=pipe.readline():
            wall=time.time_ns(); mono=time.monotonic_ns()
            raw.write(line)
            if which=='stdout' or any(k in line for k in keys):
                idx.write(json.dumps([offset,len(line),wall,mono],separators=(',',':'))+'\n')
            offset+=len(line)
def measure(st,arm):
    o=OUT/arm;o.mkdir();(o/'trace').mkdir()
    official=json.loads((X/'build-script-current-stock-sdk-v1/official.json').read_bytes())
    sdk=Path(official['sdk_root']); assert official['hashes']==expected
    table={'cargo':sdk/'bin/cargo','frontend':sdk/'bin/rustc','driver':sdk/'lib'/official['driver_name'],'wild':sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd'}
    assert {k:sha(f) for k,f in table.items()}==expected
    st.mkdir(mode=0o700);(st/'target').mkdir();(st/'shared').mkdir();(st/'registry-home').mkdir()
    subprocess.run(['cp','-a','--reflink=auto','--',OLD/'registry-home/registry',st/'registry-home/registry'],check=True)
    subprocess.run(['cp','-a','--reflink=auto','--',OLD/'rustup',st/'rustup'],check=True)
    assert (st/'rustup/toolchains/ohm').resolve()==FROZEN.resolve() and not any((st/'target').iterdir()) and not any((st/'shared').iterdir())
    assert sorted(f.name for f in (st/'registry-home').iterdir())==['registry']
    registry=input_check(st/'registry-home');dump1(o/'cargo-registry.json',registry)
    assert not (o/'inputs.json').is_file()
    mount=[v for s,d in [(OUT,OUT),(st/'target',TARGET),(st/'shared',SHARED),(st/'registry-home',CARGO_HOME),(st/'rustup',P/'rustup')] for v in ('--bind',str(s),str(d))]
    args=[*skeleton(o),*mount,'--ro-bind',str(sdk),str(FROZEN),'--chdir',str(RUFF),'--','taskset','-c','0-23']
    env=dict(HOME=str(Path.home()),USER='dev-user',PATH=str(Path.home()/'.cargo/bin')+':/usr/local/bin:/usr/bin:/bin',RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0',CARGO_HOME=str(CARGO_HOME),CARGO_TARGET_DIR=str(TARGET),CARGO_BUILD_BUILD_DIR=str(SHARED),CARGO_BUILD_JOBS='8',GIT_OPTIONAL_LOCKS='0',LANG='C.UTF-8',LC_ALL='C.UTF-8',CARGO_TERM_COLOR='never',CARGO_LOG=log,SSL_CERT_FILE='/etc/ssl/certs/ca-certificates.crt',SSL_CERT_DIR='/etc/ssl/certs')
    assert all(k not in env for k in ['CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST','RUSTC_WRAPPER','RUSTFLAGS','RUSTC_WORKSPACE_WRAPPER'])
    check="from pathlib import Path;import hashlib,json,subprocess,sys;p=Path(sys.argv[1]);paths="+repr({k:str(f.relative_to(sdk)) for k,f in table.items()})+"; print(json.dumps({k:hashlib.file_digest((p/f).open('rb'),'sha256').hexdigest() for k,f in paths.items()})); print(subprocess.check_output(['cargo','+ohm','-V'],text=True).strip());print(subprocess.check_output(['rustc','+ohm','-V'],text=True).strip())"
    bind=subprocess.check_output([*args,'/usr/bin/python3','-B','-c',check,str(FROZEN)],env=env,text=True).splitlines()
    assert json.loads(bind[0])==expected and all('ohm-1.99.0-16' in v for v in bind[1:])
    cmd=['cargo','+ohm']+([] if arm=='default' else ['-Zohm-early-tests=no'])+['test','--no-run','--locked','--offline','-j8','--message-format=json']
    trace=['strace','-q','-ff','-ttt','-s','1048576','-e','trace=execve,execveat','-e','signal=SIGCHLD','-o',str(o/'trace/exec'),*cmd]
    dump1(o/'inputs.json',dict(arm=arm,source=git('rev-parse','HEAD'),source_index=hashlib.sha256(subprocess.check_output(['git','-C',RUFF,'ls-files','-s'])).hexdigest(),cargo_lock=sha(RUFF/'Cargo.lock'),sdk=expected,versions=bind[1:],trust_overrides=False,canonical_paths={k:str(v) for k,v in {'source':RUFF,'target':TARGET,'build':SHARED,'registry':CARGO_HOME,'runtime':FROZEN}.items()},physical_state=str(st),empty_target=True,empty_shared=True,registry_manifest_sha256=sha(o/'cargo-registry.json'),command=cmd,trace_options=trace[:trace.index('-o')],cargo_log=log))
    proc=subprocess.Popen([*args,*trace],env=env,cwd=RUFF,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    threads=[threading.Thread(target=capture,args=(pipe,o,name)) for name,pipe in [('stdout',proc.stdout),('stderr',proc.stderr)]]
    for th in threads:th.start()
    try:
        while True:
            try:rc=proc.wait(timeout=4);break
            except subprocess.TimeoutExpired:
                assert shutil.disk_usage(RAM).free>7*2**30 and shutil.disk_usage(X).free>20*2**30 and shutil.disk_usage(P).free>15*2**30,'disk reserve'
    finally:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait()
        for th in threads:th.join()
    dump1(o/'cargo-exit.json',dict(returncode=rc,stdout_sha256=sha(o/'stdout.raw'),stderr_sha256=sha(o/'stderr.raw')))
    assert rc==0,(arm,rc)
    subprocess.run([*args,'/usr/bin/python3','-B',str(PROTO/'capture.py'),'elf',str(o)],check=True,env=env)
    assert not git('status','--porcelain')
    print(arm,'cold command and ELF output capture complete',flush=True)
def inner(path):
    o=Path(path);ev=audit_json(o/'stdout.raw','test');arts=[json.loads(l) for l in (o/'stdout.raw').read_bytes().splitlines()];arts=[a for a in arts if a.get('reason')=='compiler-artifact']
    assert len(ev['executables'])==102 and len(ev['elf'])==110 and len(arts)==619 and not any(a['fresh'] for a in arts)
    groups=collections.Counter(a['profile']['test'] for a in arts if a['executable'])
    assert groups=={True:84,False:18},groups
    fingerprints={f:elf(Path(f)) for f in ev['elf']}
    dump1(o/'elf.json',fingerprints);dump1(o/'products.json',ev)
    dump1(o/'output-summary.json',dict(unit_count=len(arts),fresh=sum(a['fresh'] for a in arts),harness_profile=groups[True],other_executables=groups[False],whole_ELF=len(fingerprints),messages=ev['messages'],roster=ev['roster_sha256'],elf_file=sha(o/'elf.json')))
def main():
    assert socket.gethostname()=='charlie-ohm-relink-b-1024'
    assert git('rev-parse','HEAD')=='93526150df078af7dd8fc4226cdcc469539d2001' and not git('status','--porcelain')
    assert not OUT.exists() and not RAM.exists()
    assert shutil.disk_usage(RAM.parent).free>45*2**30 and shutil.disk_usage(X).free>25*2**30 and shutil.disk_usage(P).free>18*2**30
    OUT.mkdir(mode=0o700);RAM.mkdir(mode=0o700)
    with (P/'native-measure.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for arm in ('default','disabled'):measure(RAM/arm,arm)
        assert sha(OUT/'default/cargo-registry.json')==sha(OUT/'disabled/cargo-registry.json')
        a=json.loads((OUT/'default/output-summary.json').read_bytes());b=json.loads((OUT/'disabled/output-summary.json').read_bytes());assert a['roster']==b['roster'] and a['messages']==b['messages']
        dump1(OUT/'complete.json',dict(unscored=True,cargo_exits=[0,0],physical_elves=[a['whole_ELF'],b['whole_ELF']],source_clean=not bool(git('status','--porcelain'))))
if __name__=='__main__':
    if len(sys.argv)>1:inner(sys.argv[2])
    else:
        try:main()
        except BaseException:
            if OUT.exists():(OUT/'capture-failure.txt').write_text(traceback.format_exc())
            raise

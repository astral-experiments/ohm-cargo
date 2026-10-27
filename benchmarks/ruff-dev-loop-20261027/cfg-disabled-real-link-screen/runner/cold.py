"""Warm only genuinely empty full-workspace source/target histories before any formal observations."""
from pathlib import Path
import fcntl,os,subprocess,sys,time
from shared import *
from roster import audit_json
def inside(edit,arm):
    out=P/'results'/edit/arm/'cold';out.mkdir(parents=True)
    view(edit,False);trusted();floors(15*2**30)
    need(sorted(os.sched_getaffinity(0))==list(range(24)) and sha(FROZEN/'bin/cargo')==plan()['arms'][arm]['cargo'] and sha(FROZEN/'lib'/SONAME)==plan()['baseline_rustc'] and sha(FROZEN/'bin/rustc')==FRONT,'frozen runtime/lane')
    need(not any(TARGET.iterdir()) and not any(BUILD.iterdir()),'priming from a nonempty unit store')
    cmd=plan()['command'];trace=['strace','-ff','-qq','-s','262144','-e','trace=execve,execveat','-o',str(out/'exec')]
    with (out/'stdout').open('wb') as so,(out/'stderr').open('wb') as se:
        start=time.monotonic_ns();s=subprocess.run(trace+cmd,stdin=subprocess.DEVNULL,stdout=so,stderr=se,cwd=WT,env=env());elapsed=time.monotonic_ns()-start
    dump(out/'invocation.json',{'elapsed_ns':elapsed,'command':cmd,'traced':True,'status':s.returncode,'free':floors()});need(s.returncode==0,('cold failed',out,(out/'stderr').read_text()[-900:]))
    j=audit_json(out/'stdout','test');need(len(j['dirty'])==619,('initial fresh units',j['dirty']))
    dump(out/'receipt.json',{'elapsed_ns':elapsed,'units':j['units'],'fresh_units':0,'roster':j['roster_sha256'],'elf_count':len(j['elf']),'traced':True});print(edit,arm,'cold complete',elapsed,flush=True)
if len(sys.argv)>1 and sys.argv[1]=='--inside':inside(*sys.argv[2:]);sys.exit(0)
need(not (P/'results/score').exists(),'scoring already started')
with (P/'bench.lock').open('a') as l:
    fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for edit in ('parser','stdlib','wasm-only'):
        for arm in 'ABC':
            st=state(edit,arm);out=P/'results'/edit/arm/'cold'
            if (out/'receipt.json').is_file():continue
            if not st.exists():seed(edit,arm)
            need(not out.exists() and (st/'seed.json').is_file(),'prior incomplete cold command')
            print('starting',edit,arm,flush=True)
            subprocess.run([*shell(edit,arm),sys.executable,'-B',str(HERE/'cold.py'),'--inside',edit,arm],check=True,env=env())

"""Unscored physical process attribution for the qualified H7 spaced ty_wasm edit."""
import fcntl, importlib.util, json, os, shutil, subprocess, sys, time, zipfile
from pathlib import Path
P=Path('/mnt/devbox-scratch/dev-user/ohm-early-completion-20261027')
O=P/'spaced-dirty-attribution-20261028'
D=O/'scripts'
src=P/'member-build-wall-protocol-v2'
spec=importlib.util.spec_from_file_location('prior_wall',src/'wall_members.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
w.out=O
def emit(path, data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def check_free(reserve=60):
    free=shutil.disk_usage(P).free
    assert free>reserve*2**30,(free,reserve)
def audit(arm,d):
    assert arm.ordinary(d/'json')==arm.reference[arm.source]['settled_dirty']
    arm.verify(d/'products')
def sample(arm,d,mode):
    d.mkdir(parents=True)
    if mode=='life':
        argv=['/usr/bin/python3','-B',str(D/'life.py'),str(d),*w.cmd]
    else:
        argv=['strace','-ff','-qq','-ttt','-s','100','-e','trace=execve,wait4,waitid,exit_group','-o',str(d/'proc'),*w.cmd]
    result=arm.run(argv,d)
    (d/'stdout').write_bytes(result.stdout);(d/'stderr').write_bytes(result.stderr)
    assert result.returncode==0 and not result.stdout and b'Finished' in result.stderr and b'Blocking waiting' not in result.stderr,(result.returncode,result.stderr[-500:])
    emit(d/'info.json',{'image':arm.image,'source':arm.source,'argv':argv,'source_sha':w.q.sha(arm.visible),'code':result.returncode})
def main():
    os.sched_setaffinity(0,set(range(8)))
    check_free(70)
    with (P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); w.q.source_gate()
        assert not (O/'states').exists()
        arms={}
        for image in 'BC':
            arms[image]=a=w.Arm(image,'ty_wasm')
            audit(a,O/'anchor'/image)
        for i,order in enumerate(('BC','CB','CB','BC','BC','CB')):
            mode='process' if i<2 else 'life'
            stage='reversed' if i%2==0 else 'original'
            for image in order:
                a=arms[image];a.switch(stage)
                d=O/'observations'/f'{i+1:02}-{image}'
                check_free()
                sample(a,d/'edit',mode);sample(a,d/'repeat',mode)
                a.verify(d/'products')
            emit(O/'progress.json',{'blocks':i+1,'mode':mode,'stage':stage})
        w.q.source_gate()
        emit(O/'complete.json',{'diagnostic_only':True,'commands':24,'fresh_and_native_anchors':2})
if __name__=='__main__': main()

"""Count the real compiler and build-script children in isolated Cargo commands; no wall scoring."""
import collections, fcntl, json, os, shutil, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect as x
w=x.w; O=x.O/'ir-v1'; T=x.O/'tools-v1'; w.out=O
def getcount(f):
    rows=[s.split() for s in f.read_text().splitlines()]
    assert rows and all(len(r)==4 for r in rows),(f,rows[:1])
    p=f.name.split('-')[0]
    assert rows[0]==['B',p,'0','0'] and rows[-1]==['P',p,'0','0'],(f,rows[:1],rows[-1:])
    ts=sorted((r[1],r[2]) for r in rows if r[0]=='T')
    fs=sorted((r[1],r[2]) for r in rows if r[0]=='F');assert ts==fs and len(set(ts))==len(ts)
    return dict(total=sum(int(r[3]) for r in rows if r[0]=='F'),threads=len(ts),count_sha=w.q.sha(f))
def counts(a,d):
    d.mkdir(parents=True); prior=dict(a.env)
    a.env.update(OHM_DIAG_COUNT_DIR=str(d),OHM_DIAG_DR_ROOT=str(T),LD_PRELOAD=str(T/'calibration-v2/dispatch.so'))
    try:r=a.run(w.cmd,d)
    finally:a.env=prior
    (d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
    assert r.returncode==0 and not r.stdout and b'Finished' in r.stderr and b'Blocking waiting' not in r.stderr,(r.returncode,r.stderr[-600:])
    rows={}
    for f in d.glob('*.count'):
        stem=f.with_suffix('').name
        image=stem.split('-',1)[1]
        arg=(d/(stem+'.args')).read_bytes().rstrip(b'\0').split(b'\0')
        if image=='rustc' and b'--crate-name' in arg:image+=':'+os.fsdecode(arg[arg.index(b'--crate-name')+1])
        assert image not in rows,(image,r.stderr[-400:])
        rows[image]=getcount(f)
    x.emit(d/'counts.json',rows)
    assert set(rows)=={'cargo','rustc:ty_vendored','rustc:ty_wasm','build_script_build'},(list(rows),r.stderr[:500])
    return rows
def main():
    os.sched_setaffinity(0,set(range(8)));x.check_free(70);O.mkdir()
    assert (x.O/'complete.json').is_file()
    with (x.P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);w.q.source_gate()
        arms={}
        for image in 'BC':
            arms[image]=a=w.Arm(image,'ty_wasm');x.audit(a,O/'anchor'/image)
        for i,order in enumerate(('BC','CB','CB','BC')):
            stage='reversed' if i%2==0 else 'original'
            for image in order:
                a=arms[image];a.switch(stage);d=O/'rows'/f'{i+1:02}-{image}'
                x.check_free();counts(a,d/'edit');a.verify(d/'edited-products')
                assert a.ordinary(d/'repeat')==a.reference[stage]['settled_dirty'];a.verify(d/'settled-products')
            x.emit(O/'progress.json',{'pairs':i+1})
        w.q.source_gate();x.emit(O/'complete.json',{'diagnostic_only':True,'pairs':4})
if __name__=='__main__':main()

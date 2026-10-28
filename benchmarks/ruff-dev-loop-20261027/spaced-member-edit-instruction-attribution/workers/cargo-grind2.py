import fcntl,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect as x
w=x.w;O=x.O/'cargo-grind-v2';T=x.O/'software-counters/callgrind'
def count(a,d):
    d.mkdir(parents=True);env=a.env;a.env=dict(env,LD_PRELOAD=str(T/'call-dispatch.so'),OHM_PRIVATE_CG_OUT=str(d),OHM_PRIVATE_CG_TOOL='cargo',OHM_PRIVATE_CG_ROOT=str(T))
    a.env.update(json.loads((x.O/'ssl-native-control/verified.json').read_bytes())[a.image])
    try:r=a.run(w.cmd,d)
    finally:a.env=env
    (d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
    assert r.returncode==0 and not r.stdout and b'Finished' in r.stderr and b'Blocking waiting' not in r.stderr,(r.returncode,r.stderr[-600:])
    f,=list(d.glob('*-cargo.args'));pid=f.name.split('-')[0]
    argv=[os.fsdecode(v) for v in f.read_bytes().strip(b'\0').split(b'\0')]
    assert argv[1:]==w.cmd[2:],argv
    data=d/('callgrind.'+pid); lines=data.read_text().splitlines()
    assert 'events: Ir' in lines
    cnt,=[int(v.split()[1]) for v in lines if v.startswith('summary:')];assert cnt>10000000
    final,=[int(v.split()[1]) for v in lines if v.startswith('totals:')];assert abs(final-cnt)<5000000,(final,cnt)
    x.emit(d/'supervisor.json',dict(ir=cnt,totals=final,process=pid,argv=argv,native_profile_sha=w.q.sha(data),collector=w.q.sha(T/'usr/libexec/valgrind/callgrind-amd64-linux')))
def main():
    os.sched_setaffinity(0,set(range(8)));x.check_free(69)
    with (x.P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);w.q.source_gate();O.mkdir()
        arms={};w.out=O
        for image in 'BC':
            arms[image]=a=w.Arm(image,'ty_wasm');a.br.extend(['--ro-bind',str(T/'usr/lib/debug'),'/usr/lib/debug'])
            x.audit(a,O/'anchor'/image)
        for i,order in enumerate(('BC','CB','CB','BC')):
            stage='reversed' if i%2==0 else 'original'
            for image in order:
                a=arms[image];a.switch(stage);d=O/'rows'/f'{i+1:02}-{image}'
                x.check_free(63);count(a,d/'edit');a.verify(d/'edited-products')
                assert a.ordinary(d/'repeat')==a.reference[stage]['settled_dirty'];a.verify(d/'settled-products')
            x.emit(O/'progress.json',{'pairs':i+1})
        w.q.source_gate();x.emit(O/'complete.json',{'pairs':4,'collector':'Callgrind Cargo only','diagnostic_only':True})
if __name__=='__main__':main()

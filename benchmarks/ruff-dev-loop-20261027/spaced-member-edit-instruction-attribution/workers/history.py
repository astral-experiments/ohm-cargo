"""Same corrected binary, canonical path and files; change only whether the prior unchanged fulls run."""
import collections, fcntl, json, os, shutil, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import collect as x
import counts2 as ir
w=x.w;O=x.O/'history-v1'
def force(a,d):
    """Preserve and remove only Cargo's private two dep-info files; leave rustc's IC intact."""
    assert a.st.is_relative_to(O) and a.st != O
    d.mkdir(parents=True)
    rows={}
    for crate in ('ty_vendored','ty_wasm'):
        f,=list((a.st/'target').rglob('dep-lib-'+crate));assert f.parent.name=='fingerprint'
        rows[crate]=dict(relative=str(f.relative_to(a.st)),sha256=w.q.sha(f),size=f.stat().st_size)
        f.rename(d/f.name)
    x.emit(d/'files.json',rows)
def replay(a,d):
    d.mkdir(parents=True);trace=d/'trace';trace.mkdir()
    av=['strace','-ff','-qq','-s','1048576','-e','trace=execve,execveat','-o',str(trace/'exec'),*w.cmd,'--message-format=json']
    ret=a.run(av,d);(d/'stdout').write_bytes(ret.stdout);(d/'stderr').write_bytes(ret.stderr)
    assert ret.returncode==0 and b'Blocking waiting' not in ret.stderr,(ret.returncode,ret.stderr[-600:])
    rows=[json.loads(r) for r in ret.stdout.splitlines()];assert w.typed(rows)==a.roster and rows[-1]=={'reason':'build-finished','success':True}
    jobs=w.m.capture.cmds(trace); x.emit(d/'physical.json',jobs)
    return [[x['crate'],x['kind']] for x in jobs['jobs']],len(jobs['wild'])
def main():
    os.sched_setaffinity(0,set(range(8)));x.check_free(70)
    assert (x.O/'ir-children-v2/complete.json').is_file();O.mkdir()
    with (x.P/'member-build-native.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);w.q.source_gate()
        arms={}
        for i in ('normal','forced'):
            w.out=O/i;a=arms[i]=w.Arm('C','ty_wasm');x.audit(a,O/'anchor'/i)
        for j,order in enumerate((('normal','forced'),('forced','normal'),('forced','normal'),('normal','forced'),('normal','forced'),('forced','normal'))):
            s='reversed' if j%2==0 else 'original'
            for i in order:
                a=arms[i];d=O/'rows'/f'{j+1:02}-{i}';a.switch(s);x.check_free()
                if j<2:x.sample(a,d/'edit','life')
                else:ir.counts(a,d/'edit')
                a.verify(d/'edited-products')
                if i=='forced':force(a,d/'retained-proofs')
                results=replay(a,d/'repeat')
                x.emit(d/'repeat-jobs.json',results)
                expected=([['ty_vendored','full'],['ty_wasm','full']],1) if i=='forced' else ([],0)
                assert results==expected,(results,expected)
                a.verify(d/'settled-products')
            x.emit(O/'progress.json',{'pairs':j+1})
        w.q.source_gate();x.emit(O/'complete.json',{'counted_pairs':4,'lifecycle_pairs':2,'diagnostic_only':True})
if __name__=='__main__':main()

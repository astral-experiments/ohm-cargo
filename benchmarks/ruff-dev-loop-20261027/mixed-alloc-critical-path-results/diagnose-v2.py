from pathlib import Path
from collections import Counter
import fcntl,hashlib,json,os,shutil,socket,subprocess,sys,traceback,signal,time
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
H=X/'mixed-native-abc-protocol-h3-v2';Q=X/'mixed-alloc-same-compiler-protocol-v1';proof=X/'mixed-alloc-same-compiler-qualification-v1';W=X/'mixed-alloc-cargo-wall-20261027-v2'
D=X/'mixed-critical-path-v2';K=D/'code';P=Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
sys.path[:0]=[str(Q),str(H)]
import helpers as q
from common import load,dump,sha
from namespace import skeleton
from state import source_clean,gate_free,verify_plan,set_source
from products import compare_context
def safe_launch(cmd):
    # Freshness is checked as bytes arrive, in addition to the full frozen worker's final guard.
    fresh='--phase' in cmd and cmd[cmd.index('--phase')+1] in ('fresh','detailed-fresh')
    log=Path(cmd[cmd.index('--out')+1])/'stdout' if fresh else None
    child=subprocess.Popen(cmd,start_new_session=True);seen=0
    try:
        while child.poll() is None:
            gate_free(D);gate_free(Path('/dev/shm'))
            if log is not None and log.is_file():
                with log.open('rb') as f:
                    f.seek(seen)
                    for l in f:
                        if not l.endswith(b'\n'):break
                        seen+=len(l)
                        if b'"reason":"compiler-artifact"' in l:
                            row=json.loads(l)
                            assert row['fresh'],('spurious compilation rejected at first event',row['target']['name'],row['filenames'])
                            assert all('v2-23163ec4bfef81db' not in z for z in row['filenames']),'rejected namespace entered'
            time.sleep(.12)
        assert child.returncode==0,(child.returncode,cmd[-12:])
    except BaseException:
        if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=30)
        raise
def run():
    assert socket.gethostname()=='charlie-ohm-trait-perf-1024' and sorted(os.sched_getaffinity(0))==list(range(24))
    assert load(W/'complete.json')['scored_commands']==80
    assert sha(Q/'SHA256SUMS')=='da50f3cb8a6071b604bb60737084093dc4caef313fba4569c0ded9dba478a2bc' and sha(H/'SHA256SUMS')=='59ca9193f8f6ddf4cff22ab023cc41733200d251f42e3400635f0e81c42a5d71'
    for parent in (Q,H):subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=parent,check=True)
    verify_plan();original=source_clean();q.out=D;q.checked_launch=safe_launch;q.mount=skeleton(D);q.binding=Q/'binding.json';q.b=load(q.binding);q.fixture=proof/'fixture'
    for a,hs in [('B','dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1'),('C','0f237cc3b506aa90c1224e6ed80f646566b424b78c8d74f288f6523d17fc8aa1')]:
        subj=q.b['arms'][a];assert sha(Path(subj['cargo']))==hs==subj['cargo_sha256'];assert sha(Path(subj['driver']))==subj['driver_sha256']=='63145e253973980f3786ce562b2342d2590b4a783256e4197e8ffacdf7d110fa'
    dump(D/'binding.json',{'source_index':original,'formal_complete_sha256':sha(W/'complete.json'),'formal_summary_sha256':sha(W/'statistics.json'),'seed_qualification_sha256':sha(proof/'complete.json'),'source_manifest_sha256':sha(q.fixture/'manifest.json'),'probes':'descriptive only, first both-direction process timelines, then a separately instrumented exact syscall-read edit','arms':{a:{k:v for k,v in q.b['arms'][a].items() if k.endswith('sha256')} for a in 'BC'}})
    for arm in 'BC':
        st=q.state('build',arm);src=proof/'state/build'/arm
        assert (src/'source-state').read_text()=='original' and not st.exists()
        # Clone only one state on the actual study volume at a time. Each complete native input
        # fingerprint must match the prior published qualification; later bytes can be dirtied only here.
        need=int(subprocess.check_output(['du','-s','-B1',src]).split()[0]);gate_free(D,int(need*1.10));st.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['cp','-a','--reflink=auto','--',src,st],check=True)
        # Reserve ext4 for the actual native artifact hashes, outputs and incremental state.
        # The verified private registry directory moves to tmpfs while keeping its visible name.
        reg=Path('/dev/shm')/('ohm-critical-v2-registry-'+arm);assert not reg.exists()
        subprocess.run(['mv','-T','--',st/'registry-home',reg],check=True);(st/'registry-home').symlink_to(reg,target_is_directory=True)
        refs=q.current_rows(proof/'receipts/build'/arm/'first-restore-fresh');seen={}
        for rec in refs:
            if rec['reason']!='compiler-artifact':continue
            for k in rec['filenames']:
                if k in seen:continue
                f=Path(k);label,can=next((n,p) for n,p in [('target',q.TARGET),('shared',q.SHARED)] if f.is_relative_to(p))
                left=src/label/f.relative_to(can);right=st/label/f.relative_to(can);s,t=left.stat(),right.stat()
                assert (s.st_size,s.st_mode,s.st_mtime_ns)==(t.st_size,t.st_mode,t.st_mtime_ns) and not left.samefile(right) and sha(left)==sha(right)
                seen[k]=sha(right)
        assert len(seen)>=501;dump(D/(arm+'-seed-sha.json'),seen)
        print('prepared',arm,len(seen),need,flush=True)
        entry=q.call('build',arm,arm,'detailed-fresh','entry',False);q.check_row(entry,load(proof/'receipts/build'/arm/'first-restore-fresh/receipt.json'))
        for sig,ed in [('process',True),('process',False),('io',True)]:
            label='edit' if ed else 'restore';set_source(st,q.fixture,ed);d=D/(arm+'-'+sig+'-'+label);cmd=[*q.command(st,arm),sys.executable,'-B',K/'inside.py',label,arm,sig,d,st,q.fixture,q.binding];print('observe',arm,sig,label,flush=True)
            q.checked_launch(cmd)
            fresh=q.call('build',arm,arm,'detailed-fresh',sig+'-'+label+'-fresh',ed);ref=load(proof/'receipts/build'/arm/('first-'+label+'-fresh')/'receipt.json');q.check_row(fresh,ref);eq=compare_context(fresh['product'],ref['product']);dump(d/'output-comparison.json',eq)
        # Preserve genuine output hashes and CLI/metadata comparisons and give back only our disposable private clone.
        assert st==D/'state/build'/arm and st.is_dir() and not st.is_symlink();assert sha(proof/'receipts/build'/arm/'first-restore-fresh/receipt.json') and (D/(arm+'-io-edit')/'output-comparison.json').is_file()
        shutil.rmtree(st);assert reg.is_dir() and reg.name=='ohm-critical-v2-registry-'+arm;shutil.rmtree(reg);assert source_clean()==original;gate_free(D)
    dump(D/'complete.json',{'source_index':original,'qualification':sha(proof/'complete.json'),'diagnostic_observations':6,'timed_samples':0})
if __name__=='__main__':
    try:
        with (P/'native-measure.lock').open('a') as lk:fcntl.flock(lk,fcntl.LOCK_EX);run()
    except BaseException:
        (D/'failure.txt').write_text(traceback.format_exc());raise

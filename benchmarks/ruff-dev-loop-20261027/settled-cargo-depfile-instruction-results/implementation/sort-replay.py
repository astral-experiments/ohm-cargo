import fcntl,os,subprocess
import setup as s
D=s.H/'output-path-study';tools=s.P/'spaced-dirty-attribution-20261028/tools-v1'
with (s.P/'member-build-native.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);os.sched_setaffinity(0,range(8))
    m=D/'sort-replay';e=s.env()
    rlib=D/'librustc_hash.rlib';src=next((s.H/'cargo-home/registry/src').glob('*/rustc-hash-2.1.*/src/lib.rs'));subprocess.run(['/home/dev-user/.cargo/bin/rustc','+ohm','--edition','2021','--crate-name','rustc_hash','--crate-type=rlib','--cfg','feature="std"','-Copt-level=3',src,'-o',rlib],env=e,check=True)
    subprocess.run(['/home/dev-user/.cargo/bin/rustc','+ohm','--edition','2024','-Copt-level=3','--extern',f'rustc_hash={rlib}',s.H/'sort-replay.rs','-o',m],env=e,check=True)
    rows=[]
    for mode in ['map-tree','tree','sort','components']:
        f=D/('count-'+mode)
        proc=subprocess.run([tools/'sdk/bin64/drrun','-quiet','-no_follow_children','-c',tools/'client/libpidcounter.so',f,'--',m,mode,D/'input'],env=e,capture_output=True);assert proc.returncode==0,proc.stderr
        assert proc.stdout==(D/'output').read_bytes(),mode
        raw=[l.split() for l in f.read_text().splitlines()];assert len([r for r in raw if r[0]=='B'])==1 and len([r for r in raw if r[0]=='P'])==1 and len([r for r in raw if r[0]=='T'])==len([r for r in raw if r[0]=='F'])==1
        row=dict(mode=mode,ir=sum(int(v[3]) for v in raw if v[0]=='F'),raw=s.sha(f)); rows.append(row);print(row,flush=True)
    s.emit(D/'replay.json',dict(rows=rows,repeat=4,rustc_hash_rlib=s.sha(rlib),input=s.sha(D/'input'),gold=s.sha(D/'output'),program=s.sha(m)))

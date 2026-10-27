from pathlib import Path
from collections import Counter,defaultdict
import bisect,gzip,hashlib,json,os,re,sys
X=Path.home()/'.cache/ohm-233-position-qualified-20261027'
D=X/'mixed-critical-light-v1';H=X/'mixed-native-abc-protocol-h3-v2'
sys.path.insert(0,str(H))
from processes import records
def load(p):return json.loads(p.read_bytes())
def he(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def analyze(d):
    command=load(d/'command.json');typed=load(d/'typed.json');sample=load(d/'sampled-processes.json');jobs=typed['jobs'];native=typed['native'];pidof=lambda v:int(str(v).split('.')[-1]);fproc={}
    for p,img,argv in records(d/'projection'):
        p=pidof(p);q=Path(img);iswild=any(pidof(v)==p for v in native['wild'])
        if q.name=='cargo' and '/rustup/toolchains/ohm/bin/' in img:fproc[p]=('cargo','cargo')
        if '--crate-name' in argv:fproc[p]=('rustc',argv[argv.index('--crate-name')+1])
        if iswild:
            assert '-o' in argv
            fproc[p]=('wild',Path(argv[argv.index('-o')+1]).name)
    cargo_pid,=[p for p,(k,_) in fproc.items() if k=='cargo'];t0={};t1={};parent={};sig={}
    signal=re.compile(r'si_pid=(\d+).*si_status=(\d+).*si_utime=(\d+).*si_stime=(\d+)')
    for f in d.glob('timed.*'):
        pid=int(f.name[6:])
        for row in f.open(errors='replace'):
            line=row.rstrip();timeval=line.split(' ',1)[0];tn=float(timeval)
            if pid in fproc:
                if ' execve(' in line and line.endswith(' = 0'):t0[pid]=tn
                if ' exit_group(' in line:t1[pid]=tn
            if 'SIGCHLD' in line:
                m=signal.search(line)
                if m:
                    child,status,u,ss=map(int,m.groups());parent[child]=pid;sig[child]=[status,u,ss]
    assert set(fproc)<=set(t0) and set(fproc)<=set(t1),(set(fproc)-t0.keys(),set(fproc)-t1.keys())
    base=t0[cargo_pid];make=lambda x:round(x-base,6)
    acc=defaultdict(lambda:[0]*7)
    with gzip.open(d/'samples.jsonl.gz','rt') as f:
        for line in f:
            ts,samples=json.loads(line)
            for pid,ppid,us,sy,rss,threads,rc,wc,rb,wb in samples:
                for i,v in enumerate((us,sy,rss,rc,wc,rb,wb)):acc[pid][i]=max(acc[pid][i],v)
    kind={pidof(j['pid']):j['kind'] for j in jobs}
    results=[]
    for pid,(key,target) in sorted(fproc.items(),key=lambda z:t0[z[0]]):
        ar=acc[pid];times=dict(start=make(t0[pid]),end=make(t1[pid]),seconds=round(t1[pid]-t0[pid],6))
        results.append(dict(kind=key,target=target,compiler_kind=kind.get(pid),pid=pid,**times,sampled_max_user_ticks=ar[0],sampled_max_system_ticks=ar[1],sampled_peak_rss_pages=ar[2],sampled_peak_rchar=ar[3],sampled_peak_wchar=ar[4],sampled_peak_disk_read_bytes=ar[5],sampled_peak_disk_write_bytes=ar[6],sigchld_linux_clock_t_ticks=sig.get(pid)))
    def read_output(name,matcher):
        raw=(d/name).read_bytes();bounds=[json.loads(r) for r in (d/(name+'.clock.jsonl')).read_bytes().splitlines()];ends=[off+n for off,n,t in bounds];offset=0;seen=[]
        for line in raw.splitlines(keepends=True):
            offset+=len(line);selected=matcher(line)
            if selected:seen.append([make(bounds[bisect.bisect_left(ends,offset)][2]/1e9),*selected])
        return seen
    def of(line):
        m=json.loads(line)
        if m.get('reason')=='compiler-artifact' and not m['fresh']:return [m['target']['name'],m['target']['kind']]
    def ef(line):
        s=line.decode(errors='replace').rstrip()
        if 'relink-only: cache validation for ' in s:
            unit,value=s.split('relink-only: cache validation for ',1)[1].rsplit(' took ',1);return [unit,value]
    arts=read_output('stdout',of);validation=read_output('stderr',ef)
    w=[r for r in results if r['kind']=='wild'];mix=[r for r in results if r['kind']=='rustc' and r['target'] in ('ruff_wasm','ty_wasm')]
    before=[r for r in results if r['kind']=='rustc' and r['target']=='ruff_python_parser'];assert len(before)==1 and len(mix)==2 and len(w)==8
    return dict(probe='descriptive timestamped process observation',arm=command['arm'],direction=command['direction'],recorded_command_sha256=he(d/'command.json'),rustc_count=len(jobs),wild_count=len(w),cargo_exit=make(t1[cargo_pid]),parser_finished=before[0]['end'],last_wild_finished=max(r['end'] for r in w),last_compiler_finished=max(r['end'] for r in results if r['kind']=='rustc'),processes=results,artifact_pipe_arrival=arts,actual_cargo_prevalidation_logs=validation,ticks_per_sec=os.sysconf('SC_CLK_TCK'),native_proof=load(d/'output-comparison.json') if (d/'output-comparison.json').exists() else None)
if __name__=='__main__':
    result={d.name:analyze(d) for d in sorted(D.glob('*-fasttrace-*')) if d.is_dir() and (d/'typed.json').is_file()}
    print(json.dumps(result,sort_keys=True))

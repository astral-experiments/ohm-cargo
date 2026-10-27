"""Scoped live registry Ron validation, using locked Ruff dependency versions and actual ELF output."""
from pathlib import Path
import gzip,json,os,re,shutil,statistics,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paired import Study,getargs,sha,log_json
s=Study(getargs());s.bins['V']=Path(os.environ['PREVIOUS_CARGO']).resolve()
old=subprocess.run
def traces(cmd,*a,**k):
    if 'trace=execve' in cmd:
        cmd=list(cmd);cmd[cmd.index('trace=execve')]='trace=execve,prctl'
    return old(cmd,*a,**k)
subprocess.run=traces
env={'CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST':'all','CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST':'all'}
def prepare(label):
    a=s.init(label)
    (a/'src/Cargo.toml').write_text('[workspace]\nmembers=["probe_ron"]\nresolver="2"\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\n')
    d=a/'src/probe_ron';(d/'src').mkdir(parents=True)
    (d/'Cargo.toml').write_text('[package]\nname="probe_ron"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nron="=0.12.0"\n')
    (d/'src/lib.rs').write_text('pub fn text()->String{ron::to_string(&17u32).unwrap()}\n#[test]fn check(){assert_eq!(text(),"17")}\n')
    (a/'cargo-home/registry').symlink_to(Path.home()/'.cache/ohm-ruff-loop-20261026/registry-home/registry')
    shutil.copyfile(Path.home()/'code/oss/ruff-ohm-loop-default-20261026/Cargo.lock', a/'src/Cargo.lock')
    return a
def run(k,a,name,trace):
    r=s.run(a,k,name,trace=trace,packages=('probe_ron',),mode='test --no-run',envadd=env,check_product=False)
    output=gzip.decompress((s.logs/name/'stderr.gz').read_bytes()).decode()
    written=re.findall(r'^\s*Executable unittests src/lib.rs \((.+)\)$',output,re.MULTILINE)
    assert len(written)==1,(name,written)
    paths=[a/Path(written[0]).relative_to(s.active)]
    assert paths[0].is_file() and os.access(paths[0],os.X_OK)
    helper=None
    if trace:
        raw=gzip.decompress((s.logs/name/'exec.gz').read_bytes()).decode(errors='replace')
        helper=sum('PR_SET_NAME, "cargo-checksum"' in x for x in raw.splitlines())
    return r,sha(paths[0]),helper
_,gold,_=run('P',prepare('empty-reference'),'empty-reference',True)
arms={k:prepare('arm-'+k) for k in 'VC'}
helpers={}
for k,a in arms.items():
    for i in range(4):
        r,h,n=run(k,a,f'{k}-train-{i}',True);assert h==gold,(k,h,gold)
    assert r['roster']==[],r['roster']
    assert any('dep-lib-ron' in k and x['complete'] for k,x in r['readers'].items()),r['readers']
    helpers[k]=n;assert bool(n)==(k=='C'),(k,n)
samples={k:[] for k in arms}
for i,order in enumerate(('VC','CV','CV','VC'),1):
    for k in order:
        r,h,_=run(k,arms[k],f'native-{i}-{k}',False);assert h==gold
        samples[k].append(r['ns']/1e6)
for k,a in arms.items():
    r,h,n=run(k,a,'audited-final-'+k,True);assert r['roster']==[] and h==gold and n==helpers[k]
report={'scope':'small actual registry Ron 0.12.0 test-build; four exploratory pairs','cargo_sha256':{k:sha(s.bins[k]) for k in arms},
        'driver_sha256':s.digest['driver'],'elf':gold,'helpers':helpers,'native_ms':samples,
        'medians_ms':{k:statistics.median(v) for k,v in samples.items()},
        'paired_reduction_pct':statistics.median(100*(1-c/v) for c,v in zip(samples['C'],samples['V']))}
log_json(s.logs/'screen.json',report);print(json.dumps(report,indent=2))

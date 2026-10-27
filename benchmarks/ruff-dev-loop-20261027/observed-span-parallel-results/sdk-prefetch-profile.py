"""Small native feasibility and actual worker proof; independent from the registered v4 series."""
from pathlib import Path
import gzip,json,os,statistics,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from paired import Study,getargs,sha,log_json
s=Study(getargs())
baseline=Path(os.environ['PREVIOUS_CARGO']).resolve()
s.bins['V']=baseline
subject=json.loads((s.logs/'subject.json').read_text())
subject['sha256']['V']=sha(baseline);subject['resolved']['V']=str(baseline)
log_json(s.logs/'subject.json',subject)
s.references();stores={arm:s.init('pilot-'+arm) for arm in 'VC'}
normal=subprocess.run
def include_thread_names(cmd,*args,**kwargs):
    if 'trace=execve' in cmd:
        cmd=list(cmd);cmd[cmd.index('trace=execve')]='trace=execve,prctl'
    return normal(cmd,*args,**kwargs)
subprocess.run=include_thread_names
def helper_count(row):
    raw=gzip.decompress((s.logs/row['phase']/'exec.gz').read_bytes()).decode(errors='replace')
    return sum('PR_SET_NAME, "cargo-checksum"' in line for line in raw.splitlines())
readers={'hold_bridge','hold_direct'}
for arm,store in stores.items():
    for i in range(4):
        r=s.run(store,arm,f'train-{arm}-{i}',trace=True);s.equivalent(r,s.gold[False])
    assert r['roster']==[] and len(r['readers'])==2
    n=helper_count(r)
    assert (n>0)==(arm=='C'),(arm,n)
result={'warm_noop_ms':{},'changed_native_ms':{},'source':s.digest,'control_cargo':sha(baseline),'cpu':s.a.cpus}
for phase,orders in [('noop',('VC','CV','CV','VC')),('edit',('CV','VC'))]:
    rows={k:[] for k in stores};new=False
    for i,order in enumerate(orders,1):
        if phase=='edit':new=not new
        for arm in order:
            if phase=='edit':s.edit(stores[arm],new)
            row=s.run(stores[arm],arm,f'native-{phase}-{i}-{arm}')
            s.equivalent(row,s.gold[new]);rows[arm].append(row['ns']/1e6)
    result['warm_noop_ms' if phase=='noop' else 'changed_native_ms']=rows
for state in [True,False]:
    for arm,store in stores.items():
        s.edit(store,state);row=s.run(store,arm,f'audit-edit-{int(state)}-{arm}',trace=True);s.equivalent(row,s.gold[state])
        assert len(row['roster'])==5
        assert {x['crate'] for x in row['roster'] if x['mode']=='full'}=={'hold_shapes','hold_indirect',*readers}
        assert {x['crate'] for x in row['roster'] if x['capture']}==readers
        assert helper_count(row)==0, (row['phase'],helper_count(row))
# Same invocation/namespace and job count, borrowing whatever GNU Make offers.
fifo=s.root/'jobserver';os.mkfifo(fifo);fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
env={'CARGO_MAKEFLAGS':f' -j --jobserver-auth=fifo:{fifo}', 'MAKEFLAGS':f' -j --jobserver-auth=fifo:{fifo}'}
gate={}
for name,available in [('empty',False),('one',True)]:
    if available:os.write(fd,b'+')
    row=s.run(stores['C'],'C','jobserver-'+name,trace=True,envadd=env)
    s.equivalent(row,s.gold[False]);assert row['roster']==[],row['roster']
    observed=helper_count(row);gate[name]=observed
    assert (observed>0)==available,(name,observed)
    if available:assert os.read(fd,1)==b'+'
with open(s.root/'no-token-passed','w') as f:print(gate,file=f)
one=s.init('one-job');env={'CARGO_BUILD_JOBS':'1'}
for i in range(4):
    row=s.run(one,'C',f'one-job-{i}',trace=True,envadd=env)
    # Compile job count may change context, but the outputs must still agree.
    s.equivalent(row,s.gold[False],require_elf=False)
    assert helper_count(row)==0
assert row['roster']==[]
result['helper_counts_inherited_jobserver']=gate;result['one_job_helpers']=0
result['normalized']={n:{'V_median':statistics.median(r['V']),'C_median':statistics.median(r['C']),
    'paired_reduction':statistics.median(100*(1-c/v) for v,c in zip(r['V'],r['C']))}
    for n,r in result.items() if n.endswith('_ms')}
log_json(s.logs/'screen.json',result)
print(json.dumps(result,indent=2))

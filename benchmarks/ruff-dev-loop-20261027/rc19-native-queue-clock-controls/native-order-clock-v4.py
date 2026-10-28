"""Execute one full prespecified batch with no interim inference or selective sample removal."""
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path.home()/'.cache/ohm-18-ty-e2e-link-20261028';study=root/'native-ready-order19';reports=study/'reports';ops=root/'ops';worker=ops/'native-order-primary-v4.py';lane=study/'native-order-lane.py'
section,label=sys.argv[1:];assert section in ('batch1','batch2','edit','plain');assert label.isalnum()
read=lambda path:json.loads(path.read_bytes())
def sha(path):
    with path.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def put(path,value):
    with path.open('x') as out:json.dump(value,out,sort_keys=True,indent=2);out.write('\n')
def outer(*a,quiet=True):subprocess.run([sys.executable,'-IB',lane,*a],stdout=subprocess.DEVNULL if quiet else None,check=True)

def envelope():
    others=[]
    names={'cargo','rustc','collect2','g++','ld.bfd','wild','wild-linker','clang','clang++','valgrind','strace','perf','lto1','cc1','cc1plus','rust-lld','rsync','zstd','pigz','tar'}
    for child in Path('/proc').iterdir():
        if not child.name.isdecimal():continue
        try:name=Path(os.readlink(child/'exe')).name
        except (PermissionError,FileNotFoundError,ProcessLookupError):continue
        if name in names:others.append([child.name,name])
    relative=next(v.removeprefix('0::').lstrip('/') for v in Path('/proc/self/cgroup').read_text().splitlines() if v.startswith('0::'))
    cgroups={};cg=Path('/sys/fs/cgroup')/relative
    for upper in [cg,*cg.parents]:
        if not upper.is_relative_to('/sys/fs/cgroup'):break
        files={name:(upper/name).read_text().strip() for name in ('memory.events','memory.max','memory.peak','memory.pressure','cpu.max','cpu.stat','io.pressure') if (upper/name).is_file()}
        if files:cgroups[str(upper.relative_to('/sys/fs/cgroup'))]=files
    return {'time_ns':time.time_ns(),'others':others,'cpu_mask':sorted(os.sched_getaffinity(0)),'cpu_stat':Path('/proc/stat').read_text().splitlines()[0],
            'load':os.getloadavg(),'pressure':{p.name:p.read_text().strip() for p in Path('/proc/pressure').iterdir() if p.is_file()},'cgroups':cgroups}
def ensure(env):
    assert not env['others'] and env['cpu_mask']==list(range(32)),env['others']
def oom(env):return {group:int(line.split()[1]) for group,fields in env['cgroups'].items() if 'memory.events' in fields for line in fields['memory.events'].splitlines() if line.startswith('oom_kill ')}

assert sha(ops/'native-order-random-order.json')=='db9a7dff6e92e03349af00832b6693e7d1d6d844a750d709f79ebe0925186ed4'
order=read(ops/'native-order-random-order.json')['primary'];admission=read(reports/'functional-admission-v4.json')
assert admission['eligible'] and admission['plan_sha256']=='467090560adc9c413466e40f2b80770ab781245f0fa8af3ad7839a94829b10a6'
assert admission['worker_sha256']==sha(worker) and admission['lane_sha256']==sha(lane)
for name,digest in admission['receipts'].items():assert sha(reports/name/'result.json')==digest
for arm,digest in admission['images'].items():assert sha(study/'images'/arm)==digest and sha(study/'images'/(arm+'-build.json'))==admission['binding_sha256'][arm]
# This separate packet is issued only after actual scheduler eligibility, complete product qualification and resource adjudication.
permission=read(reports/'clock-release-v4.json');assert permission['eligible'] and permission['functional_sha256']==sha(reports/'functional-admission-v4.json') and permission['images']==admission['images']
assert permission['controller_sha256']==sha(Path(__file__)) and permission['h8_caps_sha256']==sha(ops/'native-order-h8-caps-v4.json')=='ecb94f95e49b43db0474bb55977f41b129d65db4dbc518332e0a0659991b9d4f'
assert permission['h8_anchor_sha256']==sha(ops/'native-order-h8-physical-v4.json')
assert permission['source']=={'A':'235f9228651b74c591e6f62cae4c9b761448dd2d','B':'4b0751af97bfa22204a013d0d1f0707382b0df52'}
for arm,source in permission['source'].items():assert read(study/'images'/(arm+'-build.json'))['tree']==source
assert sha(reports/'stationary-ext4-geometry-v6.json')=='103192ed12d0995d0b9eda7495f35de37b7f67c091b77db94332e3932c450e42'
lock=(root/'measure.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
batch={'batch1':'batch1','batch2':'batch2','plain':'batch2','edit':'qa'}[section]
section_grant=reports/('clock-section-'+section+'-'+label+'-v4.json');grant=read(section_grant)
assert grant['section']==section and grant['lane']==batch and grant['label']==label and grant['released'] and grant['no_concurrent_transfers']
assert grant['global_release_sha256']==sha(reports/'clock-release-v4.json')
for evidence in grant['physical_receipts']:
    file=Path(evidence['path']);assert file.is_file() and sha(file)==evidence['sha256']
assert grant['physical_receipts'] and grant['spaces']
for space in grant['spaces']:
    assert space['minimum_free_bytes']>0 and shutil.disk_usage(space['path']).free>=space['minimum_free_bytes'],space
if section=='edit':assert grant['pristine_edit_pair'] and grant['distinct_from_both_stationary_batches']
schedule=(order['batches'][int(batch[-1])-1] if section.startswith('batch') else order['plain' if section=='plain' else 'edit_and_repeat'])
assert len(schedule)==({'edit':12,'plain':16}.get(section,48));assert Counter(schedule)=={'AB':len(schedule)//2,'BA':len(schedule)//2}
name='clock-v4-'+section+'-'+label; d=reports/name;d.mkdir();before=envelope();ensure(before);put(d/'host-before.json',before)
def run(arm,mode,state,shape,slot):
    tag=name+'-'+slot+'-'+arm
    outer('run',batch,arm,'--',sys.executable,'-IB',worker,mode,arm,state,shape,tag)
    return read(reports/tag/'result.json')
def trace(arm,phase):return run(arm,'census','original','repeat',phase)
starting={arm:json.loads(subprocess.check_output([sys.executable,'-IB',lane,'paths',batch,arm])) for arm in 'AB'}
source=read(root/'prepared.json')
for row in starting.values():assert sha(Path(row['source'])/source['file'])==source['old_sha256']
assert starting['A']['namespace']!=starting['B']['namespace'] and starting['A']['source']!=starting['B']['source']
for store in ('target','shared','cargo'):
    a,b=[Path(starting[arm]['upper'][store]) for arm in 'AB'];assert a.is_dir() and b.is_dir() and not os.path.samefile(a,b)
put(d/'binding.json',{'order':schedule,'section':section,'batch':batch,'starting_lanes':starting,'admission_sha256':sha(reports/'functional-admission-v4.json'),'clock_release_sha256':sha(reports/'clock-release-v4.json'),'section_release_sha256':sha(section_grant),'controller_sha256':sha(Path(__file__))})
for arm in 'AB':
    run(arm,'warm','original','settle','prepare');trace(arm,'trace-before')
a0=read(reports/(name+'-trace-before-A')/'result.json');b0=read(reports/(name+'-trace-before-B')/'result.json')
assert a0['native_args']==b0['native_args'] and a0['compiler_args']==b0['compiler_args'], 'unequal input roster before timing'
assert len(a0['native_args'])==150 and len(a0['compiler_args'])==51
for n in (1,2):
    for arm in 'AB':run(arm,'warm','original','repeat','warm-'+str(n))
print('Eligible work and two ordinary warmups verified in each arm.',flush=True)
pairs=[]
for n,sequence in enumerate(schedule,1):
    entry={'order':sequence};slot=f'p{n:02}';env0=envelope();ensure(env0)
    if section=='edit':
        state='notebook' if n%2 else 'original';entry['state']=state
        for arm in sequence:
            outer('edit',batch,arm,state);entry[arm]={}
            for phase,shape in [('edit','transition'),('repeat','repeat')]:entry[arm][phase]=run(arm,'clock',state,shape,slot+'-'+phase)
        for arm in sequence:
            tag=name+'-'+slot+'-repeat-'+arm
            outer('run',batch,arm,'--',sys.executable,'-IB',worker,'oracle',arm,state,'repeat',tag)
            entry[arm]['behavior']=read(reports/tag/'behavior.json')
            reference='cold-edit' if state=='notebook' else 'original'
            gold=read(reports/('gate-v4-'+arm+'-'+reference)/'result.json')['behavior']
            assert entry[arm]['behavior']['sha256']==gold['sha256'] and entry[arm]['behavior']['listing_sha256']==gold['listing_sha256']
    else:
        for arm in sequence:entry[arm]=run(arm,'plain' if section=='plain' else 'clock','original','repeat',slot)
    env1=envelope();ensure(env1);assert oom(env0)==oom(env1)
    pairs.append(entry);put(d/(slot+'.json'),{'pair':entry,'before':env0,'after':env1})
    if n%8==0:print('Completed',n,'of',len(schedule),'pairs.',flush=True)
for arm in 'AB':trace(arm,'trace-after')
aa=read(reports/(name+'-trace-after-A')/'result.json');bb=read(reports/(name+'-trace-after-B')/'result.json')
if section!='edit':
    assert aa['native_args']==bb['native_args']==a0['native_args'] and aa['compiler_args']==bb['compiler_args']==a0['compiler_args']
after=envelope();ensure(after);assert oom(before)==oom(after)
put(d/'host-after.json',after);put(d/'pairs.json',pairs)
print('All declared pairs and post-run native work verified.',flush=True)

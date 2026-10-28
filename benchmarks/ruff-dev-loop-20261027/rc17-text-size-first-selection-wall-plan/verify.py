"""Recompute the registered trial from raw portable or on-host slot receipts after terminal."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import checks as g
import analysis


def one(root,block,position,arm,frozen,admission):
    path=root/f'{block:02d}-{position}-{arm}';rec=path/'ordinary';repeat=path/'follow'
    start=g.read(path/'start.json');w=g.read(path/'verified.json')
    assert (start['block'],start['slot'],start['arm'])==(block,position,arm)
    assert start['scored'] is (block>0) and start['admission']==admission
    assert start['cargo']==g.P['cargo'][arm] and start['cpu']==g.P['cpus']
    assert start['copy']=='cp -a --reflink=never' and start['independent_regular_files']==frozen['seed']['unique_files']>0
    assert start['seed']=={k:frozen['seed'][k] for k in ('digest','unique_files','unique_file_bytes','objects')}
    idle=start['idle']
    assert set(idle['per_cpu'])=={'cpu'+str(i) for i in g.P['cpus']}
    assert 1>=idle['average']>=g.P['quiet']['minimum_idle_all'] and min(idle['per_cpu'].values())>=g.P['quiet']['minimum_idle_each']
    for entry,extra in (('free_before_copy',frozen['seed']['unique_file_bytes']),('free_before_command',0)):
        m=start[entry]
        assert m['tmpfs_free']>g.P['minimum_tmpfs_free']+g.P['per_copy_extra_allowance']+extra
        assert m['available']>g.P['minimum_ram_available']+extra
    assert w['swap_after']==start['free_before_command']['counters']
    model=frozen['model'];reference=frozen['files']
    assert not (path/'fresh-physical-copy').exists()
    assert g.sha(path/'start.json')==w['start']
    assert g.ordinary(rec,model)=={k:w[k] for k in ('stdout','stderr')}
    first=g.read(rec/'files.json');g.validate_files(first,reference);g.listing(rec,model)
    assert g.sha(rec/'files.json')==w['ordinary_files']
    followed=g.events((repeat/'cargo.stdout').read_bytes());g.compare_model(followed,11)
    assert all(followed[k]==model[k] for k in ('typed','files','targets','diag'))
    assert followed['typed']==w['repeat_typed'] and followed['fresh']==w['repeat_fresh']
    assert g.sha(repeat/'cargo.stdout')==w['repeat_stdout'] and g.sha(repeat/'cargo.stderr')==w['repeat_stderr']
    q=g.read(repeat/'cargo.status.json')
    assert q['exit']==0 and q['argv'][:7]==['strace','-ff','-q','-s','1048576','-e','trace=execve']
    logical_phase='wall-admission-v1' if block==0 else 'wall-result-v1'
    destination=Path(g.P['remote_base'])/logical_phase/path.name/'follow/trace/exec'
    assert q['argv'][7:]==['-o',str(destination),*g.P['command'],'--message-format=json']
    inv=g.trace_inventory(repeat/'trace',set(model['targets'].values()))
    assert inv==g.read(repeat/'inventory.json') and g.sha(repeat/'inventory.json')==w['repeat_traces']
    assert not inv['tools'] and w['repeat_tools']==[] and g.read(repeat/'jobs.json')==[]
    second=g.read(repeat/'files.json');g.validate_files(second,reference);assert second==first
    assert g.sha(repeat/'files.json')==w['repeat_files']
    g.listing(repeat,model)
    if block==0:
        assert (rec/'unclocked-exit.json').is_file() and not (rec/'clock.json').exists()
        assert g.read(rec/'unclocked-exit.json')==dict(command=g.P['command'],exit=0)
        return None
    assert not (rec/'unclocked-exit.json').exists()
    t=g.read(rec/'clock.json');assert set(t)=={'start','stop','elapsed_ns','command','exit'}
    assert t['command']==g.P['command'] and t['exit']==0
    assert all(type(t[k]) is int for k in ('start','stop','elapsed_ns')) and 0<t['start']<t['stop'] and t['elapsed_ns']==t['stop']-t['start']
    return t


def verify_preflight(folder):
    assert not (folder/'failure.txt').exists()
    f=g.read(folder/'frozen.json');model=f['model'];g.compare_model(model,1)
    assert g.dig(model['typed'])==g.A['first']['roster'] and sorted(set(model['typed']))==model['typed']
    assert f['cpu']==g.P['cpus'] and f['state_fs']=='tmpfs' and f['tools']['arms']==g.P['cargo'] and f['tools']['sdk']==g.P['sdk']
    assert f['tools']['source']==g.P['tree'] and f['tools']['edited']==g.P['after']
    assert f['ci']==g.ci(g.read(folder/'ci-current.json'))
    reg=g.read(folder/'registration.json')
    assert reg['wall_sha256']==g.manifest(HERE) and g.REF.fullmatch(reg['wall_ref']) and reg['native_result_ref']==g.P['native_result_ref']
    assert reg['native_result_sha256']==g.P['native_result_sha256'] and reg['native_plan_ref']==g.P['native_source_ref']
    assert reg['native_plan_sha256']==g.P['native_registration']['sha256']
    assert g.read(folder/'post-condition.json')==dict(seed=f['seed'],tools=f['tools'],unscored=True,clocks=0)
    assert set(p.name for p in folder.iterdir() if p.is_dir())=={'00-1-B','00-2-C'}
    for i,arm in enumerate(g.P['unscored_preflight_order'],1):
        assert one(folder,0,i,arm,f,None) is None
    return dict(admitted=True,native_result_ref=g.P['native_result_ref'],wall_manifest=reg['wall_sha256'],
                frozen=g.sha(folder/'frozen.json'),ci=g.sha(folder/'ci-current.json'),registration=g.sha(folder/'registration.json'),
                preflight=[g.sha(folder/f'00-{i}-{a}/verified.json') for i,a in enumerate(g.P['unscored_preflight_order'],1)],
                physical_seed=f['seed'],test_builds=2,followups=2,clocks=0)


def all_slots(results,admit):
    terminal=g.read(results/'terminal.json');assert not (results/'failure.txt').exists() and terminal['phase']=='all_slots_finished' and terminal['slots']==48
    auth=verify_preflight(admit);assert auth==g.read(admit/'admission.json')
    f=g.read(admit/'frozen.json');h=g.sha(admit/'admission.json')
    assert terminal['admission']==h and terminal['seed']==f['seed'] and terminal['tools']==f['tools']
    reg=g.read(results/'registration.json');assert reg==g.read(admit/'registration.json')
    assert g.read(results/'ci-current.json')==g.read(admit/'ci-current.json')
    g.grant_valid(reg,g.read(results/'grant.json'),h)
    assert terminal['grant']==g.sha(results/'grant.json')
    want={f'{i:02d}-{j}-{a}' for i,o in enumerate(g.P['order'],1) for j,a in enumerate(o,1)}
    assert {q.name for q in results.iterdir() if q.is_dir()}==want
    rows=[];stop=0
    for i,order in enumerate(g.P['order'],1):
        ns={};clock_hashes={}
        for j,a in enumerate(order,1):
            t=one(results,i,j,a,f,h)
            assert stop<t['start']
            stop=t['stop'];ns[a]=t['stop']-t['start']
            clock_hashes[a]=g.sha(results/f'{i:02d}-{j}-{a}/ordinary/clock.json')
        rows.append(dict(block=i,order=order,ns=ns,clock_sha256=clock_hashes))
    return dict(rows=rows,statistics=analysis.evaluate(g.P,rows),verified_genuine_clocks=48,first_and_post_listing_processes=384,
                typed_fully_fresh_followups=48,physical_repeat_compilers_or_links=0,
                crossarm_raw_elf_comparisons=24*6,raw_harness_comparisons=24*4,
                complete_declared_paths=len(f['files']),native_result_ref=g.P['native_result_ref'])


def stopped(results):
    failure=results/'failure.txt'
    assert failure.is_file()
    clocks=[]
    for i,order in enumerate(g.P['order'],1):
        for j,arm in enumerate(order,1):
            at=results/f'{i:02d}-{j}-{arm}'
            if not at.is_dir():continue
            clk=at/'ordinary/clock.json';out=at/'ordinary';hashes={}
            for name in ('clock.json','stdout','stderr','files.json'):
                if (out/name).is_file():hashes[name]=g.sha(out/name)
            clocks.append(dict(block=i,slot=j,arm=arm,clock_present=clk.is_file(),raw_hashes=hashes,verified=(at/'verified.json').is_file()))
    return dict(status='stopped',failure_sha256=g.sha(failure),slots=clocks,statistics=None)


if __name__=='__main__':
    results,admit=map(Path,sys.argv[1:])
    if (results/'failure.txt').is_file():
        value=stopped(results)
    else:
        value=all_slots(results,admit)
        assert value==g.read(results/'result.json')
    print(json.dumps(value,sort_keys=True,indent=2))

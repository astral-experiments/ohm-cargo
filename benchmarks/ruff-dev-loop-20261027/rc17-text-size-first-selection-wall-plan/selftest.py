"""Positive full 48-slot raw and portable replay, deliberately bad gates, and a stopped study."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import checks as g
import portable
import verify as v


def fail(f):
    try:f()
    except (AssertionError,ValueError,FileNotFoundError):return 1
    raise AssertionError('invalid fixture passed')


def build_fixture(base):
    # No native compilation, linker, test binary or elapsed clock executes in this QA.
    raw_base=Path(g.P['remote_base'])/'logical/target'
    harness={t:str(raw_base/f'{t}-123456789abcdef0') for t in g.P['harnesses']}
    listings={t:(f'{t}: test\n\n1 test, 0 benchmarks\n') for t in harness}
    rows=[];names=[]
    for i in range(11):
        target=g.P['harnesses'][i] if i<4 else f'regular-{i}'
        path=harness[target] if i<4 else str(raw_base/target)
        paths=[path]
        if i>=6:paths.append(path+'.rmeta')
        names+=paths
        rows.append(dict(reason='compiler-artifact',package_id=f'pkg-{i}',manifest_path=f'/fixture/{i}/Cargo.toml',
                    target={'name':target,'kind':['test' if i<4 else 'lib']},profile={},features=[],filenames=paths,
                    executable=path if i<4 else None,fresh=True))
    data=b''.join((json.dumps(x)+'\n').encode() for x in [*rows,dict(reason='build-finished',success=True)])
    model=g.events(data);model['fresh']=1
    values={g.path_id(path):{'kind':'elf' if i<6 else 'archive','size':123+i,'sha256':g.dig(['data',i])} for i,path in enumerate(names)}
    assert len(values)==16
    g.P['declared_raw_sha256']=g.dig({k:s['sha256'] for k,s in values.items()})
    g.A['first']={**g.A['first'],'roster':model['roster'],'units':11,'diag':[],
        'elf':{k:s['sha256'] for k,s in values.items() if s['kind']=='elf'},
        'harness':{k:{'file':g.path_id(p),'sha256':values[g.path_id(p)]['sha256'],'listing':g.path_id(listings[k])} for k,p in harness.items()}}
    # Publish the test-only code-manifest anchor to a separate local directory.
    synthetic=base/'source';synthetic.mkdir();(synthetic/'w').write_text('fixture\n')
    (synthetic/'SHA256SUMS').write_text(g.sha(synthetic/'w')+'  w\n')
    v.HERE=synthetic;portable.HERE=synthetic
    digest=g.manifest(synthetic)
    seed=dict(digest='e'*64,objects=9,unique_files=7,unique_file_bytes=g.P['native_seed_bytes'],edited_library='d'*64,edited_library_path='f'*64)
    tools=dict(source=g.P['tree'],edited=g.P['after'],sdk=g.P['sdk'],arms=g.P['cargo'],rustup='b'*64,sdk_tree={'digest':'f'*64})
    ci=g.read(HERE/'ci-exact-heads.json')
    fr=dict(seed=seed,model=model,files=values,tools=tools,ci=g.ci(ci),cpu=g.P['cpus'],state_fs='tmpfs')
    reg=dict(wall_ref='9'*40,wall_sha256=digest,native_result_ref=g.P['native_result_ref'],native_result_sha256=g.P['native_result_sha256'],
             native_plan_ref=g.P['native_source_ref'],native_plan_sha256=g.P['native_registration']['sha256'])
    ad=base/'admission';result=base/'result';ad.mkdir();result.mkdir()
    for r in (ad,result):g.save(r/'registration.json',reg);g.save(r/'ci-current.json',ci)
    g.save(ad/'frozen.json',fr)
    def slot(r,i,j,arm,stamp,h=None):
        d=r/f'{i:02d}-{j}-{arm}';d.mkdir();rec=d/'ordinary';post=d/'follow';rec.mkdir();post.mkdir()
        idle={f'cpu{k}':.99 for k in g.P['cpus']};mem=dict(available=24*2**30,tmpfs_free=22*2**30,counters={'pswpin':0,'pswpout':0})
        g.save(d/'start.json',dict(block=i,slot=j,arm=arm,scored=i>0,admission=h,cargo=g.P['cargo'][arm],
               seed={k:seed[k] for k in ('digest','objects','unique_file_bytes','unique_files')},independent_regular_files=7,
               copy='cp -a --reflink=never',cpu=g.P['cpus'],idle={'average':.99,'per_cpu':idle},free_before_copy=mem,free_before_command=mem))
        (rec/'stdout').write_bytes(b'')
        (rec/'stderr').write_text('    Finished test profile\n'+''.join(f'  Executable tests/{k}.rs ({p})\n' for k,p in harness.items()))
        if i:
            # Synthetic integral nanoseconds exercise score reconstruction without touching a clock.
            ns=800 if arm=='C' else 1000
            g.save(rec/'clock.json',dict(command=g.P['command'],exit=0,start=stamp,stop=stamp+ns,elapsed_ns=ns))
        else:
            g.save(rec/'unclocked-exit.json',dict(command=g.P['command'],exit=0))
        for stage in (rec,post):
            g.save(stage/'files.json',values)
            for k,p in harness.items():
                g.save(stage/f'list-{k}.status.json',dict(argv=[p,'--list'],exit=0));(stage/f'list-{k}.stdout').write_text(listings[k]);(stage/f'list-{k}.stderr').touch()
        (post/'cargo.stdout').write_bytes(data);(post/'cargo.stderr').write_text('    Finished test profile\n')
        (post/'trace').mkdir();(post/'trace/exec.123').write_text('execve("/usr/bin/cargo", ["cargo", "+ohm", "test"], 0x12 /* 8 vars */) = 0\nexecve("/sdk/bin/cargo", ["cargo", "test"], 0x13 /* 8 vars */) = 0\n+++ exited with 0 +++\n')
        inv=g.trace_inventory(post/'trace',set(harness.values()));g.save(post/'inventory.json',inv);g.save(post/'jobs.json',[])
        remote=Path(g.P['remote_base'])/('wall-result-v1' if i else 'wall-admission-v1')/d.name/'follow/trace/exec'
        g.save(post/'cargo.status.json',dict(exit=0,argv=['strace','-ff','-q','-s','1048576','-e','trace=execve','-o',str(remote),*g.P['command'],'--message-format=json']))
        g.save(d/'verified.json',dict(start=g.sha(d/'start.json'),ordinary_files=g.sha(rec/'files.json'),stdout=g.sha(rec/'stdout'),stderr=g.sha(rec/'stderr'),
               repeat_files=g.sha(post/'files.json'),repeat_stdout=g.sha(post/'cargo.stdout'),repeat_stderr=g.sha(post/'cargo.stderr'),
               repeat_traces=g.sha(post/'inventory.json'),repeat_typed=model['typed'],repeat_fresh=11,repeat_tools=[],swap_after=mem['counters']))
    for j,a in enumerate(('B','C'),1):slot(ad,0,j,a,0)
    g.save(ad/'post-condition.json',dict(seed=seed,tools=tools,unscored=True,clocks=0));g.save(ad/'admission.json',v.verify_preflight(ad))
    h=g.sha(ad/'admission.json');grant=dict(action='score exact H2 24 fresh text-size pairs',admission_ref='b'*40,admission_sha256=h,native_result_ref=g.P['native_result_ref'],wall_ref=reg['wall_ref'],wall_sha256=digest)
    g.save(result/'grant.json',grant)
    for i,o in enumerate(g.P['order'],1):
        for j,a in enumerate(o,1):slot(result,i,j,a,10_000*i+2_000*j,h)
    g.save(result/'terminal.json',dict(phase='all_slots_finished',slots=48,admission=h,seed=seed,tools=tools,grant=g.sha(result/'grant.json')))
    g.save(result/'result.json',v.all_slots(result,ad))
    return ad,result


def run():
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp);ad,r=build_fixture(base);k=0
        packet=portable.collect(r,ad);checked=portable.check(packet)
        assert checked['raw_clocks']==48 and checked['statistics']['qualifies'] and checked['statistics']['favorable']==24
        # A digest alteration, clock arith/order, diagnostics, root authority, proof and real trace class must all fail.
        for mutation in (
            lambda z:z['rows'][0]['clock'].__setitem__('stop',19),
            lambda z:z['rows'][0].__setitem__('raw_clock_bytes','{}'),
            lambda z:z['rows'][1]['first_files'][next(iter(z['rows'][1]['first_files']))].__setitem__('sha256','0'*64),
            lambda z:z['rows'][2]['listings']['first'].__setitem__('main','edited'),
            lambda z:z['rows'][3]['repeat_typed'].__setitem__('fresh',10),
            lambda z:z['rows'][4]['physical']['tools'].append({'basename':'rustc'}),
            lambda z:z['rows'][5].__setitem__('stderr','warning: changed\n'),
            lambda z:z['rows'][6]['start'].__setitem__('arm','?'),
            lambda z:z['rows'].pop(),
            lambda z:z['grant'].__setitem__('admission_ref',z['registration']['native_result_ref']),
            lambda z:z['grant'].__setitem__('action','score before public qualification'),
            lambda z:z['frozen']['ci'][0]['checks'][0].__setitem__('conclusion','FAILURE'),
            lambda z:z['frozen']['tools']['arms'].__setitem__('B','deadbeef'),
        ):
            z=copy.deepcopy(packet);mutation(z);k+=fail(lambda:portable.check(z))
        one=r/f"01-1-{g.P['order'][0][0]}"
        tr=one/'follow/trace/exec.123';prior=tr.read_bytes()
        tr.write_bytes(prior+b'execve("/usr/bin/rustc", ["rustc", "-vV"], 0x15 /* 2 vars */) = 0\n+++ exited with 0 +++\n')
        k+=fail(lambda:v.all_slots(r,ad));tr.write_bytes(prior)
        f=one/'ordinary/clock.json';old=f.read_bytes();f.write_text('{"exit":0}\n');k+=fail(lambda:v.all_slots(r,ad));f.write_bytes(old)
        # Simulate a first-slot product rejection without reinterpreting its genuine-clock slot.
        stopped=base/'stopped';stopped.mkdir();(stopped/'failure.txt').write_text('synthetic novel raw output')
        new=stopped/one.name;new.mkdir();(new/'ordinary').mkdir()
        for q in ('clock.json','stdout','stderr','files.json'):(new/'ordinary'/q).write_bytes((one/'ordinary'/q).read_bytes())
        partial=portable.check(portable.collect(stopped,ad));assert partial['clocks']==1 and partial['statistics'] is None
        proof=base/'copy-leaves';proof.mkdir();(proof/'regular').write_bytes(b'x');cert,ids=g.tree(proof)
        (proof/'regular').write_bytes(b'y');assert g.tree(proof)[0]['digest']!=cert['digest']
        return dict(synthetic_only=True,physical_commands=0,full_slots_verified=48,independent_unclocked=2,
                    adverse_gates_rejected=k,partial_clock_retained=1,partial_effect_reported=False,
                    known_reduction_pct=round(checked['statistics']['paired_reduction_pct']),exact_assignments=checked['statistics']['assignments'])

if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True,indent=2))

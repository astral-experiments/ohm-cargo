from pathlib import Path
import collections,gzip,hashlib,json,sys
root=Path.home()/'.cache/ohm-233-position-qualified-20261027/finished-producer-first-selection-h2-v3';q=Path('/dev/shm/ohm-finished-producer-selection-h2-v3');work=Path.home()/'code/oss/ruff-ohm-whole-native-20261027';mode=sys.argv[1];assert mode in ('qualify','score')
load=lambda f:json.loads(f.read_bytes());sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
reg=load(root/'qualified.json');proto=root/('protocol-'+reg['runner'][:12]);plan=load(proto/'plan.json');assert reg['runner']==sha(proto/'SHA256SUMS') and sha(proto/'plan.json')==reg['plan']
assert (root/(mode+'.rc')).read_text().strip()=='0'
if mode=='qualify':assert not (root/'times.json').exists() and not (root/'times.part.json').exists()
else:assert (root/'finished.json').is_file() and len(load(root/'times.json'))==12
histories=['qualify'] if mode=='qualify' else ['block-%02d'%i for i in range(1,13)]
registry_dir,=[x.name for x in (Path('/mnt/devbox-scratch')/Path.home().name/'ohm-whole-skips-20261027/registry-home/registry/index').iterdir() if x.is_dir() and hashlib.sha256(x.name.encode()).hexdigest()=='85e1e016efd01b791bbc91cd0960c7f9de002a7f374d60c2a299adf9ebfa1381']
private_prefix=registry_dir.rsplit('-',1)[0];assert private_prefix and private_prefix!=registry_dir
def clean(s):
    if isinstance(s,dict):return {clean(k):clean(v) for k,v in s.items()}
    if isinstance(s,list):return [clean(t) for t in s]
    if isinstance(s,str):return s.replace(str(work),'$RUFF').replace(str(q),'$STATE').replace(str(root),'$RUN').replace(private_prefix,'$REGISTRY')
    return s
out={}
for name in histories:
    d=root/'histories'/name;h=load(d/'complete.json');env=load(d/'environment.json');n={};train={}
    assert h['seed']['seed_file_manifest']==sha(d/'snapshot.manifest.json.gz') and sha(d/'seed.json')==hashlib.sha256((json.dumps(h['seed'],sort_keys=True,indent=2)+'\n').encode()).hexdigest()
    for c in sorted(d.glob('seed-*')):
        p=load(c/'product.json');cmd=load(c/'command.json');assert sha(c/'stdout')==cmd['stdout'] and sha(c/'stderr')==cmd['stderr'] and cmd['elapsed_ns'] is None and cmd['traced'] is False
        train[c.name]=dict(cmd=cmd,units=p['units'],native=len(p['native']),exe=len(p['executables']),dirty=len(p['dirty']),ty_server=p['ty_server'],proof=sha(c/'product.json'))
    for arm in h['order']:
        rd=d/arm;r=load(rd/'complete.json');assert sha(rd/'complete.json')==h['arms'][arm];phases={}
        for ph in ('preselect-fresh','first','settled','restore','restored-settled'):
            sub=rd/ph;p=load(sub/'product.json');cmd=load(sub/'command.json');assert sha(sub/'stdout')==cmd['stdout'] and sha(sub/'stderr')==cmd['stderr'] and r['capture'][ph]==[sha(sub/'command.json'),sha(sub/'product.json')]
            msgs=[];for_tests=[]
            for l in (sub/'stdout').read_bytes().splitlines():
                a=json.loads(l)
                if a.get('reason')=='compiler-artifact':
                    msgs.append([a['package_id'],a['target']['name'],a['target']['kind'],a['profile']['test'],a['fresh']]);for_tests+=([a['profile']['test']] if a['executable'] else [])
            assert len(msgs)==p['units'] and sum(not s[-1] for s in msgs)==len(p['dirty'])
            v=dict(cmd=cmd,units=len(msgs),roster=p['roster'],exe=len(p['executables']),test_profile=sum(for_tests),ordinary=len(for_tests)-sum(for_tests),e2e=p['e2e'],ty_library=p['ty_server'],typed_dirty=[s for s in msgs if not s[-1]],raw_native=p['native'],diagnostics=p['diagnostics'],product_sha=sha(sub/'product.json'))
            if ph in ('first','restore'):
                v['ordinary_caller']=r['ordinary'][ph];v['native_caller_stdout']=sha(sub/'oracle.stdout');v['native_caller_stderr']=sha(sub/'oracle.stderr')
            if cmd['traced']:
                execs=load(sub/'physical.json')
                v['trace']=dict(compilers=[{k:w[k] for k in ('pid','start','end','source','test','crate','kind','signature','ty_extern')} for w in execs['typed_compilers']],linkers={k:z for k,z in execs['target_link_groups'].items()},full=execs['rustc'],total=execs['total'],wild=execs['actual_wild'],distinct_wild=execs['distinct_wild'],native=execs['native'],source=sha(sub/'physical.json'),trace_files=sha(sub/'original-trace-index.json'))
            phases[ph]=v
        n[arm]=dict(runner_rustc_image=plan['images']['driver'],cargo=r['cargo'],snapshot=r['snapshot'],validation=sha(rd/'complete.json'),phases=phases)
    out[name]=dict(order=h['order'],controls=h['ordinary'],seed=h['seed'],seed_commands=train,release=env['toolchain'],boot=env['boot'],media=env['media'],affinity=env['cpu'],arms=n,history_sha=sha(d/'complete.json'))
result=dict(mode=mode,runner=reg['runner'],plan=reg['plan'],qualification_sha=sha(root/'qualified.json'),histories=out,rows=load(root/'times.json') if mode=='score' else None,scored_calls=24 if mode=='score' else 0)
b=json.dumps(clean(result),sort_keys=True,separators=(',',':')).encode();assert all(t not in b for t in (private_prefix.encode(),str(Path.home()).encode(),b'/mnt/devbox',b'Authorization'));sys.stdout.buffer.write(gzip.compress(b,compresslevel=9,mtime=0))

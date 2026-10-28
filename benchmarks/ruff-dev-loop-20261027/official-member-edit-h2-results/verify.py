"""Replay the official-release member study, including native jobs, artifacts, caller bytes and order."""
from pathlib import Path
from collections import Counter
import ast,hashlib,json,re,subprocess,sys,tarfile
d=Path(__file__).resolve().parent;sha=lambda b:hashlib.sha256(b).hexdigest()
if (d/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=d,check=True)
with tarfile.open(d/'observations.tar.gz',mode='r:gz') as t:
    dd={m.name:t.extractfile(m).read() for m in t if m.isfile()};assert len(dd)==len(t.getmembers())
idx=json.loads(dd.pop('index.json'));assert set(idx)==set(dd)
for n,b in dd.items():
    raw,shown,l,s,count=idx[n];assert sha(b)==shown and len(b)==s and (count or (raw==shown and l==s))
J=lambda s:json.loads(dd[s]);B=lambda s:dd[s]
contracts=J('protocol/bound-states.json');inputs=J('protocol/inputs.json');plan=J('protocol/plan.json')
assert inputs['plan_sha']==idx['protocol/SHA256SUMS'][0] and inputs['worker']==idx['protocol/worker.py'][0]
assert (d/'bound-states.json').read_bytes()==B('protocol/bound-states.json') and (d/'inputs.json').read_bytes()==B('protocol/inputs.json')
assert inputs['design']=='35104a20849a992bdebec975676d4731dec60be2' and inputs['prior']=='ba75ed6bc040e13f80aba031a753ae618512b543' and inputs['qualification']=='c249f4c9bba1a4e03cf1c277fe9b281bfa075002'
assert contracts['clocks']==0 and J('results/complete.json')['inputs']==idx['protocol/inputs.json'][0]
mh={row.split('  ',1)[1]:row.split('  ',1)[0] for row in B('protocol/SHA256SUMS').decode().splitlines()}
for name in ('worker.py','member_clock.py','member_archive.py','member_archive_base.py','member_stats.py','analysis.py','bound-states.json','reader.rs','stub-original.pyi','stub-reversed.pyi','plan.json'):assert mh[name]==idx['protocol/'+name][0]
initial={v:J('native/official-'+v+'.json')['cold_and_three_unchanged'][-1] for v in ('16','17')}
for v in ('16','17'):
    assert inputs['native'][v]==idx['native/official-'+v+'.json'][0] and J('native/official-'+v+'.json')['archive']==inputs['archives'][v]==plan['releases'][v]
    assert len(initial[v]['products'])==5 and initial[v]['caller']['search_dirs']==210
expected={'original':'721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1','reversed':'0a9e5b203ef44812cd48a115f5fceafaffc2b0c0b013a1de927e2660865a10c5'}
for stage,b in expected.items():assert sha(B('protocol/stub-'+stage+'.pyi'))==b
callers=0;traceids=0;native=[]
def product(prefix,v,stage,action):
    global callers
    prefix+='/';a=J(prefix+'product.json');ar=J(prefix+'archives.json')
    assert (a['release'],a['stage'],a['action'])==(v,stage,action)
    assert a['raw'].keys()==a['typed'].keys()==a['before'].keys()==a['after'].keys()==initial[v]['products'].keys()
    assert ar.keys()=={n for n in a['raw'] if n.endswith('.rlib')} and len(ar)==2
    for n,act in a['raw'].items():
        if n in ar:
            entry=ar[n];assert entry['raw']==act and entry['typed']==a['typed'][n]==sha(json.dumps(entry['projection'],sort_keys=True,separators=(',',':')).encode())
            assert len(set(entry['original_names']))==len(entry['original_names'])==len(entry['projection']['objects'])
        else:assert act==a['typed'][n]
    assert len(a['offsets'])==2 and all(n in a['raw'] and val>=0 for n,val in a['offsets'].items())
    c=a['caller'];b=B(prefix+'reader.stdout')
    assert c['search_dirs']==210 and set(c['externs'])=={'ty_wasm','ty_vendored'} and len(c['binary'])==64 and c['bytes']==len(b)
    assert not B(prefix+'reader.stderr') and not B(prefix+'reader.compile.stderr') and not B(prefix+'reader.compile.stdout')
    assert b==B('protocol/stub-'+stage+'.pyi') and a['stub']==c['sha256']==sha(b)==expected[stage]
    if stage=='original':
        assert a['zip']==initial[v]['compressed_zip']['sha256'] and a['raw']['debug/libty_wasm.so']==initial[v]['products']['debug/libty_wasm.so']
    if action!='prime':
        bound=contracts['contracts'][v][stage];assert a['typed']==bound['typed'] and a['zip']==bound['zip'] and a['stub']==bound['stub']
    if action=='score':
        stamps=J(prefix+'repeat-stats.json');assert stamps['before'].keys()==stamps['after'].keys()==a['raw'].keys()
        if v=='17':assert stamps['before']==stamps['after']
    callers+=1;return a
def process(prefix,v,action):
    global traceids
    rs=[json.loads(line) for line in B(prefix+'/stdout').splitlines()];assert rs[-1]=={'reason':'build-finished','success':True}
    arts=[row for row in rs if row['reason']=='compiler-artifact'];assert len(arts)==304 and not any(x['profile']['test'] for x in arts)
    aa=J(prefix+'/product.json');assert sorted(x['target']['name'] for x in arts if not x['fresh'])==aa['dirty']
    physical=J(prefix+'/native-processes.json');traces=J(prefix+'/trace-files.json')
    assert traces and {n.rsplit('/',1)[1] for n in dd if n.startswith(prefix+'/trace/')}==set(traces)
    for n,digest in traces.items():assert idx[prefix+'/trace/'+n][0]==digest
    jobs=[]
    for pid,name,kind,exitcode,digest,path in [(z[0],z[1],z[2],z[3],z[4],z[5] if len(z)>5 else '') for z in physical['jobs']]:
        key=prefix+'/trace/exec.'+str(pid);lines=[s for s in B(key).splitlines() if b'execve(' in s and b'--crate-name' in s and ('"'+name+'"').encode() in s]
        assert exitcode==0 and lines and len(digest)==64
        if not idx[key][4]:assert any(sha(s)==digest for s in lines)
        jobs.append((name,kind))
    for l in physical['linkers']:
        key=prefix+'/trace/exec.'+str(l[0]);lines=[s for s in B(key).splitlines() if b'execve(' in s and l[5].encode() in s]
        assert l[3]==0 and lines and len(l[4])==64
        if not idx[key][4]:assert any(sha(s)==l[4] for s in lines)
    traceids+=len(traces)
    actual=dict(rustc=dict(Counter(b for a,b in jobs)),wild=sum(r[1] for r in physical['linkers']),system=sum(not r[1] for r in physical['linkers']),queries=len(physical['rustc_queries']))
    assert actual==physical['counts'] and len(physical['cargo'])==1
    if action!='prime':
        work=action=='edit' or v=='16';assert sorted(jobs)==([('ty_vendored','full'),('ty_wasm','full')] if work else [])
        assert actual['system']==actual['queries']==0 and actual['wild']==int(work) and len(aa['dirty'])==(6 if work else 0)
    native.append(dict(release=v,phase=prefix,fresh=304-len(aa['dirty']),**actual))
    cols=('package_id','manifest_path','target','profile','features','filenames','executable')
    return sorted(json.dumps({key:x[key] for key in cols},sort_keys=True) for x in arts)
assert B('protocol/exit')==b'0' and not B('protocol/stderr') and J('results/complete.json')['commands']==96
for v in ('16','17'):
    prefix='preflight/'+v+'/';binding=J(prefix+'bound/bound.json');assert binding['tool']==J('native/official-'+v+'.json')['tool'] and binding['archive']==inputs['archives'][v]
    first=None
    for tag,stage,action in [('prime','original','prime'),('initial','original','repeat'),('changed','reversed','edit'),('changed-repeat','reversed','repeat'),('restored','original','edit'),('restored-repeat','original','repeat')]:
        a=product(prefix+tag,v,stage,action);ro=process(prefix+tag,v,action);assert first is None or first==ro;first=ro
ledger={key:[] for key in ('edit','first_unchanged','edit_plus_first')};last=clocks=0
for i,order in enumerate(plan['pair_order'],1):
    stage='reversed' if i%2 else 'original';pair={}
    for v in order.split('-'):
        pref='sample/'+str(i).zfill(2)+'-'+v;times={}
        for phase in ('edit','repeat'):
            p=pref+'/'+phase
            c=J(p+'/clock.json');assert c['argv']==['cargo','+ohm','build','--locked','--offline','-j4'] and c['code']==0 and c['start']>last and c['ns']==c['stop']-c['start']>0
            assert not B(p+'/stdout') and b'Finished' in B(p+'/stderr') and b'Blocking waiting' not in B(p+'/stderr')
            last=c['stop'];clocks+=1;times[phase]=c['ns']
        assert times==J(pref+'/pair-clocks.json');pair[v]=times
        product(pref,v,stage,'score')
    for key,fun in [('edit',lambda a:a['edit']),('first_unchanged',lambda a:a['repeat']),('edit_plus_first',lambda a:sum(a.values()))]:
        ledger[key].append(dict(order='BC' if order=='16-17' else 'CB',direction=stage,b=fun(pair['16']),c=fun(pair['17'])))
assert ledger==J('results/ledger.json') and J('results/progress.json')['pairs']==24
for v in ('16','17'):
    product('final/'+v,v,'original','repeat');process('final/'+v,v,'repeat')
assert clocks==96 and callers==62 and len(native)==14
for f in ('analysis.py','member_stats.py'):assert sha((d/f).read_bytes())==mh[f]
sys.path.insert(0,str(d));from analysis import analyze
result=analyze(plan,ledger);assert result==J('results/result.json')
print(json.dumps(dict(clocks=clocks,external_callers=callers,trace_files=traceids,native=native,results=result),sort_keys=True))

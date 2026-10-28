"""Recompute every score from the native process clocks and complete artifact/caller receipts."""
from pathlib import Path
import gzip,hashlib,json,subprocess,sys,tarfile
p=Path(__file__).resolve().parent;sha=lambda b:hashlib.sha256(b).hexdigest()
if (p/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=p,check=True)
idx=json.loads(gzip.decompress((p/'inventory.json.gz').read_bytes()));seen=set();ar={}
for t in sorted(p.glob('*.tar.gz')):
    with tarfile.open(t,mode='r|*') as f:
        for ent in f:
            n=ent.name;assert ent.isfile() and n in idx and n not in seen;seen.add(n)
            data=f.extractfile(ent).read();o,r,ol,rl,count=idx[n]
            assert sha(data)==r and len(data)==rl and (count or (ol==rl and o==r));ar[n]=data
assert seen==idx.keys()
J=lambda s:json.loads(ar[s]);plan=J('protocol/plan.json');contract=J('protocol/contract.json');grant=J('protocol/grant.json');native=J('native-protocol/plan.json')
assert ar['protocol/exit']==b'0' and not ar['protocol/stderr'] and J('trial/complete.json')['sessions']==144
assert grant['plan_sha']==idx['protocol/SHA256SUMS'][0] and grant['contract_sha']==idx['protocol/contract.json'][0]
hashes={line.split('  ',1)[1]:line.split('  ',1)[0] for line in ar['protocol/SHA256SUMS'].decode().splitlines()}
for n in ('member_clock.py','member_stats.py','member_archive.py','member_archive_base.py','wall_members.py','plan.json','contract.json','cross.json'):assert idx['protocol/'+n][0]==hashes[n]
assert sha((p/'member_stats.py').read_bytes())==hashes['member_stats.py']
assert J('trial/complete.json')['grant']==idx['protocol/grant.json'][0] and all(len(grant[id])==40 for id in ('publication','native_publication'))
argv=['cargo','+ohm','build','--locked','--offline','-j4']
last=0;clocks=oracles=0;results={k:[] for k in ('edit','first_unchanged','edit_plus_first','project_unchanged')}
def clock(prefix):
    global last,clocks
    v=J(prefix+'/clock.json');assert v['argv']==argv and v['code']==0 and v['start']>last and v['ns']==v['stop']-v['start']>0
    assert not ar[prefix+'/stdout'] and b'Finished' in ar[prefix+'/stderr'] and b'Blocking waiting' not in ar[prefix+'/stderr']
    last=v['stop'];clocks+=1;return v['ns']
def oracle(prefix,arm,stage):
    global oracles
    out=J(prefix+'/verified.json');ref=contract[arm][stage];b=ar[prefix+'/reader.stdout'];c=out['caller']
    assert out['stage']==stage and out['typed']==ref['typed'] and out['zip'] in ref['zips']
    archives=J(prefix+'/archives.json')
    assert set(archives)=={n for n in out['outputs'] if n.endswith('.rlib')}
    for n,v in out['outputs'].items():
        if n in archives:
            a=archives[n];assert a['raw']==v and a['typed']==out['typed'][n]
            enc=json.dumps(a['projection'],sort_keys=True,separators=(',',':')).encode()
            assert sha(enc)==a['typed'] and len(a['original_names'])==len(a['projection']['objects'])
            assert len(a['original_names'])==len(set(a['original_names']))
        else:assert out['typed'][n]==v
    if arm=='Cproject-ty_project':assert out['outputs']==ref['files'][-1]
    assert len(c['binary'])==64 and c['search_dirs']>10 and len(c['externs'])==2
    assert not ar[prefix+'/reader.stderr'] and c['sha256']==sha(b)==native['stub'][stage] and b==ar['native-protocol/stub-'+stage+'.pyi']
    assert any(v.endswith('.rlib') for v in c['externs'].values()) and c['bytes']==len(b)
    oracles+=1
def stream(prefix,arm,stage,dirty):
    rs=[json.loads(x) for x in ar[prefix+'/stdout'].splitlines()]
    assert rs[-1]=={'reason':'build-finished','success':True}
    u=[r for r in rs if r['reason']=='compiler-artifact'];pkg=arm.split('-',1)[1]
    assert len(u)==native['units'][pkg] and all(not a['profile']['test'] for a in u)
    assert sorted(r['target']['name'] for r in u if not r['fresh'])==contract[arm][stage][dirty]
    cols=('package_id','manifest_path','target','profile','features','filenames','executable')
    assert sorted(json.dumps(v,sort_keys=True) for v in rs if v['reason']=='compiler-message')==contract[arm][stage]['diagnostics']
    return sorted(json.dumps({k:v[k] for k in cols},sort_keys=True) for v in u)
for arm in ('Bwasm-ty_wasm','Cwasm-ty_wasm','Bproject-ty_project','Cproject-ty_project'):
    pr='priming/'+arm+'/';fn='final/'+arm+'/'
    roster=stream(pr+'original',arm,'original','settled_dirty')
    oracle(pr+'original-check',arm,'original')
    if 'wasm' in arm:
        for stage in ('reversed','original'):
            assert stream(pr+stage+'-edit',arm,stage,'edited_dirty')==roster
            oracle(pr+stage+'-dirty-check',arm,stage)
            assert stream(pr+stage+'-repeat',arm,stage,'settled_dirty')==roster
            oracle(pr+stage+'-settled-check',arm,stage)
    assert stream(fn+'ordinary',arm,'original','settled_dirty')==roster;oracle(fn+'validation',arm,'original')
for work in ('wasm','project'):
    assert J('trial/'+work+'-progress.json')['count']==24
    for i,order in enumerate(plan['orders'][work],1):
        times={};stage=('reversed' if i%2 else 'original') if work=='wasm' else 'original'
        for a in order:
            prefix=work+'/'+f'{i:02}-{a}';case=a+work+'-ty_'+work
            times[a]=[clock(prefix+'/'+n) for n in (('edit','repeat') if work=='wasm' else ('build',))]
            oracle(prefix+'/validation',case,stage)
            if work=='wasm':
                stamp=J(prefix+'/first-repeat-stats.json')
                assert stamp['before'].keys()==stamp['after'].keys()==J(prefix+'/validation/verified.json')['outputs'].keys()
                if a=='C':assert stamp['before']==stamp['after']
        if work=='wasm':
            for name,fn in (('edit',lambda s:s[0]),('first_unchanged',lambda s:s[1]),('edit_plus_first',sum)):
                results[name].append(dict(order=order,direction=stage,b=fn(times['B']),c=fn(times['C'])))
        else:results['project_unchanged'].append(dict(order=order,direction=stage,b=times['B'][0],c=times['C'][0]))
assert clocks==144 and oracles==112 and results==J('trial/ledger.json')
sys.path.insert(0,str(p))
from member_stats import analyze
v=analyze(plan,results);assert v==J('trial/result.json')
print(json.dumps(dict(scored_commands=clocks,external_callers=oracles,results=v),sort_keys=True))

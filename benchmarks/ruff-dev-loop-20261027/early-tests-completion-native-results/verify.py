"""Independently join six workspace builds to actual compiler and linker execve records."""
from pathlib import Path
import ast
import collections
import gzip
import hashlib
import json
import re
import subprocess
import tarfile

p=Path(__file__).resolve().parent;sha=lambda b:hashlib.sha256(b).hexdigest()
if (p/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=p,check=True)
index=json.loads(gzip.decompress((p/'inventory.json.gz').read_bytes()));pool={}
for f in sorted(p.glob('*.tar.gz')):
    with tarfile.open(f) as tar:
        for member in tar:
            name=member.name;assert member.isfile() and name not in pool and name in index
            b=tar.extractfile(member).read();old,h,n,size,edit=index[name]
            assert sha(b)==h and len(b)==size and (edit>0 or (old==h and n==size))
            pool[name]=b
assert pool.keys()==index.keys()
def get(name):return json.loads(pool[name])
def bound(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
summary=json.loads((p/'native-summary.json').read_bytes());allr=get('product/complete.json')
assert summary['native_complete']==index['product/complete.json'][0]
assert allr['all_tests_executed_during_build']==0
assert all(get('product/selftest.json').values())
continued=get('product/continuation.json')
assert allr['continuation']==index['product/continuation.json'][0] and allr['selftest']==index['product/selftest.json'][0]
assert continued['original_failure']==index['prior/failure.txt'][0] and continued['previous_progress']==index['prior/progress.json'][0]
assert b"has no attribute 'index'" in pool['prior/failure.txt'] and len(continued['reused'])==5
for k,group in continued['reused'].items():
    assert all(index[k+'/'+file][0]==digest for file,digest in group.items())
roles={'A':'42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568',
       'B':'eea47e1d637a96d0d91dee825cf6a029d5123396ea1af1389aad187555fe2af3',
       'C':'46d8d787ab0e8f346f9fc5186e6a9bbad6ccd8c822c193deed51e8c9e9452afd'}
seed=get('seed/complete.json');assert seed['selected_units']==619 and seed['seed_rlib']['sha256']==seed['selected_rlib']['sha256']
for i in range(seed['seed_steps']):
    n='seed/seed-'+str(i)+'/';s=get(n+'product.json')
    assert s['ty_server']['sha256']==seed['seed_rlib']['sha256'] and not s['e2e'] and get(n+'command.json')['cargo']==roles['A']
    if i==seed['seed_steps']-1:assert not s['dirty']
for name in ('candidate/unit','candidate/integration','candidate/warm','parent-with-regression/integration'):
    n='behavior/'+name;rc=get(n+'.json');assert rc['stdout']==index[n+'.stdout'][0] and rc['stderr']==index[n+'.stderr'][0]
    if name.startswith('candidate'):assert rc['returncode']==0 and b'passed' in pool[n+'.stdout']
    else:
        logs=pool[n+'.stdout']+pool[n+'.stderr']
        assert rc['returncode']==101 and all(b in logs for b in (b'built-library',b'left: 2',b'right: 1'))

def records(buf):
    result=[];exit_=None;old=None
    for raw in buf.splitlines():
        ts,_,line=raw.partition(b' ');s,dot,fraction=ts.partition(b'.');ns=int(s)*10**9+int(fraction.ljust(9,b'0'))
        if m:=re.match(rb'^\+\+\+ exited with (\d+) \+\+\+$',line):exit_=[ns,int(m[1])]
        if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
            assert old is None;old=(ns,line.removesuffix(b'<unfinished ...>'));continue
        if m:=re.match(rb'^<\.\.\. (execve(?:at)?) resumed>(.*)$',line):
            assert old;ns,first=old;line=first+m[2];old=None
        if not line.startswith((b'execve(',b'execveat(')) or not re.search(rb'\)\s+= 0$',line):continue
        m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
        image=ast.literal_eval(m[1].decode());argv=ast.literal_eval(m[2].decode())
        result.append((ns,image,argv,sha(raw)))
    assert old is None
    return result,exit_
src='crates/ty_server/tests/e2e/main.rs'
for w in ('selection','cold'):
    views={}
    for a in 'ABC':
        k=w+'-'+a;name=k+'/';out=get(name+'product.json');raw=get(name+'physical.json');cmd=get(name+'command.json')
        views[a]=out;row=summary['rows'][k]
        assert cmd['exit']==0 and cmd['trace'] and cmd['cargo']==roles[a] and cmd['command']==['cargo','+ohm','test','--no-run','--workspace','--locked','--offline','-j8','--message-format=json']
        assert cmd['stdout']==index[name+'stdout'][0] and cmd['stderr']==index[name+'stderr'][0]
        assert allr['results'][w][a]['product']==index[name+'product.json'][0]
        lines=[json.loads(l) for l in pool[name+'stdout'].splitlines()]
        assert lines[-1]=={'reason':'build-finished','success':True}
        arts=[v for v in lines if v['reason']=='compiler-artifact'];exes={x['executable'] for x in arts if x['executable']}
        assert len(arts)==out['units']==619 and exes==set(out['executables']) and len(exes)==102 and len(out['native'])==110
        assert collections.Counter(bool(v['profile']['test']) for v in arts if v['executable'])=={True:84,False:18}
        assert row['test_list']==sha(pool[name+'test-list.stdout']) and b'inlay_hints::default_inlay_hints: test' in pool[name+'test-list.stdout']
        keyed=collections.defaultdict(list)
        for c in get(name+'calls.json'):keyed[c['pid']].append(c)
        requested={};ids=get(name+'original-trace-index.json');jobs=[];wild=[];primary=[];images=[]
        for pid,refs in keyed.items():
            fn=name+'exec/'+str(pid);assert ids[str(pid)]==[index[fn][0],index[fn][2]]
            actual,fin=records(pool[fn]);assert len(actual)==len(refs)
            for (ts,img,args,line),r in zip(actual,refs,strict=True):
                assert r['pid']==pid and r['time']==ts and r['image']==img and r['portable']==bound([img,args])
                if index[fn][-1]==0:assert r['raw_line']==line
                images.append(img)
                if Path(img).name=='rustc' and '--crate-name' in args and '--out-dir' in args and '--print=file-names' not in args:
                    cr=args[args.index('--crate-name')+1]
                    if cr in ('___','__'):continue
                    jobs.append((pid,ts,fin,cr,r['original']))
                    if '--test' in args and any(v==src or v.endswith('/'+src) for v in args):primary.append((pid,fin))
                elif Path(img).name=='ld.bfd' and 'wild-ld' in Path(img).parts:
                    assert '-o' in args and fin and fin[1]==0
                    wild.append((pid,args[args.index('-o')+1],fin))
        assert not exes.intersection(images)
        declared=[(v['pid'],v['start'],v['end'],v['crate'],v['signature']) for v in raw['typed_compilers']]
        assert sorted(declared)==sorted(jobs) and len(jobs)==raw['total'] and len(set(z[-1] for z in jobs))==raw['distinct']==row['distinct_rustc']
        assert len(wild)==raw['actual_wild']==row['wild'] and len({f for _,f,_ in wild})==row['distinct_wild']
        assert len(primary)==row['e2e'] and len([1 for pid,f,e in wild if f==out['e2e'][0]])==row['e2e_wild']
        assert sorted(i[0] for i in primary)==sorted(v['pid'] for v in raw['integration'][src])
        assert sha(pool[name+'test-list.stdout'])==allr['results'][w][a]['test_list']['stdout']
        if w=='selection':
            assert out['ty_server']['fresh'] and out['ty_server']['sha256']==seed['seed_rlib']['sha256'] and len(primary)==row['e2e_wild']==(1 if a=='C' else 2)
            assert all(end and end[1]==0 for pid,end in primary)
        else:assert len(out['dirty'])==619 and not out['ty_server']['fresh']
    for arm in 'BC':
        left=views['A'];right=views[arm];assert left['roster']==right['roster'] and left['diagnostics']==right['diagnostics']
        assert left['native'].keys()==right['native'].keys()
        differing={k for k in left['native'] if left['native'][k]!=right['native'][k]}
        comparison=allr['comparisons'][w+'/'+arm]
        assert 110-len(differing)==comparison['exact']==summary['comparisons'][w+'/'+arm]['exact']
        assert differing==comparison['allowed'].keys()
        for k,(x,y) in comparison['allowed'].items():
            assert x['bytes']==y['bytes'] and x['normalized']==y['normalized']
            assert all(v['rodata_entsize'] in (0,1,2,4,8,16,32,64,128,256) for v in (x,y))
            assert x['rodata_entsize']==y['rodata_entsize'] or min(x['rodata_entsize'],y['rodata_entsize'])==0
        assert summary['rows'][w+'-A']['test_list']==summary['rows'][w+'-'+arm]['test_list']
assert summary['native_compiles']['C']<summary['native_compiles']['B'] and summary['native_wild']['C']<summary['native_wild']['B']
assert summary['rows']['cold-B']['distinct_rustc']==summary['rows']['cold-C']['distinct_rustc'] and summary['rows']['cold-B']['distinct_wild']==summary['rows']['cold-C']['distinct_wild']
print(json.dumps(summary,sort_keys=True,indent=2))

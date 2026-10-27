"""Recompute the native compiler and linker counts from the successful execve history."""
from pathlib import Path
import ast
import collections
import gzip
import hashlib
import json
import re
import subprocess
import tarfile

here=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
if (here/'SHA256SUMS').is_file():
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=here,check=True)
idx=json.loads(gzip.decompress((here/'inventory.json.gz').read_bytes()))
data={}
for f in sorted(here.glob('*.tar.gz')):
    with tarfile.open(f) as tar:
        for m in tar:
            assert m.isfile() and m.name not in data and m.name in idx
            b=tar.extractfile(m).read()
            orig,digest,sz,portable,n=idx[m.name]
            assert sha(b)==digest and len(b)==portable and (n or (sz==portable and orig==digest))
            data[m.name]=b
assert data.keys()==idx.keys() and data['run/exit']==b'0' and not data['run/stderr']
fixture=json.loads((here/'fixture.json').read_bytes())
assert fixture['commit']=='93526150df078af7dd8fc4226cdcc469539d2001'
assert fixture['index']=='fc84f15ac7401cd9bdc362e4574c6d395529766c16be2e6b032ac47fa63d21cd'
get=lambda k:json.loads(data[k])
registered=get('run/plan.json')
ledger=get('run/complete.json');package=set(ledger)=={'spaced','unspaced'}
matched=set(ledger)=={'package','workspace'}
if matched:
    arm=get('run/binding.json');assert registered['arm']==get('run/sdk.json')['arm']==arm
    assert registered['runner']==idx['run/matched-native.py'][0]
    for g in ledger:
        v=get('run/'+g+'/sysroot.json')
        assert Path(v['probe']).name==('Ohm-SDK' if g=='package' else 'Ohm SDK')
        assert set(v['hashes'].values())=={arm[k] for k in ('cargo_sha','frontend','driver','wild')}
else:assert registered['source']==fixture['commit']
if package: assert registered['worker']==idx['run/capture.py'][0] and 'no speed claim' in registered['phase']
elif not matched:
    assert set(ledger)=={a+'-'+b for a in ('spaced','unspaced') for b in ('build','test')}
    assert all(registered['digests'][n]==idx['run/'+n][0] for n in ('capture.py','workspace.py'))
    if 'run/preflight.json' in data:
        orig=get('run/preflight.json')
        assert orig['code']==0 and orig['path']==orig['sysroot'] and Path(orig['sysroot']).name=='Ohm SDK'
        for g in ledger:
            sy=get('run/'+g+'/sysroot.json')
            assert sy['source']==fixture['commit'] and sy['cargo']==fixture['sdk']
            assert sy['spelling']==sy['sysroot'] and Path(sy['sysroot']).name==('Ohm SDK' if g.startswith('spaced-') else 'Ohm-SDK')
            assert Path(sy['logical_target']).name=='ruff-target'

def successes(b):
    pending=None
    for line in b.splitlines():
        if line.startswith((b'execve(',b'execveat(')) and line.endswith(b'<unfinished ...>'):
            assert pending is None
            pending=line[:-len(b'<unfinished ...>')]
            continue
        if m:=re.match(rb'^<\.\.\. execve(?:at)? resumed>(.*)$',line):
            assert pending is not None
            line=pending+m[1];pending=None
        if not line.startswith((b'execve(',b'execveat(')) or not re.search(rb'\)\s+= 0$',line):
            continue
        m=re.match(rb'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)
        assert m
        yield ast.literal_eval(m[1].decode()),ast.literal_eval(m[2].decode())
    assert pending is None

result={}
for group,rows in sorted(ledger.items()):
    assert len(rows)==(5 if package else 4)
    ended={}
    result[group]=[]
    for i,row in enumerate(rows):
        assert row['call']==i and row['tests_executed']==0
        k=group+'/call-'+str(i)+'/'
        rec=get(k+'command.json')
        if matched:
            assert rec['code']==0 and rec['arm']==arm
            cmd=rec['command']
        else:
            assert rec['status']==0 and rec['cargo']==fixture['sdk']
            cmd=rec['cmd']
        assert cmd[:2]==['cargo','+ohm'] and all(v in cmd for v in ['--locked','--offline','-j4','--message-format=json'])
        assert ('--no-run' in cmd)==(matched or package or group.endswith('-test'))
        assert rec['stdout']==idx[k+'stdout'][0] and rec['stderr']==idx[k+'stderr'][0]
        lines=[json.loads(b) for b in data[k+'stdout'].splitlines()]
        assert lines[-1]=={'reason':'build-finished','success':True}
        arts=[v for v in lines if v['reason']=='compiler-artifact']
        dirty=[n['target']['name'] for n in arts if not n['fresh']]
        exes={n['executable'] for n in arts if n['executable']}
        assert len(arts)==row['units'] and dirty==row['dirty']
        phys=get(k+'physical.json');names=collections.Counter();rusts=[];wild=[]
        for f,b in data.items():
            if not f.startswith(k+'trace/'):continue
            for image,args in successes(b):
                assert image not in exes
                name=Path(image).name;names[name]+=1
                if name=='rustc' and '--crate-name' in args and '--out-dir' in args and '--print=file-names' not in args:
                    crate=args[args.index('--crate-name')+1]
                    if crate in ('__','___'):continue
                    kind='link-only' if any(a in ('-Zlink-only','link-only') for a in args) else 'full'
                    rusts.append((Path(f).name,crate,kind))
                if name=='ld.bfd' and 'wild-ld' in Path(image).parts:
                    wild.append((Path(f).name,args[args.index('-o')+1]))
        assert names==phys['all_names'] and sorted(rusts)==sorted((v['trace'],v['crate'],v['kind']) for v in phys['jobs'])
        assert sorted(wild)==sorted((v['trace'],v['path']) for v in phys['wild'])
        counts=dict(collections.Counter(kind for _,_,kind in rusts))
        assert counts==row['jobs' if package else 'rustc' if matched else 'compilers'] and len(wild)==row['wild']
        proof=get(k+'proof.json')
        marks=[[(v['has_obs1'],v['status']) for v in h['fingerprints']] for h in proof]
        native=row['native'] if package or matched else get(k+'products.json')
        if package:
            assert set(native)==exes and len(arts)==303
            ron,=[n for n in arts if n['target']['name']=='ron']
            assert ron['fresh']==row['ron_fresh']
            assert marks==[[tuple(v) for v in h[1]] for h in row['observer']]
        elif matched:
            assert get(k+'product.json')==row and row['oracle']==idx[k+'list.stdout'][0]
            assert b': test' in data[k+'list.stdout'] and not data[k+'list.stderr']
            assert set(row['executables'])==exes and len(arts)==(303 if group=='package' else 619)
            assert len(exes)==(1 if group=='package' else 102) and len(native)==(4 if group=='package' else 110)
            assert marks==[[tuple(v) for v in h] for h in row['obs']]
        else:
            assert len(native)==row['native']==len(exes) and len(arts)>400
        assert all(re.fullmatch('[a-f0-9]{64}',h) for h in native.values())
        result[group].append(dict(i=i,units=len(arts),dirty=len(dirty),rustc=counts,wild=len(wild),
            executables=len(exes),native_files=len(native),same_native_as_previous=sum(ended.get(key)==h for key,h in native.items()) if i else None,
            observers=[x[1] for m in marks for x in m],compiled=[v for _,v,_ in rusts] if i else None))
        ended=native
    for j,h in enumerate(proof):
        dep=group+'/final/dep-'+str(j)
        assert idx[dep][0]==h['sha256'] and b'ohm-foreign-span-bytes' in data[dep]
        for l,v in enumerate(h['fingerprints']):
            stored=get(group+'/final/tail-'+str(j)+'-'+str(l)+'.json')
            trailer=bytes.fromhex(stored['last41'])
            assert stored['original']==v['raw'] and stored['bytes']==v['n']
            assert len(trailer)==41 and trailer[:4]==b'OBS1' and trailer[-33]==v['status']
if package:
    assert all(v['rustc']=={'full':2,'link-only':1} and v['wild']==1 and v['dirty']==6 and v['observers']==[0] for v in result['spaced'][1:])
    assert all(not v['rustc'] and not v['wild'] and not v['dirty'] and v['observers']==[1] for v in result['unspaced'][2:])
elif 'run/preflight.json' in data:
    assert all(v['units']==619 and v['executables']==102 for g in ('spaced-test','unspaced-test') for v in result[g])
    assert all(v['rustc']=={'full':1,'link-only':50} and v['wild']==50 and v['dirty']==56 for v in result['spaced-test'][1:])
    assert result['unspaced-test'][1]['rustc']=={'full':1,'link-only':50} and result['unspaced-test'][1]['wild']==50
    assert all(not v['dirty'] and not v['rustc'] and not v['wild'] for v in result['unspaced-test'][2:])
    assert all(not v['dirty'] and not v['rustc'] and not v['wild'] for g in ('spaced-build','unspaced-build') for v in result[g][1:])
print(json.dumps(result,sort_keys=True))

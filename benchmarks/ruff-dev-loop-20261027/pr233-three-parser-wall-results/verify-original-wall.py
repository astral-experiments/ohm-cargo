"""Reproduce the paired results on every raw Cargo message and every physical process control."""
from collections import Counter
import hashlib, json, subprocess, sys, tarfile, tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here))
from time_analyze import analyze
def sha(data):return hashlib.sha256(data).hexdigest()
def read(p):return json.loads(p.read_bytes())
def as_digest(v):return sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode())
p=read(here/'time-plan.json');packed=read(here/'export-receipt.json')
rawparts=sorted(here.glob('cargo-evidence.zst.part-*'));assert rawparts
summary={};checks={};elapsed={};phase_count=Counter();seen=set();current=None
refs=None
def verify_case(rid,record,files):
    pp=rid.split('/');phase=pp[0]
    if phase=='timed':
        sched=p['sequence'][int(pp[1])-1];arm=pp[2];mode=sched['mode'];label=sched['edit']+'-'+sched['direction'];assert arm in sched['arms']
    elif phase in ('pre','post'):
        _,mode,edit,direction,arm=pp;label=edit+'-'+direction
    else:
        assert phase=='settle';_,mode,arm,_=pp;label='original-baseline'
    ref=refs['/'.join((mode,arm,label))]
    assert record['source_view']==ref['source_view'] and record['reference']==ref['original_receipt']
    normalized=ref['release_roster']
    cols=('package_id','manifest_path','target','profile','features','filenames','executable')
    marks={'B':'v2-c95b8d54c8a62c02-all-native-all','C':'v2-8b4edd970c9a0df5-all-native-all'}
    prefix='/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/native-target/debug/build/workspaces/2a0346c599559020/'
    for which in ('first','immediate'):
        if which not in record:assert phase=='settle' and which=='immediate';continue
        r=record[which];f=files[which]
        assert r['stdout_sha256']==sha(f['stdout']) and r['stderr_sha256']==sha(f['stderr']) and r['status']==0 and b'Blocking waiting' not in f['stderr']
        assert all(min(r[k].values())>=25*2**30 for k in ('before_free','after_free'))
        rows=[json.loads(line) for line in f['stdout'].splitlines() if line]
        assert rows[-1]=={'reason':'build-finished','success':True}
        arts=[a for a in rows if a.get('reason')=='compiler-artifact'];msgs=sorted(json.dumps([x['package_id'],x['target']['name'],x['message']],sort_keys=True) for x in rows if x.get('reason')=='compiler-message')
        dirty=sorted(a['target']['name'] for a in arts if not a['fresh'])
        assert r['unit_count']==len(arts)==ref['units'] and as_digest(msgs)==ref['messages'] and dirty==r['dirty']
        exes={a['executable'] for a in arts if a['executable']};assert len(exes)==r['exe_count']==ref['exes']
        unit=[{k:a[k] for k in cols} for a in arts]
        assert as_digest(sorted(json.dumps(v,sort_keys=True) for v in unit))==ref['roster']
        mapped=0
        for v in unit:
            paths=[]
            for x in [*v['filenames'],v['executable']]:
                if isinstance(x,str) and x.startswith(prefix):
                    scope,_,rest=x[len(prefix):].partition('/');assert scope==marks[arm] and rest;x=prefix+'<registered-compiler-release>/'+rest;mapped+=1
                paths.append(x)
            v['filenames']=paths[:-1];v['executable']=paths[-1]
        assert {'sha256':as_digest(sorted(json.dumps(v,sort_keys=True) for v in unit)),'units':len(arts),'mapped_output_path_count':mapped}==normalized
        assert r['elf_count']==len(ref['elf']) and r['cli']==as_digest([ref['old_cli'],ref['novel_cli']])
        assert r['structure']==as_digest(dict(units=ref['units'],roster=ref['roster'],release_roster=ref['release_roster'],messages=ref['messages'],elf=ref['elf'],exes=ref['exes']))
        assert r['command']==['cargo','+ohm',mode,*(['--no-run'] if mode=='test' else []),'--locked','--offline','--message-format=json']
        if r['traced']:
            jobs=[];native={'cc':0,'collect2':0,'wild':0}; seen_cargo=False
            for pid,digest,im,av,ah in json.loads(f['programs.json']):
                assert len(digest)==len(ah)==64 and pid.startswith('exec.') and im not in exes
                if av is not None:assert sha(json.dumps(av,separators=(',',':')).encode())==ah
                img=Path(im)
                if im in ('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/frozen-toolchain/bin/cargo','/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/rustup/toolchains/ohm/bin/cargo'):seen_cargo=True
                if img.name=='rustc' and av and '--crate-name' in av:
                    crate=av[av.index('--crate-name')+1]
                    if crate not in ('___','__') and '--print=file-names' not in av:jobs.append([crate,'link-only' if any(x in ('-Zlink-only','link-only') for x in av) else 'full'])
                if img.name in ('cc','gcc','x86_64-linux-gnu-gcc','x86_64-linux-gnu-gcc-13','gcc-13'):native['cc']+=1
                if img.name=='collect2':native['collect2']+=1
                if img.name=='ld.bfd' and img.parent.name=='wild-ld':native['wild']+=1
            assert seen_cargo and {'native':native,'jobs':sorted(jobs)}==r['native']
            if which=='immediate':assert not jobs and not any(native.values()) and not dirty
            elif phase!='settle':assert r['native']==ref['native'] and dirty==ref['dirty']
        else:
            assert phase=='timed' and which=='first' and r['native'] is None and 'programs.json' not in f and dirty==ref['dirty']
            elapsed[int(pp[1]),arm]=r['elapsed_ns'];assert r['elapsed_ns']>0
        phase_count[phase,which]+=1
with tempfile.TemporaryDirectory() as temp:
    packed_path=Path(temp)/'packed.zst'
    digest=hashlib.sha256()
    with packed_path.open('wb') as out:
        for part in rawparts:
            b=part.read_bytes();digest.update(b);out.write(b)
    assert digest.hexdigest()==packed['sha256'] and packed_path.stat().st_size==packed['bytes']
    proc=subprocess.Popen(['zstd','-q','-d','--stdout',str(packed_path)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=proc.stdout,mode='r|') as stream:
        for member in stream:
            name=member.name;assert member.isfile() and name not in seen;seen.add(name)
            if name.startswith('summary/'):
                n=Path(name).stem;assert current is None;summary[n]=json.loads(stream.extractfile(member).read());refs=summary.get('references');continue
            bits=name.split('/')
            if bits[-1]=='witness.json':
                if current is not None:verify_case(current,record,files)
                current='/'.join(bits[:-1]);record=json.loads(stream.extractfile(member).read());files={}
                checks[current]=sha((json.dumps(record,indent=2,sort_keys=True)+'\n').encode())
            else:
                assert current=='/'.join(bits[:-2])
                files.setdefault(bits[-2],{})[bits[-1]]=stream.extractfile(member).read()
        assert current;verify_case(current,record,files)
    assert proc.wait()==0 and len(seen)==packed['selected_files']
observations=summary['observations']
assert phase_count['timed','first']==phase_count['timed','immediate']==192 and phase_count['pre','first']==phase_count['post','first']==24
assert len(observations)==96
for i,row in enumerate(observations,1):
    assert {a:elapsed[i,a] for a in 'BC'}==row['elapsed_ns'] and {a:checks[f'timed/{i:03d}/{a}'] for a in 'BC'}==row['proofs']
for n,entry in summary['prepared']['pre_controls'].items():assert checks[n]==entry['proof_sha256']
for n,entry in summary['post-controls'].items():assert checks[n]==entry['proof_sha256']
results=analyze(p,observations)
assert results==summary['results']==read(here/'results.json') and observations==read(here/'observations.json') and packed['untraced']==192
print('Verified all 192 ordinary Cargo wall times, all immediate zero-job traces, 48 physical controls, and six balanced multiplicity-adjusted comparisons.')

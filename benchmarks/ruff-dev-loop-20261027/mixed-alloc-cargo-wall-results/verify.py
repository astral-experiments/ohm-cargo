"""Check each ordinary clock, native trace, Cargo roster, post-control, and registered test."""
from collections import Counter
from pathlib import Path
import ast
import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tarfile
import tempfile

root=Path(__file__).resolve().parent
if (root/'SHA256SUMS').exists():
    subprocess.run(['sha256sum','--quiet','-c','SHA256SUMS'],cwd=root,check=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
ledger=json.loads(gzip.decompress((root/'inventory.json.gz').read_bytes()))
members={}
for f in sorted(root.glob('*.tar.gz')):
    with tarfile.open(f) as tar:
        for m in tar:
            assert m.isfile() and m.name not in members and m.name in ledger
            if m.name in members or Path(m.name).is_absolute() or '..' in Path(m.name).parts:raise ValueError(m.name)
            b=tar.extractfile(m).read();d,h,n,size,replacements=ledger[m.name]
            assert sha(b)==h and len(b)==size and (replacements>0 or (d,h,n)==(h,d,size)),m.name
            members[m.name]=b
assert members.keys()==ledger.keys()
def obj(n):return json.loads(members[n])
plan=obj('protocol/plan.json');obs=obj('observations.json');stats=obj('statistics.json')
assert sha(members['protocol/SHA256SUMS'])=='65228149a67c682f3744091a3a4c406b6da14780f7a4a3646e2cebf9e82ef0c7'
for line in members['protocol/SHA256SUMS'].decode().splitlines():
    h,n=line.split('  ',1);assert sha(members['protocol/'+n])==h
assert sha(members['protocol/analyze.py'])==plan['analyzer']
with tempfile.TemporaryDirectory() as t:
    t=Path(t)
    for n,b in [('analyze.py',members['protocol/analyze.py']),('obs.json',members['observations.json']),('plan.json',members['protocol/plan.json'])]:(t/n).write_bytes(b)
    repeat=json.loads(subprocess.check_output([sys.executable,'-IB',str(t/'analyze.py'),str(t/'obs.json'),str(t/'plan.json')]))
assert repeat==stats and all(r['exact_assignments']==63_504 for r in stats.values())
assert members['protocol/outer-exit']==b'0' and members['protocol/outer-stderr']==b''
assert obj('complete.json')['plan']==sha(members['protocol/SHA256SUMS'])
assert obj('complete.json')['scored_commands']==obj('complete.json')['fresh_followups']==80
assert obj('build-retention.json')['contents']['files']>1000 and len(obj('build-retention.json')['contents']['sha256'])==64
def actual(stream):
    calls=[];pending=None
    for line in stream.decode(errors='replace').splitlines():
        if line.startswith(('execve(','execveat(')) and line.endswith('<unfinished ...>'):
            assert pending is None;pending=line.removesuffix('<unfinished ...>');continue
        if m:=re.match(r'^<\.\.\. (execve(?:at)?) resumed>(.*)$',line):
            assert pending is not None;line=pending+m[2];pending=None
        if not line.startswith(('execve(','execveat(')) or not re.search(r'\)\s+= 0$',line):continue
        m=re.match(r'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
        calls.append([ast.literal_eval(m[1]),[ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"',m[2])]])
    assert pending is None
    return calls
assert set(obs)==set(stats)=={'build','test'}
witness={};c=Counter();declared=set()
for mode in ('build','test'):
    assert obs[mode]==obj('ledger-'+mode+'.json') and len(obs[mode])==20
    want=plan['units'][mode];els,exs=(15,6) if mode=='build' else (110,102)
    for arm in 'BC':
        assert len(obj('clone-'+mode+'-'+arm+'.json'))>=want
        phases={'entry':'detailed-fresh'}
        for side in ('pre','post'):
            for direction in ('edit','restore'):
                tag=side+'-'+direction;phases[tag]='edit';phases[tag+'-fresh']='detailed-fresh'
                b=obj('control-'+mode+'-'+arm+'-'+tag+'.json');assert b['raw_equal']+len(b['allowed_elf_differences'])==els
                assert set(b['mixed'])=={'ruff_wasm','ty_wasm'}
        for i,row in enumerate(obs[mode]):
            tag=f"{i+1:02d}-{row['direction']}";phases[tag]='ordinary';phases[tag+'-fresh']='fresh'
        for tag,phase in phases.items():
            prefix=f'receipts/{mode}/{arm}/{tag}/';r=obj(prefix+'receipt.json');inv=obj(prefix+'invocation.json')
            declared.add(prefix+'receipt.json');c[phase]+=1
            assert r['status']==0 and r['phase']==phase and r['mode']==mode and r['arm']==arm
            assert all(r[k]==val for k,val in inv.items()) and r['elapsed_ns']>0
            assert r['actual_cargo']==plan['cargo'][arm] and r['actual_driver']==plan['compiler']
            assert r['command']==['cargo','+ohm',mode]+(['--no-run'] if mode=='test' else [])+['--locked','--offline']
            err=members[prefix+'stderr'];out=members[prefix+'stdout']
            assert b'Finished' in err and b'Blocking waiting' not in err
            if phase=='ordinary':
                i=int(tag[:2])-1
                assert obs[mode][i]['ns'][arm]==r['elapsed_ns'] and not out and any('ruff_python_parser' in s for s in r['terminal_work'])
                if arm=='C':assert r['recipe_before']==r['recipe_after'] and len(r['recipe_after'])==2
                continue
            native=f'native-trace/{mode}/{arm}/{tag}/';calls=obj(native+'successful-execs.json');inventory=obj(native+'inventory.json')
            verified=[]
            for pid,(h,n,executed) in sorted(inventory.items()):
                if executed:
                    entry=native+pid;assert ledger[entry][0]==h and ledger[entry][2]==n
                    verified.extend([[pid,img,args] for img,args in actual(members[entry])])
            assert verified==calls and [[pid,img] for pid,img,args in calls]==r['processes']['images']
            rows=[json.loads(l) for l in out.splitlines() if l];assert rows[-1]=={'reason':'build-finished','success':True}
            arts=[v for v in rows if v['reason']=='compiler-artifact'];assert len(arts)==want==r['unit_count']
            exe={v['executable'] for v in arts if v['executable']};assert len(exe)==exs and not exe.intersection(img for pid,img,args in calls)
            assert sum(v['fresh'] for v in arts)==r['fresh_units']
            p=r['processes'];jobs=Counter(j['kind'] for j in p['jobs']);links=[len(p['native'][k]) for k in ('cc','collect2','wild')]
            if phase!='edit':
                assert r['fresh_units']==want and not jobs and links==[0,0,0]
            else:
                baseline=3 if mode=='build' else 6;relink=6 if mode=='build' else 62;wild=8 if mode=='build' else 67
                assert jobs==Counter({'full':baseline-(2 if arm=='C' else 0),'checked-native':2 if arm=='C' else 0,'link-only':relink})
                assert links==[wild]*3
                if arm=='C':assert sorted(j['crate'] for j in p['jobs'] if j['kind']=='checked-native')==['ruff_wasm','ty_wasm']
            state=r['state'];view=[r['product'][v] for v in ('structural_roster','messages','diagnostics')]
            key=(mode,arm,state);assert witness.setdefault(key,view)==view
            if 'elf' in r['product']:assert len(r['product']['elf'])==els
assert {n for n in members if n.startswith('receipts/') and n.endswith('/receipt.json')}==declared
assert c=={'ordinary':80,'fresh':80,'detailed-fresh':20,'edit':16}
print(json.dumps(dict(clocks=80,fresh=80,traced_pre_and_post=16,traced_entry_and_controls=20,registered=stats,passes_all=all(r['passes'] for r in stats.values())),indent=2,sort_keys=True))

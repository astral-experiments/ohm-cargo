"""Verify reported native, process, runtime, and Cargo execution controls from the exported raw data."""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
SHA = lambda data: hashlib.sha256(data).hexdigest()
SHIPPED = '4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3'
PARENT = '0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322'
PARENT_DEV = '45207a4096dad4461f68445741488a273111a1811ae56e2a75a2bb7a2bf98786'
FIXED = '5e37d20fa6f79cfcc5a273fb7a95eb19f7239ba750c8a3d1aeaedb90171cdd36'
RUSTC = '7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c'
ELF17 = '77ddb54ca7f3b3c530fccf864c3fe7a8440e6e9a180a8b0eff806d3a6f4ffe91'
ELF29 = 'd95864fcc3df2d1233befdb17c934a8d5b9fb296f106c23ee42e839cb6cc0fe4'
EXEC = re.compile(r'^execve\(("(?:\\.|[^"])*"), (\[.*?\]), [^)]*\)\s+= 0$')

def archive(kind):
    with tarfile.open(ROOT / f'{kind}-receipts.tar.gz') as t:
        assert all(i.isfile() and not i.name.startswith('/') and '..' not in Path(i.name).parts for i in t)
        files={i.name:t.extractfile(i).read() for i in t}; assert len(files)==len(t.getmembers())
    ledger=json.loads(files.pop('PHYSICAL-SHA256.json'))
    assert ledger['entries']=={k:[len(b),SHA(b)] for k,b in files.items()}
    return files

def actual_rustcs(files, base):
    for f,raw in files.items():
        if not f.startswith(base+'exec.'):
            continue
        for line in raw.decode().splitlines():
            m=EXEC.match(line)
            if m and Path(ast.literal_eval(m[1])).name=='rustc':
                argv=ast.literal_eval(m[2]); idx=argv.index('--crate-name') if '--crate-name' in argv else None
                if idx is not None and argv[idx+1]!='___':
                    yield (argv[idx+1],argv,SHA(line.encode()))

def ordinary(kind, expected_arms):
    files=archive(kind); total=0
    assert {k.split('/')[0] for k in files if k.endswith('/complete.json')}==set(expected_arms)
    for arm,cargo in expected_arms.items():
        corrected=arm=='removed-default'; result=json.loads(files[arm+'/complete.json'])
        assert len(result)==10
        for name,r in result.items():
            total+=1; prefix=arm+'/'+name+'/'
            assert json.loads(files[prefix+'result.json'])==r and r['cargo']==cargo and r['rustc']==RUSTC
            calls=list(actual_rustcs(files,prefix)); assert sorted((a,b) for a,b,_ in calls)==sorted((e['crate'],e['argv']) for e in r['rustcs'])
            c_expected=29 if name=='empty-edited' or corrected and name in ('c-edit','c-edit-again','reader-edit','reader-edit-again') else 17
            assert r['value']==c_expected and r['executable']=={17:ELF17,29:ELF29}[c_expected]
            for _,av,_ in calls:
                assert ('-Zcache-proc-macros' in av) != corrected
                assert '-Zlink-only' not in av and ('-Z','link-only') not in list(zip(av,av[1:]))
            if name=='c-edit': assert sorted(crate for crate,av,s in calls)==['native_derive','plain_reader']
            if name=='reader-edit': assert [crate for crate,av,s in calls]==['plain_reader']
            if name.endswith('-again'): assert not calls and all(r['fresh'].values())
            assert r['raw_deps'] and not any(flag for _,flag in r['raw_deps'].values())
        before,edit=result['prime'],result['c-edit']; assert before['src_reader']==edit['src_reader'] and before['src_c']!=edit['src_c']
        assert set(before['object'].values()).isdisjoint(edit['object'].values()) and before['native_macro']!=edit['native_macro']
        assert {s for s in before['native_sections'] if before['native_sections'][s]!=edit['native_sections'][s]}=={'.text'}
    return total

def observers(kind, expected):
    files=archive(kind); total=0; s=set(); coverage={}
    for path,raw in files.items():
        if not path.endswith('/complete.json'):continue
        a=path.split('/'); arm,stamp=a[0],a[2]; assert arm in expected; s.add((arm,stamp)); rec=json.loads(raw); rows=rec['rows']
        assert rec['old_token_before_replacement']==17 and rec['compiled']['17']['bytes']==rec['compiled']['29']['bytes']
        assert rec['compiled']['17']['source']==rec['compiled']['29']['source']
        assert {k for k,(l,r) in rec['sections'].items() if l!=r}=={'.text'}
        assert rec['old']['inode']!=rec['replacement']['inode'] and any(x['exe']=='rustc' and 'r-xp' in x['permissions'] for x in rec['observed_old_maps'])
        assert (rec['old']['mtime_ns']==rec['replacement']['mtime_ns'])==(stamp=='dso-preserved')
        for phase,r in rows.items():
            total+=1; prefix='/'.join(a[:-1])+'/'+phase+'/'; assert json.loads(files[prefix+'result.json'])==r
            assert r['exit']==0 and r['compiler']==RUSTC and not r['unit_fresh']
            calls=list(actual_rustcs(files,prefix)); assert sorted(x['argv_sha256'] for x in r['native'] if x['process']=='rustc')==sorted(s for _,_,s in calls)
            assert any(k=='hold_direct' and '-Zlink-only' not in av and ('-Z','link-only') not in list(zip(av,av[1:])) for k,av,_ in calls)
            assert r['trace_sha256']=={k.removeprefix(prefix):SHA(b) for k,b in files.items() if k.startswith(prefix+'exec.')}
            good=phase=='clean' or (phase not in ('initial',) and phase in expected[arm])
            exp=17 if phase=='initial' else (29 if good else 17)
            assert r['value']==exp and r['join']==(17 if phase=='initial' else 29)
            assert r['derive_calls']==(['17'] if phase=='initial' else (['29'] if good else []))
        coverage[arm]=sorted(rows)
    assert s=={(a,t) for a in expected for t in ('dso-current','dso-preserved')}
    return total,coverage

n=ordinary('ordinary',{'shipping':SHIPPED,'pr261':PARENT,'removed-default':FIXED})+ordinary('explicit',{'matched-parent':PARENT_DEV,'candidate-explicit-cache':FIXED})
en=['repeat','again'];good_en=['repeat','again','upgrade','up-again']
e,a=observers('early',{'known-default':[],'new-default':[],'new-explicit-no-cache':en,'candidate-known':en,'candidate-first':['again'],'upgrade-first':['again'],'upgrade-known-already-stale':['up-again']})
f,b=observers('fixed',{'candidate-known':en,'candidate-first':en,'upgrade-first':en,'upgrade-known-already-stale':['upgrade','up-again']})
print(json.dumps({'ordinary_native_cargo_commands':n,'earlier_observer_commands':e,'fixed_observer_commands':f,'all_native_executions':n+e+f,'ordinary_elf_17':ELF17,'ordinary_elf_29':ELF29},sort_keys=True))

suite=archive('suite'); checked=json.loads(suite['checked.json']); assert [(r['arm'],r['group'],r['rc']) for r in checked]==[('parent','native',101),('v2','native',0),('v2','rustflags',101)]
assert len({r['suite'] for r in checked})==1
for r in checked:
    assert r['actual_cargo']=={'parent':PARENT_DEV,'v2':FIXED}[r['arm']]
    assert SHA(suite[f"{r['arm']}-{r['group']}.log"])==r['log_sha256']
for arm in ['parent','v2']:
    calls={}; argv=[]
    for f,raw in suite.items():
        if not f.startswith(arm+'-native-exec.'): continue
        for line in raw.decode().splitlines():
            m=EXEC.match(line)
            if not m: continue
            n=Path(ast.literal_eval(m[1])).name; av=ast.literal_eval(m[2]);calls[n]=calls.get(n,0)+1
            if n=='cc' and 'value.c' in av: argv.append(av)
    assert calls['cargo']==calls['reader']==calls['build-script-build']==len(argv)==2
ansi=re.compile(r'\x1b\[[0-9;]*m');log=ansi.sub('',suite['parent-native.log'].decode());assert '- 29' in log and '+ 17' in log and '1 failed' in log
assert b'1 passed; 0 failed' in suite['v2-native.log']
print('The checked-in native test observed the old 17 on the parent and the expected 29 on the revised default.')

context=archive('context')
pinned=json.loads(context['pinned/complete.json'])
assert b'd37229159e545bbdec917dd7efdf5d26da40d2bc' in context['pinned/rustc-vv']
assert b'4d75695b40cf14e7e7122fb8c87a66942ee05ba309c26d644a0a217b98d96456' in context['pinned/sdk.sha']
assert b'53bc74814a82d724fe69fe789682fd5ea425035ddc330c71a0000577f33ecf78' in context['pinned/sdk.sha']
assert len(set(r['suite'] for r in pinned.values()))==1 and pinned['fixed']['suite']==checked[0]['suite']
assert [(pinned[a]['cargo'],pinned[a]['exit']) for a in ['parent','fixed']]==[(PARENT_DEV,101),(FIXED,0)]
for arm,r in pinned.items():
    assert SHA(context[f'pinned/{arm}.log'])==r['log_sha256']
    children={'cc':0,'reader':0}
    for path,raw in context.items():
        if not path.startswith('pinned/'+arm+'-exec.'):continue
        for line in raw.decode().splitlines():
            m=EXEC.match(line)
            if not m:continue
            key=Path(ast.literal_eval(m[1])).name;av=ast.literal_eval(m[2])
            if key=='reader' or key=='cc' and 'value.c' in av:children[key]+=1
    assert children=={'cc':2,'reader':2}
assert '- 29' in ansi.sub('',context['pinned/parent.log'].decode()) and '+ 17' in ansi.sub('',context['pinned/parent.log'].decode())
assert b'1 passed; 0 failed' in context['pinned/fixed.log']
module=json.loads(context['module/complete.json'])
assert module['repo-feature-normal']['module_rc']==0 and module['source-parent-official']['module_rc']==101
parentlog=context['module/source-parent-official-suite.out'];candidate_log=suite['v2-rustflags.log']
failures=lambda b:set(re.findall(rb'^test (rustflags::\S+) .* FAILED$',b,re.M))
assert len(failures(parentlog))==7 and failures(parentlog)==failures(candidate_log)
assert b'43 passed; 7 failed' in parentlog and b'44 passed; 7 failed' in candidate_log
assert b'51 passed; 0 failed' in context['module/repo-feature-normal-suite.out']
print('The pinned -9 independently reproduced 17 on the parent and 29 on the revised default. The feature-on parent and candidate shared seven named failures. The regular module passed 51/51.')

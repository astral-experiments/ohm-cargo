"""Recompute every native migration verdict, typed Cargo row and output-selected linker off-line."""
import argparse
import ast
import collections
import gzip
import hashlib
import json
import re
import tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HEX=re.compile(r'[0-9a-f]{64}')
def sha(b):return hashlib.sha256(b).hexdigest()
def argv_events(data):
    """Successful physical execve records, including individual per-PID strace files."""
    got=[]
    for line in data.decode().splitlines():
        assert '<unfinished ...>' not in line and ' resumed>' not in line
        if not re.search(r'\)\s+= 0$',line):continue
        m=re.fullmatch(r'(?:\d+\s+)?execve\(("(?:\\.|[^"\\])*"), (\[.*\]), (.*)\)\s+= 0',line)
        assert m,line[:120]
        image,args=ast.literal_eval(m[1]),ast.literal_eval(m[2])
        assert args and all(isinstance(x,str) for x in args)
        got.append((image,args))
    return got
def opt(args,name):return args[args.index(name)+1] if name in args else None
def messages(raw):
    records=[json.loads(line) for line in raw.splitlines() if line.startswith(b'{')]
    assert records and records[-1]['reason']=='build-finished'
    return records
def jobs(events):
    rust=[];links=[]
    for image,args in events:
        exe=Path(image).name
        if exe=='rustc' and opt(args,'--crate-name') not in (None,'___'):
            rust.append((opt(args,'--crate-name'), 'link-only' in args or '-Zlink-only' in args))
        if image.endswith('/wild-ld/ld.bfd') or image in ('/usr/bin/ld','/usr/bin/ld.bfd') or exe in ('rust-lld','ld.lld'):
            target=opt(args,'-o')
            if target:links.append((image,Path(target).name))
    return sorted(rust),sorted(links)
def step(state,implicit):
    if state=='absent':return 0,0,17
    if state=='malformed':return 101,None,None
    assert state=='valid'
    return (0,83,None) if implicit else (0,0,29)
def oldresult():return 0,0,17
def identity_tuples(items):return {(r['name'],tuple(r['kind']),r['test'],r['sha']) for r in items}
def audit(ledger,stream):
    official=json.loads((ROOT/'official-19.json').read_bytes())
    sources=json.loads((ROOT/'development-subjects.json').read_bytes())
    phys=ledger['physically_reopened'];assert ledger['schema']=='native-migration-1'
    assert set(ledger['histories'])=={
        *{f'implicit-{salt}-{arm}-{state}' for salt in ('salted','unsalted') for arm in ('same-image','same-stamp') for state in ('valid','malformed')},
        *{f'official19-{arm}-{state}' for arm in ('same-image','salted','unsalted') for state in ('valid','malformed')},
        'official19-staged-release','implicit-empty-valid','implicit-empty-malformed','declared-empty-valid','declared-empty-malformed'}
    assert ledger['asset']['sha256']==official['archive']=='ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812' and ledger['asset']['bytes']==359628600
    assert all(phys['official19'][k]['sha256']==official['images'][k] for k in ('cargo','rustc','wild','driver'))
    keys={'old-same-stamp':'predecessor_unsafe_dev','real-link-unsalted':'predecessor_real_link_dev','real-link-salted':'current_dev'}
    assert all(phys[k]['cargo']['sha256']==sources[v] for k,v in keys.items())
    assert len({phys[k]['driver']['sha256'] for k in keys})==len({phys[k]['rustc']['sha256'] for k in keys})==1
    assert len({phys[k]['cargo']['sha256'] for k in keys})==3
    assert all(v['wild']['sha256']==sources['wild'] for v in phys.values())
    assert sources['source_commit']=='2447f7f4eacb4fdf499899929f08d0de19abb4d0'
    assert sources['prior_head']=='fd872c053bb1e9dcde722cf90a05a7cb8335dd32'
    assert ledger['streams'].keys()==stream.keys()
    for fn,meta in ledger['streams'].items():
        b=stream[fn];assert len(b)==meta['bytes'] and sha(b)==meta['sha256'] and HEX.fullmatch(meta['raw_sha256']) and meta['raw_bytes']>=0
        assert not fn.startswith('/') and '..' not in Path(fn).parts
    counters=collections.Counter();clean={};first={};phasevals={}
    for label,case in ledger['histories'].items():
        implicit=label.startswith('implicit-');held='held' in case['kind'];counts=[]
        if held:
            assert len(case['rows'])==8
            old=case['old'];new=case['new']
            expected_old='old-same-stamp' if implicit else 'official19'
            if 'same-image' in label:expected_new=expected_old
            elif '-unsalted-' in label:expected_new='real-link-unsalted'
            else:expected_new='real-link-salted'
            for side,key in [(old,expected_old),(new,expected_new)]:
                for tool in ['cargo','rustc']:
                    assert side[tool]['sha256']==phys[key][tool]['sha256']
                    assert re.search(r'\ncommit-hash: [a-f0-9]{40}\n',side[tool]['version'])
            if implicit:
                assert old['cargo']['version']==new['cargo']['version']
                assert old['rustc']==new['rustc']
            else:
                assert all(old[k]['version']==official['versions'][k] for k in old)
                if 'same-image' not in label:
                    assert old['rustc']!=new['rustc'] and old['cargo']['version']!=new['cargo']['version']
            snap=case['unchanged_target_and_source_snapshot']
            assert snap['files']>50 and snap['bytes']>1_000_000 and HEX.fullmatch(snap['sha256'])
        fs={k[len(label+'/fixture-source/'):]:sha(v) for k,v in stream.items() if k.startswith(label+'/fixture-source/')}
        assert ('provider/build.rs' in fs)!=implicit and 'app/tests/probe.rs' in fs
        for idx,row in enumerate(case['rows']):
            ph=row['phase'];base=f'{label}/{ph}/';st=row['state'];sources_at=dict(fs);sources_at.pop('Cargo.lock',None)
            expr=f'1 + {row["lib"]}' if implicit else f'middle::base() + {row["lib"]}'
            sources_at['app/src/lib.rs']=sha(f'pub fn value() -> i32 {{ {expr} }}\n'.encode())
            if not implicit:sources_at['provider/state']=sha((st+'\n').encode())
            assert row['sources']==sources_at,(label,ph)
            if held:
                if idx<3 or 'same-image' in label or (implicit and '-unsalted-' in label and idx in (3,4)):
                    verdict=oldresult()
                else:verdict=step(st,implicit)
            elif case['kind']=='declared-stock':verdict=oldresult()
            else:verdict=step(st,implicit)
            assert (row['cargo'],row.get('native_exit'),row.get('value'))==verdict,(label,ph,verdict)
            paths={}
            for sub in ('test','prepare'):
                pref=base+sub+'/'
                if pref+'exec.log' not in stream:assert sub=='prepare';continue
                counters[sub]+=1;rec=messages(stream[pref+'stdout']);physical=argv_events(stream[pref+'exec.log'])
                assert rec[-1]['success']==(sub=='prepare' or row['cargo']==0)
                actual_scripts=[e for e in rec if e['reason']=='build-script-executed']
                if implicit:assert not actual_scripts
                else:
                    ss,=actual_scripts;out=ss['out_dir']
                    assert ss['linked_paths']==['native='+out+'/early','native='+out+'/fallback']
                    assert ss['linked_libs']==[];paths[sub]=out
                comp,links=jobs(physical)
                wrappers=[a for exe,a in physical if Path(exe).name=='cargo' and '+ohm' in a]
                assert len(wrappers)==1, (label,ph,sub)
                if sub=='prepare':
                    assert '-p' in wrappers[0] and 'provider' in wrappers[0] and 'build' in wrappers[0]
                    assert any(Path(k).name=='ar' for k,_ in physical) and any(re.fullmatch(r'build[-_]script[-_]build(?:-[a-f0-9]{16})?',Path(k).name) for k,_ in physical)
                    continue
                assert '-p' in wrappers[0] and 'app' in wrappers[0] and '--test' in wrappers[0] and 'probe' in wrappers[0]
                real=[(exe,out) for exe,out in links if re.fullmatch(r'probe-[a-f0-9]{16}',out)]
                assert all(exe.endswith('/wild-ld/ld.bfd') for exe,_ in real)
                expected_attempts = 2 if case['kind'].startswith('empty') and row['cargo']==101 else 1
                assert len(real) <= expected_attempts,(label,ph,real)
                if row['cargo']==101:
                    assert len(real)==expected_attempts and comp.count(('probe',False))+comp.count(('probe',True))==expected_attempts
                    assert any('linking with' in e['message']['message'] for e in rec if e['reason']=='compiler-message')
                    assert pref+'native.stdout' not in stream
                else:
                    arte,=[r for r in rec if r['reason']=='compiler-artifact' and r['target']['name']=='probe' and r['executable']]
                    assert arte['fresh']==row['fresh'] and Path(arte['executable']).name==row['elf']
                    native=stream[pref+'native.stdout'];err=stream[pref+'native.stderr'];vals=re.findall(rb'native-choice=(\d+)',native)
                    if row['native_exit']==0:assert vals==[str(row['value']).encode()] and b'1 passed; 0 failed' in native
                    elif row['native_exit']==83:assert not native and not err
                    else:raise AssertionError((label,ph))
                    assert HEX.fullmatch(row['hash'])
                if held and idx<3:
                    assert bool(real)==(idx==0)
                    if idx==2:assert not comp
                if held and idx in (3,4):
                    miss='same-image' in label or (implicit and '-unsalted-' in label)
                    if miss:assert not comp and not real and row['fresh']
                    elif idx==3 or row['cargo']==101:
                        assert len(real)==1 and any(name=='probe' for name,_ in comp)
                    else:assert not comp and not real and row['fresh']
                    if idx==3:first[label]=row
                if case['kind'].startswith('empty'):
                    assert len(real)==expected_attempts and comp.count(('probe',False))==expected_attempts
                    if row['cargo']==0:
                        entry=case['physically_reopened_empty_elf'];body=ledger['empty_elfs'][row['hash']]
                        assert entry=={'sha256':row['hash'],'bytes':body['bytes']} and bytes.fromhex(body['elf_header_hex'])[:4]==b'\x7fELF'
                        clean[label]=row['hash']
            if 'prepare' in paths: assert paths['prepare']==paths['test']
            counts.append((row['cargo'],row.get('native_exit'),row.get('value')))
        if held:assert len({r['hash'] for r in case['rows'][:3]})==1
        phasevals[label]=counts
    assert clean['implicit-empty-valid']==first['implicit-salted-same-stamp-valid']['hash']=='543fcfd64d6c6e055518a32c54d503981980b3390a0d524dcd4105e6ddb943f0'
    assert clean['declared-empty-valid']==first['official19-salted-valid']['hash']=='2d82c3c78e55c0f794b1157d3a3236976872fba5f623d7144770593d0c8313d3'
    assert clean['implicit-empty-valid'] != first['implicit-unsalted-same-stamp-valid']['hash']
    assert len(ledger['scope_commands'])==12 and stream['scope/old-version']==stream['scope/new-version']
    assert sha(stream['scope/new-version'])==ledger['scope_old_new_version_sha256']
    groups={}
    for label,case in ledger['scope_commands'].items():
        pref=f'scope/{label}/';ref=case['receipt'];rec=messages(stream[pref+'stdout'])
        assert ref['stderr_sha']==ledger['streams'][pref+'stderr']['raw_sha256'] and ref['stdout_sha']==ledger['streams'][pref+'stdout']['raw_sha256']
        assert rec[-1]['success'] and ref['rustc']==sources['rustc']
        assert ref['cargo']==(sources['current_dev'] if label.startswith('new') else sources['predecessor_unsafe_dev'])
        assert len(ref['units'])==8
        actual=sorted(((j['target']['name'],j['target']['kind'],j['profile']['test'],j['fresh']) for j in rec if j['reason']=='compiler-artifact'), key=str)
        typed=sorted(((j['name'],j['kind'],j['test'],j['fresh']) for j in ref['units']), key=str)
        assert actual==typed
        kernels=[k for k in stream if k.startswith(pref+'exec.')];assert kernels
        physical=[entry for f in kernels for entry in argv_events(stream[f])]
        comp,links=jobs(physical)
        assert comp==sorted((r['crate'],r['link_only']) for r in ref['compiler'])
        if '-defaults-off-' in label:
            assert sorted(out for _,out in links)==sorted(r['output'] for r in ref['linker'])
            assert all(Path(exe).name in ('ld.lld','rust-lld') for exe,_ in links)
            if links:
                assert collections.Counter(Path(exe).name for exe,_ in links)=={'ld.lld':7,'rust-lld':7}
                assert len({r['exe'] for r in ref['linker']})==2
        else:
            assert sorted(out for exe,out in links if exe.endswith('/wild-ld/ld.bfd'))==sorted(g['output'] for g in ref['linker'])
            assert all(g['exe']==sources['wild'] for g in ref['linker'])
        if label.startswith('new') or label.startswith('old') and label.endswith('-2'):
            fresh=[j['name'] for j in ref['units'] if not j['fresh']]
            if label=='new-native-1':
                assert fresh==['library_integration'] and comp==[('library_integration',False)] and len(links)==1
            else:assert not fresh and not comp and not links
        groups[label]=identity_tuples(ref['units'])
    for mode in ['native','check','defaults-off']:
        assert groups['old-'+mode+'-2']==groups['new-'+mode+'-1']==groups['new-'+mode+'-2']
    smoke=json.loads((ROOT/'replay-smoke.json').read_bytes());assert smoke.keys()=={'implicit','declared'}
    for role,key,old in [('implicit','implicit-salted-same-stamp-malformed','old-same-stamp'),('declared','official19-salted-valid','official19')]:
        item=smoke[role];row=first[key]
        assert item['exit']==0 and item['first']=={k:row.get(k) for k in ('cargo','hash','native_exit','value')}
        assert item['old']['cargo']['sha256']==phys[old]['cargo']['sha256']
        assert item['new']['cargo']['sha256']==phys['real-link-salted']['cargo']['sha256']
        assert item['stderr_sha256']==sha(b'') and item['snapshot']['files']==ledger['histories'][key]['unchanged_target_and_source_snapshot']['files']
        assert HEX.fullmatch(item['raw_result_sha256'])
    return counters

def load():
    ledger=json.loads(gzip.decompress((ROOT/'acquisition.json.gz').read_bytes()))
    data={}
    with tarfile.open(ROOT/'streams.tar.gz','r:gz') as arch:
        for member in arch:
            assert member.isfile() and member.name not in data
            data[member.name]=arch.extractfile(member).read()
    return ledger,data

def verify():
    l,s=load();c=audit(l,s)
    print(f"{len(l['histories'])} histories, {c['test']} primary commands, {c['prepare']} staged provider commands, 12 target-scope commands, {len(s)} bound raw streams and {len(l['empty_elfs'])} independently reopened empty ELFs.")

def selftest():
    l,s=load()
    original=l['histories']['implicit-salted-same-stamp-valid']['rows'][3]
    for key,value in [('hash','0'*64),('native_exit',0),('sources',{}),('fresh',True)]:
        old=original[key];original[key]=value
        try:audit(l,s)
        except AssertionError:pass
        else:raise RuntimeError('accepted an altered salted record: '+key)
        original[key]=old
    label='new-native-1';reference=l['scope_commands'][label]['receipt']
    before=reference['compiler'];reference['compiler']=[]
    try:audit(l,s)
    except AssertionError:pass
    else:raise RuntimeError('accepted an unrecorded target recompile')
    reference['compiler']=before
    print('Rejected changed ELF, native exit, source identity, freshness and removed physical compiler.')

if __name__=='__main__':
    command=argparse.ArgumentParser();command.add_argument('--selftest',action='store_true');args=command.parse_args()
    verify()
    if args.selftest:selftest()

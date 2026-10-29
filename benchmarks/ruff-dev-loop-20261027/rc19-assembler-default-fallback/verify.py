#!/usr/bin/env python3
"""Audit the complete normalized streams and the distinctions between changed, empty and fresh."""
import ast,base64,gzip,hashlib,json,re,sys
from pathlib import Path
from collections import Counter

root=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def j(f):return json.loads(f.read_bytes())
def unzip(f):return json.loads(gzip.decompress(f.read_bytes()))
def sort(rows):return sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))
def native(rows,lines,blobs,tool):
    exe={};parent={};seen=[];opens=[]
    for k,reference in rows.items():
        if not k.startswith('trace.'):continue
        pid=int(k.split('.')[-1])
        for b in blobs[reference[2]].splitlines():
            l=b.decode();h=sha(b)
            if l.startswith('execve(') and l.endswith('= 0'):
                m=re.search(r'^execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[)',l)
                if m is None:continue
                image=Path(ast.literal_eval(m[1])).name;argv=ast.literal_eval(m[2])
                unit=argv[argv.index('--crate-name')+1] if '--crate-name' in argv else None
                exe[pid]=(image,unit)
                if image=='rustc' and unit in ('assembler_reader','reader'):
                    is_link='-Zlink-only' in argv or 'link-only' in argv
                    seen.append((pid,'rustc',unit,is_link,any(x.startswith('incremental=') for x in argv),h))
                if image in ('ld','ld.bfd','ld.lld','rust-lld') and '-o'in argv and Path(argv[argv.index('-o')+1]).name.startswith('reader-'):
                    seen.append((pid,'linker',image,h))
            if re.search(r'\b(?:clone3?|vfork|fork)\(|<\.\.\. (?:clone3?|vfork|fork) resumed>',l):
                m=re.search(r'=\s*(\d+)\s*$',l)
                if m:parent[int(m[1])]=pid
            if l.startswith(('open(','openat(','openat2(')) and '"/run-case/fixture/payload.bin"' in l:
                opens.append((pid, bool(re.search(r'=\s*\d+\s*$',l)), 'ENOENT' in l,h))
    expected=[]
    for x in tool['processes']:
        if x['type']=='rustc':expected.append((x['pid'],'rustc',x['unit'],x['link_only'],x['incremental'],lines[x['line']]))
        else:expected.append((x['pid'],'linker',x['name'],lines[x['line']]))
    assert sorted(seen)==sorted(expected)
    traced=[]
    for pid,ok,missing,h in opens:
        p=pid;visited=set();ancestry=[]
        while p and p not in visited:
            visited.add(p)
            if p in exe:ancestry.append(exe[p])
            p=parent.get(p)
        name=next((u for e,u in ancestry if e=='rustc' and u),'')
        traced.append((pid,ok,missing,h,name,ancestry[0][0] if ancestry else ''))
    expected=[(x['tid'],x['open_successful'],x['missing'],lines[x['line']],x['nearest_compiler'],x['nearest_executable']) for x in tool['asset_opens']]
    assert sorted(traced)==sorted(expected)
    return [x[3] for x in seen if x[1:3]==('rustc','reader')],traced

def fixture_values(script):
    tree=ast.parse((root/script).read_text())
    return {n.targets[0].id:n.value.value for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and isinstance(n.value,ast.Constant)}

def check_phase(ph,unsafe,used,record,raw,lines,blobs,imgs):
    pre={'01','02','10'};new={'03','04','05'}
    expected_status=101 if ph in {'08','09'} or (ph=='07' and not unsafe) else 0
    assert record['status']==expected_status and record['expected_incremental']==0 and record['compiler_incremental_directories']==[]
    assert record['empty']==(ph in {'01','04','08'}) and record['asset']==(sha(bytes([17])) if ph in pre else sha(bytes([29])) if ph in new else None)
    source=b'#[inline(never)]\npub fn observed(x: u8) -> u8 { x ^ 5 }\n';edit=source.replace(b'x ^ 5',b'x ^ 9') if used else source+b'pub struct AddedByPublicEdit;\n'
    assert record['source']==sha(edit if ph in new else source)
    stdout=blobs[raw['stdout'][2]];stderr=blobs[raw['stderr'][2]];messages=list(map(json.loads,stdout.splitlines()))
    assert messages[-1]=={'reason':'build-finished','success':not expected_status}
    assert not any(m['reason']=='build-script-executed' for m in messages)
    assert [[m['target']['name'],m['fresh']] for m in messages if m['reason']=='compiler-artifact']==record['typed']
    modes,opens=native(raw,lines,blobs,record)
    assert all(x['exe']==imgs['rustc'] for x in record['processes'] if x['type']=='rustc')
    assert all(x['exe']==imgs['wild'] for x in record['processes'] if x.get('name')=='ld.bfd')
    if ph=='02':assert record['processes']==[] and record['typed']==[['assembler_reader',True],['reader',True]]
    elif unsafe and ph in {'03','07'}:assert modes==[True] and not opens
    else:
        assert modes and not any(modes) and opens
        assert all(x[1]==(expected_status==0) and x[2]==(expected_status==101) and x[4]=='reader' for x in opens)
    assert record['diagnostic_mentions_incbin']==(b'payload.bin' in stdout+stderr)==bool(expected_status)
    if ph!='02':assert record['depinfo'] and all(not v['mentions_payload'] and v['mentions_reader_source'] for v in record['depinfo'].values())
    if not expected_status:
        assert re.fullmatch('[0-9a-f]{64}',record['elf'])
        rv=10 if used and ph in new else 6 if used else 0
        nv=17 if ph in pre or (unsafe and ph=='03') else 29
        value,=re.findall(rb'native-value=(\d+),rust-value=(\d+)',blobs[raw['test.stdout'][2]])
        assert tuple(map(int,value))==(record['native'],record['rust'])==(nv,rv) and b'1 passed' in blobs[raw['test.stdout'][2]]
    else:assert 'test.stdout' not in raw and 'elf' not in record

def checked_sources(ds):
    j=unzip(root/'checked-sources.json.gz');assert sha((root/'regression.rs').read_bytes())==j['source_excerpt_sha256']
    expected='freshness::dependency_edit_reassembles_native_targets_by_default'
    for arm,rc,body,product,calls in [('red',101,'link:integration','parent',3),('green',0,' ... ok','candidate',4)]:
        v=j['checked'][arm];row=v['row']
        assert row['suite']=='de95cb1eedce56790d5836e30aaa27f8b930129eb92866bed6207ba9e99da2ba'
        assert row['cargo']==ds[product]['cargo']==v['mount']['cargo'] and v['mount']['same_inode']
        assert row['exit']==rc and row['actual_cargo']==calls and row['requested']==[expected] and body in v['stdout']
    for arm in ('default','full'):
        for i,phase in enumerate(j['kernel'][arm]['phases']):
            r=phase['result'];events=phase['events'];opens=[e['kind'] for e in events if e['kind'] in ('present','missing')]
            for kind in ('full','link'):
                assert sorted(e['crate'] for e in events if e['kind']==kind)==r[kind]
            assert all('syscall.'+str(e['tid']) in phase['streams'] and re.fullmatch('[0-9a-f]{64}',e['raw']) for e in events)
            assert sorted(opens)==sorted(r['payload_opens']) and phase['build_finished']==(i<2 or arm=='default')
            assert len(opens)==(0 if arm=='default' and i else 2)
            assert phase['missing_diagnostic']==(i==2 and arm=='full')
            assert r['native']==(['1:65','22:65','3:65'] if arm=='default' else ['1:65','22:66','22:66'])[i]
            assert r['cargo']==([0,101,101] if arm=='default' else [0,0,101])[i]
    assert j['kernel']['full']['phases'][1]['result']['executable']==j['kernel']['full']['phases'][2]['result']['executable']

def main():
    sums=root/'SHA256SUMS'
    if sums.is_file():
        manifest={line.split('  ',1)[1]:line.split('  ',1)[0] for line in sums.read_text().splitlines()}
        assert set(manifest)=={p.name for p in root.iterdir() if p.is_file() and p!=sums}
        assert all(sha((root/k).read_bytes())==v for k,v in manifest.items())
    subjects=j(root/'subjects.json');assert j(root/'source.json')==subjects['build_source'] and sha((root/'product.patch').read_bytes())==subjects['build_source']['patch_sha256']
    ds=subjects['development'];assert ds['parent']['cargo']!=ds['candidate']['cargo']
    assert all(ds['parent'][k]==ds['candidate'][k] for k in ('rustc','driver','rustc_version','cargo_version'))
    assert 'ca780121cea38bb9b0538d020d4bcce76ca30cbc' in ds['parent']['rustc_version']
    db=unzip(root/'ledgers.json.gz');blobs={h:base64.b64decode(v,validate=True) for h,v in unzip(root/'streams.json.gz').items()}
    assert all(sha(v)==k for k,v in blobs.items());used_streams=set();tot=Counter();h64=re.compile('[0-9a-f]{64}').fullmatch
    def read(ref):
        size,h,p=ref
        assert type(size)==int and size>=0 and h64(h) and p in blobs
        if h==p:assert len(blobs[p])==size
        used_streams.add(p);return blobs[p]
    phases='01-cold 02-unchanged 03-edit-and-new-asset 04-independent-clean 05-forced-full-keep-incremental 07-source-restore-missing-asset 08-independent-missing 09-forced-same-missing 10-recovered'.split()
    assert set(db['integration'])=={str(n)+'-'+c for n in (17,18,19) for c in ('on','off')}|{p+'-'+u for p in ('parent','integration') for u in ('used','unused')}
    for name,case in db['integration'].items():
        t=json.loads(read(case['terminal']));official=name[:2].isdigit();used='unused' not in name
        img=subjects['official'][name[:2]]['images'] if official else ds['parent' if name.startswith('parent') else 'candidate']|{'wild':subjects['official']['19']['images']['wild']}
        assert (t['cargo'],t['rustc'])==(img['cargo'],img['rustc']) and t['incremental']==0
        assert t['defaults_off']==name.endswith('-off') and t['relationship']==('used-private' if used else 'unused-public')
        unsafe=name.endswith('-on') or name.startswith('parent');assert sorted(case['phases'])==sorted(t['phases'])==phases
        targets=set()
        for phase,item in sorted(case['phases'].items()):
            ref=item['result'];assert ref[1]==t['phases'][phase];r=json.loads(read(ref));raw=item['files']
            assert r['phase']==phase and all(raw[k][1]==v for k,v in r['raw'].items())
            assert set(raw)==set(r['raw'])|({'test.stdout'} if 'test_stdout_sha'in r else set())
            if 'test.stdout'in raw:assert raw['test.stdout'][1]==r['test_stdout_sha']
            for v in raw.values():read(v)
            assert set(item['lines'])=={x['line'] for x in r['processes']+r['asset_opens']}
            check_phase(phase[:2],unsafe,used,r,raw,item['lines'],blobs,img)
            targets.add(r['target_source']);tot['integration_commands']+=1;tot['integration_streams']+=len(raw);tot['kernel_process_records']+=len(r['processes']);tot['kernel_asset_opens']+=len(r['asset_opens']);tot['kernel_streams']+=sum(k.startswith('trace.') for k in raw);tot['test_executions']+=(r['status']==0)
            tot['depfile_observations']+=len(r['depinfo']);tot['depfile_bytes_reopened']+=sum(v['sha256'] in case['physical'] for v in r['depinfo'].values());tot['reopened_test_elf_observations']+=r.get('elf','') in case['physical']
        source=fixture_values('reproduce-integration.py')['READER'].replace('RUST_VALUE','assembler_reader::observed(std::hint::black_box(3))' if used else '0u8')
        assert targets=={sha(source.encode())} and set(case['holds'])==set(t['holds'])=={'retained-edit','retained-missing'}
        for key,ref in case['holds'].items():
            assert ref[1]==t['holds'][key]
            assert all(h64(h) for h in json.loads(read(ref)).values())
        for h,v in case['physical'].items():
            if 'file' in v:
                assert h==v['file'][1] and v['bytes']==v['file'][0]
                b=read(v['file']);assert b'reader.rs' in b and b'payload.bin' not in b
    groups='initial edited repeat empty-edited missing empty-missing restore'.split()
    for arm,case in db['generic'].items():
        t=json.loads(read(case['terminal']));assert (t['cargo'],t['rustc'])==(ds[arm]['cargo'],ds[arm]['rustc'])
        assert set(case['phases'])==set(t['rows'])=={k+'.'+p for k in ('default','full') for p in groups}
        consts=set()
        for name,refs in case['phases'].items():
            mode,phase=name.split('.');stale=mode=='default' and arm=='parent';data={k:read(v) for k,v in refs.items()}
            r=json.loads(data['result.json']);assert r==t['rows'][name]
            messages=[json.loads(x) for x in data['stdout'].splitlines() if x.startswith(b'{')]
            fail=phase=='empty-missing' or (phase=='missing' and not stale)
            assert r['status']==(101 if fail else 0) and r['successful']==(not fail)
            assert messages[-1]=={'reason':'build-finished','success':not fail}
            if fail:assert r['missing'] and b'untracked.bin' in data['stdout']+data['stderr']
            else:
                expected='5:17' if phase in ('initial','restore') else '7:17' if phase=='missing' else '9:17' if stale and phase in ('edited','repeat') else '9:29'
                assert r['value']==expected and h64(r['elf'])
                assert r['target_fresh']==(phase=='repeat')
                tot['generic_executions']+=1;tot['reopened_generic_elf_observations']+=r['elf'] in case['physical']
            cmds=[l.decode() for l in data['stderr'].splitlines() if b'Running ' in l and b'--crate-name ' in l]
            compiler=[{'name':l.split('--crate-name ',1)[1].split(' ',1)[0],'link_only':'-Z link-only' in l or '-Zlink-only' in l} for l in cmds];assert compiler==r['compiler']
            app=[v['link_only'] for v in compiler if v['name']=='app']
            if phase=='repeat':assert not compiler
            elif phase in ('edited','missing'):assert app==[stale]
            else:assert app and (phase=='restore' or not any(app))
            consts.add((r['sources']['app/src/main.rs'],r['sources']['engine/src/lib.rs']))
            tot['generic_commands']+=1;tot['generic_streams']+=len(refs)-1
        source=fixture_values('reproduce-generic.py');assert consts=={(sha(source['app'].encode()),sha(source['gen'].encode()))}
    assert set(blobs)==used_streams and tot['integration_commands']==90 and tot['generic_commands']==28
    checked_sources(ds)
    return dict(sorted(tot.items()))
if __name__=='__main__':print(json.dumps(main(),sort_keys=True))

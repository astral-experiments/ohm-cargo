"""Recompute the complete scored-free Cargo/Rust qualification from exported evidence."""
from __future__ import annotations
import ast,collections,hashlib,json,os,re,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
PARENT='4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f'
CARGO='cfc66a7ceee5cad8f8939245d359e4db0d2b6f2abb5760c7cbefa6c9a1d454f8'
DRIVER='22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f'
WILD='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
pin='93526150df078af7dd8fc4226cdcc469539d2001'
def verify():
    counts={}
    with tarfile.open(R/'native.tar.xz') as t:
        files={m.name:t.extractfile(m).read() for m in t if m.isfile()}
    b=files.__getitem__;j=lambda name:json.loads(b(name))
    origin=j('originals.json');assert set(origin['files'])==set(files)-{'originals.json'}
    for name,rec in origin['files'].items():
        assert sha(b(name))==rec['portable_sha256'] and len(rec['original_sha256'])==64
        if not rec['replaced']:assert rec['portable_sha256']==rec['original_sha256'] and len(b(name))==rec['original_bytes']
    seeded=j('prepare.done');assert seeded['tracked_paths']==11244 and seeded['packages']==498 and seeded['source_commit']==pin
    l=j('launch.json');assert (l['driver'],l['cargo'],l['matched_front'],l['packaged_wild'],l['tree'])==(DRIVER,CARGO,PARENT,WILD,pin)
    assert l['verification_only'] and l['sdk_leaves']==80
    final=j('final-sdk.json');donor=j('protocol/h2-original-sdk.json');assert final.keys()==donor.keys()
    assert {n for n in donor if donor[n]!=final[n]}=={'bin/cargo','lib/librustc_driver-774a793a844d5500.so'}
    assert final['bin/rustc']['sha256']==PARENT and final['bin/cargo']['sha256']==CARGO and final['lib/librustc_driver-774a793a844d5500.so']['sha256']==DRIVER
    assert final['lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd']['sha256']==WILD
    assert b('worker.exit').strip()==b'1' and b'other-linker' in b('failure.txt')
    assert b('worker-v2.exit').strip()==b'0' and 'failure-v2.txt' not in files
    am=j('observation-amendment-v2.json');assert am['first_cargo_command_exit']==0 and am['replayed_from_existing_trace']
    assert origin['files']['check/cold/stdout']['original_sha256']==am['raw_stdout_sha256'] and sha(b('failure.txt'))==am['failure_sha256']
    observed={}
    for name in ('actual-loaded.json','actual-loaded-all-segments.json'):
        if name in files:observed.update(j(name))
    assert observed['compiler']['frontend_sha256']==PARENT and observed['compiler']['driver_sha256']==DRIVER and observed['linker']['sha256']==WILD
    assert all(int(l.split()[4])==observed['compiler']['driver_inode'] for l in observed['compiler']['all_executable_mappings'])
    assert j('retained-storage.json')['physical_verified']
    retained=j('retained-storage.json')['objects']
    state={'cold':'original','unchanged':'original','edited':'reversed','restored':'original','final-unchanged':'original'}
    history=j('protocol/historical.json');assert history['ruff']==pin and history['historical_commit']=='83a3afc3156d73ae4296f3fa74ede28e4c72bfcd'
    assert sha(b('protocol/historical.patch'))==history['patch_sha256']
    for mode in ('check','build','test'):
        roster=None
        for phase,expected in state.items():
            st=f'{mode}/{phase}/';cmd=j(st+'command.json');assert cmd['driver']==DRIVER and cmd['cargo']==CARGO and not cmd['trust_overrides'] and cmd['source_state']==expected
            wanted=['cargo','+ohm',mode]+(['--workspace','--no-run'] if mode=='test' else [])+['--locked','--offline','-j8','--message-format=json']
            assert cmd['argv']==wanted and j(st+'exit.json')==0
            rows=[json.loads(n) for n in b(st+'stdout').splitlines()];assert rows[-1]=={'reason':'build-finished','success':True}
            arts=[m for m in rows if m['reason']=='compiler-artifact'];result=j(st+'result.json')
            assert len(arts)==result['artifacts'] and sum(a['fresh'] for a in arts)==result['fresh']
            assert [a['target']['name'] for a in arts if not a['fresh']]==result['dirty']
            typed=[s['message'] for s in rows if s['reason']=='compiler-message'];assert all(e['level']!='error' for e in typed)
            assert result['diagnostics']==[{'level':e['level'],'message':e['message']} for e in typed]
            items=sorted(json.dumps([a['package_id'],a['target']['name'],a['target']['kind'],a['features'],a['profile']],sort_keys=True) for a in arts)
            current=sha(json.dumps(items,separators=(',',':')).encode())
            # Registry package IDs contain the canonical public crates.io URL; original printed paths occur only in manifest/location fields.
            assert current==result['roster_sha256'] and (roster is None or current==roster)
            roster=current
            p=j(st+'actual-processes.json');lines=j(st+'native-exec-lines.json');kinds=collections.Counter()
            assert len(lines)==len(p['processes'])
            for (op,s) in zip(p['processes'],lines):
                assert op['pid']==s['pid'] and op['kind']==s['kind'] and op['argv_sha256']==s['sha256']
                line=s['line'];assert line.startswith('execve(') and line.endswith('= 0')
                m=re.match(r'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line);assert m
                prog=Path(ast.literal_eval(m[1]));argv=ast.literal_eval(m[2]);kind=s['kind']
                assert len(argv)>0
                if kind in ('full','link-only'):
                    assert prog.name=='rustc' and argv[argv.index('--crate-name')+1]==op['unit_or_output']
                    assert (kind=='link-only')==any(s in ('-Zlink-only','link-only') or s.startswith('link-only=') for s in argv)
                if kind=='wild':
                    assert prog.name=='ld.bfd' and prog.parent.name=='wild-ld' and Path(argv[argv.index('-o')+1]).name==op['unit_or_output']
                if kind=='cargo':assert prog.name=='cargo' and '--message-format=json' in argv
                if kind=='cargo-version':assert prog.name=='cargo' and argv[1:]==['--version']
                if kind=='configure-linker':assert op['executable']=='/usr/bin/x86_64-linux-gnu-ld.bfd' and argv[argv.index('-o')+1]=='conftest'
                kinds[kind]+=1
            assert dict(kinds)==result['actual']==p['counts'] and kinds['cargo']==1 and 'other-linker' not in kinds
            held=j(st+'retained-links.json')
            assert held['original_packaged_wild']==WILD and len(held['wild'])==kinds['wild']
            assert all(retained[v['sha256']]==v['size'] for v in held['elf'].values())
            assert all(v['sha256'] in retained for v in held['wild'] if v['retained'])
            if phase in ('cold','edited','restored'):
                external=[v for v in result['ordinary'] if 'library' in v];assert external
                for i,v in enumerate(external):
                    s=st+'ordinary-'+str(i)+'/'
                    if mode=='check':
                        assert j(s+'ordinary-good/exit.json')==0 and j(s+'ordinary-bad/exit.json')==1
                        errors=[e['code']['code'] for line in b(s+'ordinary-bad/stderr').splitlines() if (e:=json.loads(line)).get('code')]
                        assert errors==['E0308'] and v['invalid']=='E0308'
                    else:
                        assert j(s+'compile/exit.json')==0 and j(s+'run/exit.json')==0
                        assert b(s+'run/stdout').decode()==v['output']==history['oracles'][expected] and not b(s+'run/stderr')
                if mode=='build':
                    assert j(st+'real-ruff-ret505/exit.json')==0 and result['ordinary'][-1]['fixed_source_sha256']==sha(b(st+'real-ruff-ret505/stdout'))
                if mode=='test':
                    assert b'1 passed; 0 failed' in b(st+'selected-parser-test/stdout') and j(st+'selected-parser-test/exit.json')==0
                    assert result['ordinary'][-1]['list_sha256']==sha(b(st+'parser-test-list/stdout'))
            counts[mode+'/'+phase]={'reported':len(arts),'fresh':result['fresh'],**dict(kinds)}
    terminal=j('complete.json')
    assert len(counts)==15 and terminal['restored'] and not b('worker-v2.stderr').strip()
    assert all(not c.get('rustdoc',0) for c in counts.values())
    ledger=[]
    for phase in state:
        for mode in ('check','build','test'):
            out=j(f'{mode}/{phase}/result.json')
            ledger.append([mode,phase,out['artifacts'],out['fresh'],out['actual']])
    assert terminal['records']==ledger==j('progress.json')
    phases=('cold','edited','restored')
    outputs=[b('build/'+phase+'/real-ruff-ret505/stdout') for phase in phases]
    assert outputs[0]==outputs[2]!=outputs[1]
    assert len({b('test/'+phase+'/parser-test-list/stdout') for phase in phases})==1
    for phase in ('unchanged','final-unchanged'):
        q=j('test/'+phase+'/actual-processes.json')['processes']
        assert [r['unit_or_output'] for r in q if r['kind']=='full']==['ron']
    projection=json.loads((R/'projection.json').read_bytes())
    assert projection['rust_release_commit']=='9828b82f475f18bf9077ee25f36de43d4fec8277' and projection['compiler_tree_in_both']=='47e23eb4bab742e271ca9a3cf1bbd583d5b4a640'
    assert projection['cargo_gitlink']=='7181bfa6256f94da142f80fd6af09cee02ec2c78' and projection['candidate_postbolt']==DRIVER and projection['cargo_binary']==CARGO
    receipt=R/'r2-build-original-receipts.tar.gz';assert sha(receipt.read_bytes())==projection['build_original_archive']
    with tarfile.open(receipt) as t:
        assert {m.name:sha(t.extractfile(m).read()) for m in t if m.isfile()}==projection['driver_build_files']
    return counts
if __name__=='__main__':print(json.dumps(verify(),indent=2,sort_keys=True))

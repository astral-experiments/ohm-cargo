"""Recompute native process counts and compare every declared artifact across both edit directions."""
from pathlib import Path
import ast
import collections
import hashlib
import json
import re
import tarfile

root = Path(__file__).resolve().parent
ledger = json.loads((root/'originals.json').read_bytes())
with tarfile.open(root/'native-records.tar.gz') as archive:
    rows = {m.name: archive.extractfile(m).read() for m in archive}
assert len(rows)==len(ledger)==521 and set(rows)==set(ledger)
assert sum(row['original']!=row['portable'] for row in ledger.values())==12
for name, data in rows.items():
    assert hashlib.sha256(data).hexdigest()==ledger[name]['portable']
load=lambda k:json.loads(rows[k])
assert load('complete.json')['timed_samples']==0
for mode,units,art_count in [('build',90,162),('test',148,266)]:
    phases=['cold','train-1','reversed','reversed-fresh','restored','restored-fresh']
    seen={}
    for phase in phases:
        prefix='records/'+mode+'/'+phase+'/'
        get=lambda name: load(prefix+name)
        args=get('argv.json')
        assert args==['cargo','+ohm',mode,*(['--no-run'] if mode=='test' else []),'-p','ruff_python_parser','--locked','--offline','-j8','--message-format=json']
        assert get('exit.json')['returncode']==0
        messages=[json.loads(l) for l in rows[prefix+'stdout'].splitlines()]
        assert messages[-1]=={'reason':'build-finished','success':True}
        artifacts=[m for m in messages if m['reason']=='compiler-artifact']
        rec=get('receipt.json');seen[phase]=rec
        assert len(artifacts)==rec['total']==units
        assert [m['target']['name'] for m in artifacts if not m['fresh']]==rec['dirty']
        assert sum(m['fresh'] for m in artifacts)==rec['fresh']
        assert set(rec['artifacts'])=={v for m in artifacts for v in m['filenames']} and len(rec['artifacts'])==art_count
        assert rec['elf']=={m['executable']:rec['artifacts'][m['executable']] for m in artifacts if m.get('executable')}
        if phase in ('cold','restored','reversed'):
            assert get('ordinary-0/exit.json')['returncode']==0
            src='    # foo\n    # bar\n     return 2' if phase=='reversed' else '       # foo\n       # bar\n    return 2'
            assert [v['stdout'] for v in rec['ordinary']]==[src]
            assert rows[prefix+'ordinary-0/native.stdout']==src.encode() and not rows[prefix+'ordinary-0/native.stderr']
        if phase=='cold':
            assert rec['fresh']==0
            continue
        jobs=[]; wild=[]; cargo=0
        for f, data in rows.items():
            if not f.startswith(prefix+'exec.'):continue
            for line in data.splitlines():
                match=re.fullmatch(rb'execve\((".*?"), (\[.*\]), .*\)\s+= 0',line)
                if match is None:continue
                path=Path(ast.literal_eval(match[1].decode()));argv=ast.literal_eval(match[2].decode())
                if path.as_posix().endswith('ohm-packaged-16-macro-20261027/rustup/toolchains/ohm/bin/cargo'):cargo+=1
                if path.as_posix().endswith('ohm-packaged-16-macro-20261027/rustup/toolchains/ohm/bin/rustc') and '--crate-name' in argv and not any(v.startswith('--print') for v in argv):
                    kind='link-only' if any(v in ('-Zlink-only','link-only') for v in argv) else 'full'
                    jobs.append((argv[argv.index('--crate-name')+1],kind))
                if path.name=='ld.bfd' and path.parent.name=='wild-ld':wild.append(Path(argv[argv.index('-o')+1]).name)
        assert cargo==1
        assert collections.Counter(jobs)==collections.Counter(map(tuple,rec['processes']['jobs']))
        assert sorted(wild)==sorted(rec['processes']['wild'])
        if phase in ('reversed','restored'):
            expected=[('ruff_python_trivia','full')]
            if mode=='test':expected += [('ruff_python_parser','link-only'),('fixtures','link-only')]
            assert sorted(jobs)==sorted(expected)
            assert sorted(n.split('-')[0] for n in wild)==([] if mode=='build' else ['fixtures','ruff_python_parser'])
        else:assert rec['fresh']==units and not jobs and not wild
    initial=seen['cold'];edited=seen['reversed'];restored=seen['restored']
    assert initial['elf']==edited['elf']==restored['elf'] and len(initial['elf'])==(0 if mode=='build' else 3)
    def changed(arm):
        assert set(arm['artifacts'])==set(initial['artifacts'])
        paths=[Path(k) for k,v in initial['artifacts'].items() if arm['artifacts'][k]!=v]
        assert all(p.name.startswith('libruff_python_trivia-') for p in paths)
        return sorted(p.suffix for p in paths)
    assert changed(edited)==['.rlib','.rmeta'] and changed(restored)==['.rlib']
print('Verified 12 ordinary Cargo commands, every physical changed/fresh command, all 428 reported files, six ordinary native outcomes and all three exact test ELF digests.')

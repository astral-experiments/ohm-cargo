#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import re
import sys

p=Path(__file__).resolve().parent
load=lambda x:json.loads((p/x).read_text())
bind=load('binding.json'); rows=load('phases.json'); dep=load('dep-info.json'); prior=load('prior.json')
expected=['original-repeat','history-revert','history-repeat','body-change','body-repeat','invalid','restore','restored-repeat']
assert set(expected)==set(rows)
assert prior['root']==bind['cargo_source']=='34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31'
assert prior['upstream']['commit']=='840b83a10fb0e039a83f4d70ad032892c287570a'
assert all(r['head_in_final_cargo'] for r in prior['checked'])
assert {r['number'] for r in prior['checked']}=={72,73,139,161,260,279,280}
assert bind['upstream_edit']=='6cfeb8aa07306cf06d7ab552d4190a5d24b6ff8d'
assert bind['locked_archives']==498
assert bind['preflight']['cold_dirty']==215 and bind['preflight']['cold_post_namespace_dirty']==210
assert len(dep)==3 and sum(d['declares_bin_main'] for d in dep.values())==1
assert next(d for d in dep.values() if d['declares_fixture'])['declares_bin_main']==False
assert next(d for d in dep.values() if d['declares_library'])['declares_bin_main']==False
base=rows['original-repeat']['objects']
bin_name='bin ruff_python_formatter'; lib_name='lib ruff_python_formatter'; test_name='test fixtures'
source=bind['source_sha256']; command=None
for name in expected:
    r=rows[name]; invalid=name=='invalid'; dirty=name in ('history-revert','body-change','restore')
    assert (r['exit'],r['diagnostics'])==((101,['E0308']) if invalid else (0,[]))
    semantic=name.startswith('body-')
    assert r['src']==(rows['body-change']['src'] if semantic else source['invalid.rs'] if invalid else source['visibility.rs'] if name.startswith('history-') else source['original.rs'])
    assert len(r['complete_artifacts'])==(214 if invalid else 215)
    assert [a[:2] for a in r['complete_artifacts'] if not a[-1]]==([['ruff_python_formatter',['bin']]] if dirty else [])
    procs=r['successful_execves']
    rust=[x for x in procs if x['sha']==bind['rustc']]
    wild=[x for x in procs if x['sha']==bind['known_wild']]
    assert len(rust)==int(dirty or invalid) and len(wild)==int(dirty)
    assert [x['image'] for x in procs if x['image'] not in ('cargo','rustc')]==(['cc','collect2','ld.bfd'] if dirty else [])
    assert sum(x['sha']==bind['cargo'] for x in procs)==1
    if rust:
        assert not rust[0]['link_only'] and rust[0]['crate']=='ruff_python_formatter'
        command=command or rust[0]['argv_literal_sha256']
        assert rust[0]['argv_literal_sha256']==command
    o=r['objects']
    for key in [lib_name,test_name]:
        assert o[key]['fresh'] and o[key]['files']==base[key]['files']
    if not invalid:
        assert o[test_name]['harness']==base[test_name]['harness'] and o[test_name]['count']==376
        assert o[bin_name]['format']=={'stdout':'value = 29\n' if semantic else 'x = 1\n','stderr':'','exit':0}
        gold='body-change' if semantic else 'original-repeat'
        assert o[bin_name]['files']==rows[gold]['objects'][bin_name]['files'] and o[bin_name]['fresh']!=dirty
    else:
        assert bin_name not in o
    raw=r['raw_input_sha256']
    assert {'exit','stdout.jsonl','stderr'}<=raw.keys() and all(re.fullmatch('[0-9a-f]{64}',v) for v in raw.values())
    if len(sys.argv)>1:
        physical=Path(sys.argv[1])/'records'/name
        assert all(hashlib.sha256((physical/f).read_bytes()).hexdigest()==h for f,h in raw.items())
assert rows['body-change']['objects'][bin_name]['files']!=base[bin_name]['files']
assert len({rows[n]['src'] for n in ('body-change','original-repeat','history-revert','invalid')})==4
print('Verified 8 ordinary Cargo commands, all 1,719 artifact rows, full native process roles, three independent product hashes, and the E0308 control.')


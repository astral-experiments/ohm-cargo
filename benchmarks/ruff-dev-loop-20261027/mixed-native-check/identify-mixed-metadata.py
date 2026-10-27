"""Decode the check and native copies available to one failed Ruff invocation."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

P = Path('/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027')
n = 'revision-native-66815c41574c'
F = P/'frozen-toolchain'
o = P/(n+'-check-diagnosis')
idx = {'parent':(P/'reference-parser-v3/parent-cold-target',P/'reference-parser-v3/parent-cold-shared',
                 F/'.bench-components/driver-051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518'),
       'candidate':(P/(n+'-private-state')/'target-candidate',P/(n+'-private-state')/'shared-candidate',
                    P/'subjects/driver-3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2')}
for arm,(target,shared,drv) in idx.items():
    c = o/(arm+'-native-then-check')
    result = json.loads((c/'result.json').read_bytes())
    assert result['rc'] == 101
    raw=[json.loads(row) for row in (c/'stdout').read_bytes().splitlines() if row.startswith(b'{')]
    candidates=set()
    for row in raw:
        if row['reason']=='compiler-artifact' and row['target']['name'] in {'pep440_rs','libcst_native','ruff_linter','ruff_workspace','ruff_db','ruff_python_semantic','libcst','ty_project','ruff_dev'}:
            candidates.update(f for f in row['filenames'] if f.endswith('.rmeta'))
    calls=[]
    for t in c.glob('exec.*'):
        for line in t.read_text(errors='replace').splitlines():
            if not line.endswith('= 0') or '"--crate-name"' not in line: continue
            argv = json.JSONDecoder().raw_decode(line[line.index(', [')+2:])[0]
            name = argv[argv.index('--crate-name')+1]
            if name not in {'ruff_workspace','ruff_dev','ruff_linter'}:continue
            deps = [argv[i+1] for i,k in enumerate(argv) if k=='--extern']
            calls.append(dict(target=name,argv=argv,direct_deps=deps))
            candidates.update(f.split('=',1)[1] for f in deps if '=' in f and f.split('=',1)[1].endswith('.rmeta'))
    wrap=['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc',
          '--ro-bind',str(target),str(P/'native-target'),'--ro-bind',str(shared),str(P/'shared'),
          '--ro-bind',str(drv),str(F/'lib/librustc_driver-774a793a844d5500.so'),'--']
    env=dict(os.environ,RUSTUP_HOME=str(P/'rustup'),RUSTUP_AUTO_INSTALL='0')
    headers=[]
    for f in sorted(candidates):
        a=subprocess.run([*wrap,'rustc','+ohm','-Zls=root',f],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,check=True,text=True)
        lines=a.stdout.splitlines()
        pri=next((i for i,line in enumerate(lines) if line.startswith('=External Dependencies=')),None)
        core=lines[:min(pri if pri is not None else len(lines),12)]
        relevant=[line for line in lines if any(k in line for k in ('pep440_rs','libcst_native')) and line not in core]
        if relevant or 'pep440_rs/' in f or 'libcst/' in f:headers.append(dict(path=f,root=core,matching_transitive=relevant))
    assert calls and len([h for h in headers if 'pep440_rs/' in h['path']]) >= 2
    (o/(arm+'-headers.json')).write_text(json.dumps(headers,indent=2)+'\n')
    (o/(arm+'-calls.json')).write_text(json.dumps(calls,indent=2)+'\n')
    print(arm,len(calls),len(headers),flush=True)

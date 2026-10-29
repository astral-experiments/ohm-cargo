#!/usr/bin/env python3
"""Decode real process launches and the forced marker order in a public rerun."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name('verify-native.py')))
calls, exec_map, single = (helpers[k] for k in ('calls','exec_map','single'))
root = Path(sys.argv[1])
proof = {}
for arm in ('original','proposed'):
    proof[arm] = {}
    for phase in ('seed','failure','recovery','unchanged'):
        stage = root/arm/phase
        trace = stage/'kernel.trace'
        rows = calls(trace)
        state = json.loads((stage/'observed.json').read_text())
        assert hashlib.sha256(trace.read_bytes()).hexdigest() == state['trace_sha256']
        rust = exec_map(rows,lambda path:path.name=='rustc' and path.parent.name=='bin')
        wrap = exec_map(rows,lambda path:path.name==arm+'-wrapper')
        assert sorted(rust)==sorted(wrap)==state['compiles']
        out = {'real_rustc':sorted(rust),'cargo_exit':state['exit'],'trace_sha256':state['trace_sha256']}
        proof[arm][phase] = out
        if phase!='failure':
            continue
        def event(pid,predicate):
            return single([(i,j,s) for who,i,j,s in rows if (pid is None or who==pid) and predicate(s)])
        def create(pid,name):
            return event(pid,lambda s:s.startswith('openat(') and 'O_CREAT' in s and
                         ('/'+name+'",' in s or '"'+name+'",' in s) and ' = -1 ' not in s)
        dep,app=wrap['dep'],wrap['app']
        compiler=event(None,lambda s:s.startswith('write(2,') and '/libdep-' in s and
                       '.rmeta' in s and r'\"artifact\"' in s and r'}\n"' in s)
        notification=event(dep,lambda s:s.startswith('write(2,') and r'\"}}\n' in s and s.endswith('= 4'))
        lookup=event(app,lambda s:s.startswith(('statx(','newfstatat(')) and '/dependency-metadata",' in s)
        marker=create(dep,'dependency-metadata')
        witnessed=create(app,'parent-started')
        release=create(None,'qa-consumer-observed')
        failed=create(dep,'dependency-failed')
        assert compiler[0]<notification[1]<lookup[0]<=lookup[1]<witnessed[0]<release[1]<failed[0]
        if arm=='original':
            assert '= -1 ENOENT' in lookup[2] and release[1]<marker[0]
        else:
            early=create(app,'parent-started-early')
            assert lookup[2].endswith('= 0') and ('stx_size=5' in lookup[2] or 'st_size=5' in lookup[2])
            assert marker[1]<notification[0] and lookup[1]<early[0]<=early[1]<witnessed[0]
        out['kernel_events']=sorted([[e[1],title] for e,title in
            [(compiler,'real compiler metadata'),(marker,'create dependency marker'),
             (notification,'forward complete metadata notification'),(lookup,'consumer stat'),
             (witnessed,'parent started'),(release,'bounded gate complete'),(failed,'producer failed')]])
(root/'native.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')

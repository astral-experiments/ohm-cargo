"""Project terminal states of all archive-window attempts, retaining raw record commitments."""
from pathlib import Path
import hashlib
import json
import sys
base=Path(sys.argv[1])
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
attempts=[]
for name in sys.argv[2:]:
    d=base/name
    info={'directory':name,'outer_exit':int((d/'exit').read_text()),'complete_pairs':len(list(d.glob('pair-*/result.json'))),'training':[]}
    info['raw_sha256']={k:sha(d/k) for k in ['stdout','stderr','exit','config.json']}
    for t in sorted(d.glob('train*')):
        p=t/'cargo.jsonl'
        if not p.is_file():continue
        rows=[r for r in map(json.loads,p.read_bytes().splitlines()) if r['reason']=='compiler-artifact']
        out,=[r for r in rows if r['target']['name']=='ruff_linter' and r['target']['kind']==['lib']]
        cfg=json.loads((d/'config.json').read_bytes())
        actual,=[Path(f) for f in out['filenames'] if f.endswith('.rmeta')]
        expected=Path(cfg['unit']).with_suffix('.rmeta')
        assert actual.is_relative_to(cfg['active']) and expected.is_relative_to(cfg['active'])
        info['training'].append({'typed_sha256':sha(p),'units':len(rows),'fresh':sum(v['fresh'] for v in rows),
                                'expected':str(expected.relative_to(cfg['active'])),'declared':str(actual.relative_to(cfg['active']))})
    if (d/'closed.json').exists():
        info['closed_sha256']=sha(d/'closed.json')
        info['worker_complete']=(d/'stdout').read_text().splitlines()[-1]=='All six ordinary edits and repeats passed.'
    if info['outer_exit']:
        err=(d/'stderr').read_text()
        info['failure']=('git-identity-preflight' if "assert git('config','user.email')" in err else
                         'unit-path-preflight' if "assert str(unit.with_suffix('.rmeta'))" in err else
                         'outer-mount-busy' if 'target is busy' in err and 'exit status 32' in err else 'other')
    attempts.append(info)
print(json.dumps(attempts,sort_keys=True,indent=2))

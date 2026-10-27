"""Compare ELF allocation byte digests and the exact headers that differed."""
import json
from pathlib import Path
import sys

d = Path(sys.argv[1])
out = {}
for mode in ('build','test'):
    data = {a+'-'+t: json.loads((d/(a+'-'+t+'-'+mode+'-edited.json')).read_bytes()) for a in ('parent','candidate') for t in ('warm','cold')}
    for a,b in (('parent-warm','parent-cold'),('candidate-warm','candidate-cold'),('parent-cold','candidate-cold')):
        left,right=data[a],data[b]
        assert left['samples']==right['samples'] and left['diagnostics']==right['diagnostics']
        assert left['products'].keys()==right['products'].keys()
        changed={}
        for k,p in left['products'].items():
            q=right['products'][k]
            if p['raw_sha256']==q['raw_sha256']:continue
            x,y=p['sections'],q['sections']
            assert set(x)==set(y)
            fields={s:[f for f in sorted(x[s]) if x[s][f]!=y[s][f]] for s in x if x[s]!=y[s]}
            run={s:fields[s] for s in fields if x[s]['flags']&2 or y[s]['flags']&2}
            assert set(s for s in run if 'digest' in run[s]) <= {'.note.gnu.build-id','.dynsym'}
            if a.split('-')[0]==b.split('-')[0]:
                assert fields=={'.note.gnu.build-id':['digest'],'.rodata':['entsize']} or fields=={'.rodata':['entsize'],'.note.gnu.build-id':['digest']}
            changed[k]=dict(header_or_content_changes=fields,allocated=run)
        out[f'{mode}/{a}--{b}']=dict(outputs=len(left['products']),raw_identical=len(left['products'])-len(changed),diagnostics_and_cli_equal=True,raw_differences=changed)
print(json.dumps(out,indent=2,sort_keys=True))

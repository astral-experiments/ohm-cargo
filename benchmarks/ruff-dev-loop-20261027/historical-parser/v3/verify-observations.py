"""Verify every retained command, compile action, output guard, and exact parent symbol witness."""
import collections,csv,gzip,hashlib,json,sys
from pathlib import Path
p=Path(__file__).resolve().parent
b=json.loads((p/'parent-symbol-bank.json').read_bytes());plan=json.loads((p/'active-plan.json').read_bytes());refs=json.loads((p/'guard-references.json').read_bytes())
rows=[json.loads(l) for l in (p/'rows.jsonl').read_bytes().splitlines()];assert len(rows)==256
P={(m,n):set(c['parent_full_name_witnesses']) for m,v in b.items() for n,c in v.items()};T={k:set() for k in P};after={k:collections.Counter() for k in P};counts=collections.Counter()
for ix,spec in enumerate(plan['blocks'],1):
    these=rows[(ix-1)*8:ix*8]
    for r in these:
        mode=spec['endpoint'];arm=spec['order'][r['position']-1];assert (r['block'],r['mode'],r['arm'],r['order'])==(ix,mode,arm,spec['order'])
        tag='late-original' if r['phase']=='fresh' else 'late-edited';a='control' if arm=='A' else 'candidate';g=refs['/'.join([a,tag,mode])]
        for k in ('sections_sha256','diagnostics_sha256','semantics_sha256','units','products','dirty','full','link_only','api'):assert r[k]==g[k],(ix,k)
        if tag=='late-original':
            assert r['actual_symbols']=={n:c[a+'_fresh_full_names'] for n,c in b[mode].items()}
        else:
            for n,h in r['actual_symbols'].items():(P if arm=='A' else T)[mode,n].add(h);after[mode,n][h]+=1
        counts[mode,arm,r['phase']]+=1
assert set(counts.values())=={32} and len(counts)==8
w=p/'post-witnesses.jsonl';extra=[json.loads(l) for l in w.read_text().splitlines()] if w.exists() else []
for j in extra:
    assert 1<=j['repetition']<=64
    for n,h in j['actual_symbols'].items():P[j['mode'],n].add(h)
missing={m:{n:sorted(T[m,n]-P[m,n]) for n in b[m] if T[m,n]-P[m,n]} for m in b}
print(json.dumps({'retained_edited':128,'retained_fresh':128,'extra_parent_witnesses':dict(collections.Counter(j['mode'] for j in extra)),'unmatched':missing},indent=2))
if (p/'completion.json').exists():assert all(not v for v in missing.values())

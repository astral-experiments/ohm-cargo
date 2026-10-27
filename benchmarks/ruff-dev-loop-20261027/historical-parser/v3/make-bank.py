from pathlib import Path
import collections,gzip,hashlib,json,re,sys
here=Path(__file__).resolve().parent;d=here.parents[1];p=d/'symbol-forensics';L=d/'symbol-lists';r={}
def enc(x):return json.dumps(x,separators=(',',':'),ensure_ascii=False)
def sha(x):return hashlib.sha256(x.encode()).hexdigest()
def key(t):
    m=re.fullmatch(r'(.+)\.llvm\.([0-9]+)',t[0])
    return (m[1],*t[1:]) if m and t[2]==2 else None
def unpack(h):
    with gzip.open(L/(h+'.json.gz')) as f:return list(map(tuple,json.load(f)))
for mode in ('build','test'):
    originals=[json.loads((p/f'{a}-fresh-{mode}'/'elf-symbols.json').read_bytes()) for a in ('control','candidate')]
    parent=[json.loads(f.read_bytes()) for f in sorted(p.glob('control-edited-*-'+mode+'/elf-symbols.json'))]+[json.loads(f.read_bytes()) for f in sorted(p.glob('control-bank-*-'+mode+'/elf-symbols.json'))]
    assert len(parent)==30,(mode,len(parent))
    tests=[json.loads(f.read_bytes()) for f in sorted(p.glob('candidate-edited-*-'+mode+'/elf-symbols.json'))];assert len(tests)==6
    r[mode]={}
    for name in sorted(parent[0]):
        parent_hashes=sorted({row[name]['sorted_sha256'] for row in parent});test_hashes=sorted({row[name]['sorted_sha256'] for row in tests})
        assert set(test_hashes)<=set(parent_hashes),(name,set(test_hashes)-set(parent_hashes))
        lists={h:unpack(h) for h in set(parent_hashes+test_hashes)}
        seen=collections.defaultdict(set)
        for vals in lists.values():
            for t in vals:
                if (k:=key(t)):seen[k].add(t[0])
        varied={k for k,s in seen.items() if len(s)>1}
        def norm(vals):
            return sha(enc(sorted(([t[0].rsplit('.llvm.',1)[0]+'.llvm.<validated-private-label>',*t[1:]] if key(t) in varied else t for t in vals),key=enc)))
        coarse={norm(v) for v in lists.values()};assert len(coarse)==1,(mode,name,coarse)
        r[mode][name]={'parent_trials':len(parent),'parent_full_name_witnesses':parent_hashes,'six_treatment_pilot_full_names':test_hashes,'candidate_fresh_full_names':originals[1][name]['sorted_sha256'],'control_fresh_full_names':originals[0][name]['sorted_sha256'],'volatile_hidden_keys':sorted(varied,key=enc),'invariant_sha256':next(iter(coarse)),'symbol_count':parent[0][name]['symbols']}
(here/'parent-symbol-bank.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')

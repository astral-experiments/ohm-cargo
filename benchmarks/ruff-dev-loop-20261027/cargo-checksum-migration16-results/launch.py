"""Open the qualified candidate arm only after independent stock controls and original readers all passed."""
from pathlib import Path
import fcntl,os,hashlib,json,runpy
p=Path(__file__).resolve().parent
s=runpy.run_path(p/'compare.py')
D,O,P,sdk,load,save,h,c=[s[x]for x in ('D','O','P','SDK','load','save','h','compare')]
digest='d7dfa671c8ec6ca2b50c7b0e41af4c0046e19bc02f18145d97d98455af2f722c'
assert set(os.sched_getaffinity(0))==set(range(24))
with (P/'native-measure.lock').open('rb')as f:
    fcntl.flock(f,fcntl.LOCK_EX);gates={}
    assert h(D/'subjects'/digest)==digest and h(sdk/'bin/cargo')==s['VERIFIED']
    for m,n in [('check',520),('build',501),('test',619)]:
        A=O/m;ds=[load(A/(arm+'-input-tree.json'))for arm in ('stock-repeat','upgraded')];seed=load(A/'seed-tree.json');assert all(v['sha256']==seed['sha256']for v in ds)
        reader_hash=[]
        for t in ('first','second'):
            q=A/'stock-repeat'/t;r=load(q/'receipt.json');assert r['exit']==0 and r['fresh']==r['units']==n
            assert not any(r['physical'].get(x,0) for x in ['rustc-full','rustc-link-only','wild','build-script'])
            assert not load(q/'products-changed-vs-seed.json')
            dd=A/'stock-repeat'/(t+'-readers')/'result.json';w=load(dd)
            if m=='check':assert w['ordinary-success']['exit']==0 and w['ordinary-error']['exit']==1 and w['ordinary-error']['secondary']['line_start']>0
            else:
                assert w['ruff-F821']['exit']==1 and 'F821'in w['ruff-F821']['stdout'] and w['ruff-version']['exit']==w['ty-version']['exit']==0
                if m=='test':assert w['parser-list']['names']>0
            reader_hash.append({k:[a['exit'],a['stdout_sha'],a['stderr_sha']] for k,a in w.items()})
        assert reader_hash[0]==reader_hash[1],(m,reader_hash)
        gates[m]={'units':n,'seed_tree_sha256':seed['sha256'],'stock_readers':reader_hash[0],'stock_input_classes':load(A/'seed-census.json')['counts']}
    save(O/'candidate-admission.json',{'candidate_sha256':digest,'source_commit':'01742c822d9153473d35566bd1c4fc987bcb5642','originals':gates,'plan_commit':'ae916e2b71f000eadcbc99bc0596f7ed6a65236b'})
    s['g']['original']()
    for mode in ('check','build','test'):c(mode,'candidate',digest)
    s['g']['original']()

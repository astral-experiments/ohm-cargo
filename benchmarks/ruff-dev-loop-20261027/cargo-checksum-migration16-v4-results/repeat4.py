"""Recheck an unchanged Ruff workspace on six preregistered, Cargo-only v4 upgrade commands."""
from pathlib import Path
import fcntl,hashlib,json,os,runpy,sys
p=Path(__file__).resolve().parent
g=runpy.run_path(p/'compare.py')
D,O,P,img,load,save,h,manifest,copy=g['D'],g['O'],g['P'],g['SDK']/'bin/cargo',g['load'],g['save'],g['h'],g['manifest'],g['copy']
census4=runpy.run_path(p/'census4.py')['census'];candidate='787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5'
bound={'check':'00f7b4909d31d8e4efa884f1e0e65f94f6ddaf13c807391467ce2181185ed623','build':'8162775d5d6a384bea702dc83ac23d659cc970122d1822178f01beda53b5941e','test':'424e245084ea226cc105eda7e9ac5a738f0f20f15cc9a9635f6fd2f001570fd4'}
stage='final-v4';tool=D/'subjects'/candidate;b3=p/'libcargo_depinfo_b3.so';assert h(tool)==candidate and h(img)==g['VERIFIED']
assert h(p/'runner.py')=='1bb4b4301ef1fa57c4b4cf2c6c70ddb5eed6958ea4d4ce1fb281d00c5a0c8a14'
assert h(p/'compare.py')=='c0338d7aee22d5d38e499232795da091965b2af6fe09e7a5ff3f81c35f337132'
assert set(os.sched_getaffinity(0))==set(range(24));phase=sys.argv[1];assert phase in ['prepare','run']
with (P/'native-measure.lock').open('rb')as lock:
    fcntl.flock(lock,fcntl.LOCK_EX);g['g']['original']();g['guard']()
    if phase=='run':assert all((O/m/stage/'copied.json').is_file()for m in bound)
    for m,expected in bound.items():
        r=O/m/stage;state=D/'states'/m/stage;seed=state.parent/'seed';q=O/m
        if phase=='prepare':
            r.mkdir(exist_ok=False)
            ref,ino=manifest(seed);assert ref['sha256']==expected==load(q/'seed-tree.json')['sha256']
            copy(seed,state);new,other=manifest(state);assert new['sha256']==expected and ino.keys()==other.keys() and not any(ino[k]==other[k]for k in ino)
            a=census4(seed,b3);b=census4(state,b3);assert a==b
            oldwire=load(q/'seed-census.json');assert a['counts']==oldwire['counts'] and set(a['rows'])==set(oldwire['rows'])
            for k,v in a['rows'].items():assert v['sha256']==oldwire['rows'][k]['sha256'] and v['lossy_or_replacement_names']==v['space_names']==0
            save(r/'initial-census.json',a);save(r/'copied.json',{'released_seed':ref,'new_isolated_input':new,'unique_regular_inodes':len(ino),'independent_regular_inodes':True,'class_counts':a['counts']});print(m,'prepared',len(ino),expected,flush=True)
            continue
        assert manifest(state)[0]['sha256']==expected
        settled=q/'seed'/load(q/'seed-complete.json')['final'];before=load(settled/'files.json')
        for tag in ('first','second'):
            rc=g['proc'](m,stage,tag,state,tool);rec=r/tag
            after=load(rec/'files.json');change={k:{'before':before.get(k),'after':after.get(k)}for k in set(before)|set(after)if before.get(k)!=after.get(k)}
            save(rec/'products-changed-vs-seed.json',change);save(rec/'census.json',census4(state,b3))
            g['exercise'](m,state,tool,stage,tag)
        assert manifest(seed)[0]['sha256']==expected
    g['g']['original']()

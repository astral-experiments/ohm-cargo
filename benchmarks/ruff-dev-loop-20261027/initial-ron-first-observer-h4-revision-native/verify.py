"""Verify typed second-enrollment reference triplets independently of wall results."""
from pathlib import Path
from collections import Counter
import gzip,json
root=Path(__file__).resolve().parent;obs=json.loads(gzip.decompress((root/'native.json.gz').read_bytes()))
assert obs['untimed_native_controls'] and obs['scored_observations']==0
a=obs['arms'];h=obs['host'];assert set(a)==(set('ABC') if h=='h4' else set('DC')) and h in ('h4','h5')
assert obs['manifest']=={'h4':'45d9876d4fc3325f80125c302890ca22b4752a7a930c6cde2926a4887b21b004','h5':'a63f1f78fd4a32f483f7fbe2adec1b61459a801289c392450b421a3681f911ff'}[h]
for arm,v in a.items():
    assert v['cargo']==('51e2e21a219004007a2d51e19e5a8edc57b47c7eb290383f4bbc13428e0f7d9c' if arm in 'AC' else 'dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1')
    assert v['rust']==('185629fabec9baacfd8fd7e61d6d84e79f69aa9abf4a4a9bb431c24f0a89d040' if arm in 'BC' else 'dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f')
    assert v['wild']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
    assert v['ordinary']==a['C']['ordinary'] and v['ordinary']['passed']
    rows=v['phases'];old,first,settled=[rows[t]['native'] for t in ('cold','first','settled')]
    assert first==settled and (arm!='C' or old==first)
    for k in old:
        x,y=old[k],first[k]
        if x==y:continue
        assert sorted([x['rodata_entsize'],y['rodata_entsize']]) in [[0,n] for n in (1,2,4,8,16,32,64,128,256)]
        assert x['bytes']==y['bytes'] and x['except_registered_wild_fields']==y['except_registered_wild_fields']
        assert x['rodata_type']==y['rodata_type']==1 and x['rodata_flags']==y['rodata_flags'] and x['rodata_flags']&0x12==0x12 and x['rodata_flags']&5==0
        assert len(x['build_id'])==len(y['build_id'])==64 and x['build_id']!=y['build_id']
    for i,name in enumerate(('cold','first','settled')):
        q=rows[name];n=q['physical']['num'];cmd=q['command'];proof=q['proof']
        assert len(q['rost'])==619 and q['executables']==102 and q['test_harnesses']==84 and q['ordinary_bins_and_examples']==18 and len(q['native'])==110
        assert cmd['fresh']==sum(t[-1] for t in q['rost'])==(0,619 if arm=='C' else 563,619)[i]
        assert (len(proof['physical_inputs']),cmd['checksums'])==((45,45) if i>0 or arm=='C' else (0,0))
        assert proof['encoded_sha256']==cmd['ron_fingerprint'] and proof['depinfo_sha256']==cmd['ron_depinfo']
        proc=q['physical'];assert n['wild']==sum(z[1] for z in proc['linkers']) and n['system']==sum(not z[1] for z in proc['linkers'])
        assert n['full']==sum(z[1]=='full' for z in proc['rustc']) and n['relink']==sum(z[1]=='link-only' for z in proc['rustc'])
        if i==0:assert n['full']==636 and n['relink']==0 and n['wild'] in (200,201) and n['system']==62
        elif i==1 and arm!='C':assert n['full']==1 and n['relink']==n['wild']==50 and ['ron','full'] in proc['rustc']
        else:assert n['full']==n['relink']==n['wild']==n['system']==n['probe']==0
print(json.dumps({k:{phase:(x['command']['fresh'],x['physical']['num']['full'],x['physical']['num']['relink'],x['physical']['num']['wild'],x['command']['checksums']) for phase,x in v['phases'].items()} for k,v in a.items()},sort_keys=True))

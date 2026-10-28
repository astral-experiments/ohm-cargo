"""Rebuild each per-source comparison from the canonical archive components and the actual caller."""
from pathlib import Path
import hashlib,json,subprocess,tarfile
p=Path(__file__).resolve().parent;sha=lambda b:hashlib.sha256(b).hexdigest()
if (p/'SHA256SUMS').is_file():subprocess.run(['sha256sum','--check','--quiet','SHA256SUMS'],cwd=p,check=True)
raw_contract=json.loads((p/'raw-native-vectors.json').read_bytes());idx=json.loads((p/'source-index.json').read_bytes())
typed_contract={};missing={};counts={};seen=set();pairs=0
for case in ('Bwasm','Cwasm','Bproject','Cproject'):
    pkg='ty_wasm' if case.endswith('wasm') else 'ty_project';name=case+'-'+pkg
    table={};summary={};v={}
    with tarfile.open(p/(case+'.tar.gz')) as t:
        for m in t:
            assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
            key=case+'/'+m.name;assert key in idx and key not in seen;seen.add(key);data=t.extractfile(m).read();assert sha(data)==idx[key];v[m.name]=data
    done=json.loads(v['complete.json']);assert done['clocks']==0 and len(done['history'])==(7 if pkg=='ty_wasm' else 3)
    if case[0]=='B':assert done['raw_rejected']
    measurements=[];absent=[]
    for row in done['history']:
        step=row['tag'];stage=row['input'];w=json.loads(v[step+'/witness.json']);assert w['tag']==step and w['input']==stage
        assert w['raw']==row['raw'] and w['typed']==row['typed'] and row['matches_anchor']
        if w['raw'] not in raw_contract[name][stage]['files']:absent.append(step)
        original=table.setdefault(stage,w['typed']);assert w['typed']==original
        reader=v[step+'/reader.stdout'];assert sha(reader)==row['caller']==w['caller']['sha256']
        assert sha(reader)=={'original':'721696b22e172c4f9dbe15ec5e04a04a9939188eca12d8110ab62f9de81d96a1','reversed':'0a9e5b203ef44812cd48a115f5fceafaffc2b0c0b013a1de927e2660865a10c5'}[stage]
        assert not v[step+'/reader.stderr'] and not v[step+'/reader.compile.stderr']
        summary.setdefault(stage,[]).append(step)
        for f,a in w['archives'].items():
            projection=a['projection'];real=a['original_names'];ob=projection['objects']
            assert a['raw']==w['raw'][f] and a['typed']==w['typed'][f]
            assert sha(json.dumps(projection,sort_keys=True,separators=(',',':')).encode())==a['typed']
            assert len(ob)==len(real)==projection['link_roster']['object_names'] and len(real)==len(set(real))
            assert projection['link_roster']['rust_object_order_matches_archive'] and not projection['link_roster']['native_lib_filenames']
            assert all(n.rsplit('.',3)[0]+'.@nonce@.rcgu.o'==s[0] and s[1]>0 and len(s[2])==64 for n,s in zip(real,ob,strict=True))
            assert projection['symbol_count']>0 and len(projection['symbol_name_member_ordinals'])==64
            assert projection['specials']['full_metadata_wrapper'] and projection['specials']['full_link_wrapper_structure']
            measurements.append([Path(f).name,len(ob),projection['symbol_count']]);pairs+=1
        for f,z in w['raw'].items():
            if f not in w['archives']:assert w['typed'][f]==z
    if case.startswith('B'):assert any(s.startswith('unchanged') for s in absent),(case,absent)
    if pkg=='ty_wasm' and case.startswith('C'):
        seq={r['tag']:r for r in done['history']}
        for first,second in [('anchor','unchanged-one'),('unchanged-one','unchanged-two'),('edit','edit-repeat'),('restore','restore-repeat')]:assert seq[first]['raw']==seq[second]['raw']
    if case=='Cproject':assert not absent
    counts[case]=dict(commands=len(done['history'])-1,hashes_observed=len(done['history']),objects=sorted(set(tuple(z) for z in measurements)))
    typed_contract[name]=table;missing[name]=absent
assert seen==idx.keys()
controls=json.loads((p/'mutation-controls.json').read_bytes())
assert set(controls)=={'inconsistent-link-name','metadata-payload','object-content','symbol-provider'} and all(a['before_sha256']!=a['after_sha256'] for a in controls.values())
assert all(a['outcome'] in ('rejected','changed fingerprint') for a in controls.values())
bound={'typed_contract':typed_contract,'original_raw_vector_unseen':missing,'measurements':counts,'archive_witnesses':pairs,'mutation_controls':controls,'clocks':0}
if (p/'derived.json').is_file():assert json.loads((p/'derived.json').read_bytes())==json.loads(json.dumps(bound))
print(json.dumps(bound,sort_keys=True))

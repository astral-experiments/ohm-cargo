"""Attribute R2's three literal metadata files to actual Rust stable and numeric identities."""
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import runpy
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',',':'), default=bytes.hex).encode()


def main():
    base=Path(__file__).resolve().parent
    decoder=base/'wire.py'
    assert sha256(decoder.read_bytes()).hexdigest()=='99741e5a62c24e05f4bb888c638e6784db100c50cf218cbeaeb81f1fd9a9b49a'
    decode=runpy.run_path(str(decoder))['decode']
    methods=dict(zip([2181,2357,2513,2656,2817],['iter','iter_mut','keys','values','values_mut']))
    variants={}; raws={}; products=[]
    for path in sorted((base/'rmeta').glob('libron-*.rmeta')):
        raw=path.read_bytes(); digest=sha256(raw).hexdigest()
        assert path.name=='libron-'+digest+'.rmeta' and len(raw)==1442543
        locals_at_return={}
        def profile(frame,event,arg):
            if frame.f_code is decode.__code__ and event=='return': locals_at_return.update(frame.f_locals)
        sys.setprofile(profile)
        try: obj=decode(raw,'src/value/map.rs')
        finally: sys.setprofile(None)
        z=locals_at_return; declarations=[]
        for i in range(3579,3584):
            s=obj['def_spans'][i]
            assert s==obj['def_ident_spans'][i] and s[:2]==[0,0] and s[3:]==[0,9,0]
            assert obj['source_table'][9][0].endswith('/ron-0.12.0/src/value/map.rs')
            assert '::{OpaqueTy}::' in z['defname'](i)
            declarations.append({'def_index':i,'path_hash':f'{z["ids"][i]:016x}',
                                 'map_method':methods[s[2]],'source_byte':s[2]})
        stable_fields=('global','stable','defs','source_table','expansion_hashes','allocations')
        payloads={field:{'digest':sha256(canonical(obj[field])).hexdigest(),
                  'count':len(obj[field]) if isinstance(obj[field],(list,dict)) else 1} for field in stable_fields}
        payloads['root_hashes']=z['full'].hex()
        variants[digest]={'stable_fields':payloads,'synthetic_lifetime_order':declarations}
        products.append(obj);raws[digest]=raw
    assert len(variants)==3
    evidence=list(variants.values()); assert all(v['stable_fields']==evidence[0]['stable_fields'] for v in evidence)
    normalized=lambda rows:sorted((a['path_hash'],a['source_byte'],a['map_method']) for a in rows)
    assert all(normalized(v['synthetic_lifetime_order'])==normalized(evidence[0]['synthetic_lifetime_order']) for v in evidence)
    for field in ('def_spans','def_ident_spans'):
        assert len(products[0][field])==3584
        assert all(products[0][field][:3579]==v[field][:3579] for v in products)
    base_hash='1539e22718a288fa143ff936f5291526ba4a0499334c1b4e762ec780cf2f16d5'
    b=raws[base_hash]; diffs={}
    for h,data in raws.items():
        if h==base_hash:continue
        at=[i for i,(a,c) in enumerate(zip(b,data)) if a!=c]; ranges=[]
        for _,items in groupby(enumerate(at), lambda p:p[1]-p[0]):
            region=[x[1] for x in items];ranges.append([region[0],len(region)])
        assert len(at)==138; diffs[h]={'bytes_different':len(at),'ranges':ranges}
    return {'artifacts':variants,'base_sha256':base_hash,'byte_deltas':diffs}


if __name__=='__main__':print(json.dumps(main(),sort_keys=True,indent=2))

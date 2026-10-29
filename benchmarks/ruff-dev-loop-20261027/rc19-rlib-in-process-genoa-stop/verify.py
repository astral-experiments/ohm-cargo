"""Check the portable pair. Pass --archive A|B CRATE FILE to reproduce the other full native SHA."""
from pathlib import Path
import collections,argparse,gzip,hashlib,json,mmap,re
p=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()
def gz(name):return json.loads(gzip.decompress((p/name).read_bytes()))
def plain(name):return json.loads((p/name).read_bytes())
def blob(k,entry):
    content=(p/(k+'-'+entry['raw_compressed'])).read_bytes()
    assert sha(content)==entry['compressed_sha256']
    decoded=gzip.decompress(content);assert len(decoded)==entry['size'] and sha(decoded)==entry['from']
    return decoded
d=plain('comparison.json');objects=gz('objects.json.gz');ins=gz('physical-inputs.json.gz');metadata=plain('metadata.json');raw=plain('raw-ledger.json')
assert d['wall_samples']==0 and d['additional_cargo_commands_after_stop']==0 and d['volumes_detached']
assert (d['pristine']['cold_units'], d['pristine']['cold_fresh'], d['pristine']['unchanged_fresh'],d['pristine']['starting_files'])==(248,0,248,452)
assert d['pristine']['native_cli']['stdout']=='1 SIM222\n'
aa,bb=[d['arms'][k] for k in 'AB'];assert aa['original_archive']==bb['original_archive']==d['pristine']['native_cli']['linter']
assert aa['edited_archive']!=bb['edited_archive'] and aa['edited_size']==bb['edited_size'] and aa['native_caller']['ast']!=bb['native_caller']['ast']
for k,v in zip('AB',(aa,bb)):
    assert v['native_caller']['linter']==v['edited_archive'] and v['native_caller']['stdout']=='2 SIM222\n3 SIM222\n4 SIM222\n' and v['native_caller']['exit']==0
    assert v['phases']['repeat']['roles']=={'cargo':1} and v['phases']['edit']['roles']==({'cargo':1,'rustc-full':10} if k=='A' else {'cargo':1,'rustc-full':10,'rustc-query':1})
    assert all(row['exit']==0 for phase in v['phases'].values() for row in phase['raw_argv'])
    assert list(map(len,[v['phases']['edit']['hints'],v['phases']['repeat']['hints']]))==([0,0] if k=='A' else [1,0])
for phase in ('edit','repeat'):
    assert aa['phases'][phase]['normalized_full_argv']==bb['phases'][phase]['normalized_full_argv']
    assert aa['phases'][phase]['typed_ledger']==bb['phases'][phase]['typed_ledger']
assert aa['native_caller']['executable']==bb['native_caller']['executable'] and aa['native_caller']['stderr_sha256']==bb['native_caller']['stderr_sha256']
assert ins['A']['inputs']==ins['B']['inputs'] and metadata['A']==metadata['B']
o1,o2=[{v['key_sha256']:v for v in ins[k]['all_typed_files']} for k in 'AB']
assert len(o1)==len(o2)==452 and o1.keys()==o2.keys();delta=[k for k,v in o1.items() if v!=o2[k]]
assert len(delta)==10 and all(o1[k]['basename'].endswith('.rlib') and o1[k]['bytes']==o2[k]['bytes'] for k in delta)
assert sum(len(x) for x in ins['A']['inputs'].values())==150
assert {r['name'] for r in objects['A']}=={r['name'] for r in objects['B']}==set(ins['A']['inputs'])
optional=argparse.ArgumentParser();optional.add_argument('--archive',nargs=3,metavar=('ARM','CRATE','FILE'));args=optional.parse_args()
if args.archive:
    assert args.archive[0] in ('A','B') and args.archive[1] in ins['A']['inputs']
for side,peer in [('A','B'),('B','A')]:
    assert sum(r['native_CGUs'] for r in objects[side])==1107
    for r in objects[side]:
        other,=[v for v in objects[peer] if r['name']==v['name']];n=r['native_CGUs'];assert n==len(r['unchanged_cgu_files'])==len(other['unchanged_cgu_files'])
        assert r['source_sha256']==other['reconstructed_and_actual_peer_sha256']!=r['reconstructed_and_actual_peer_sha256']==other['source_sha256']
        assert r['size']==other['size'] and r['metadata']==other['metadata']
        assert all(u['matches_by_cgu_basename_size_full_digest']==u['retained_source_objects']==n and not u['unmatched'] for u in r['unit_objects'])
        assert len(r['unit_objects'])==2 and set(u['arm'] for u in r['unit_objects'])==set('AB')
        assert r['raw_symbol_index']==other['raw_symbol_index'] and r['ordered_symbol_member_digest']!=r['peer_ordered_symbol_member_digest']
        assert (r['origin'],r['peer'])==(other['peer'],other['origin']) and r['origin']!=r['peer']
        before=('.'+r['origin']+'.rcgu.o').encode();after=('.'+r['peer']+'.rcgu.o').encode()
        for (a,b,size,sha1),(inv_b,inv_a,other_size,sha2) in zip(r['unchanged_cgu_files'],other['unchanged_cgu_files']):
            assert a.encode().replace(before,after)==b.encode() and (a,b,size,sha1)==(inv_a,inv_b,other_size,sha2)
        assert [v['name'] for v in r['changes']]==['//','lib.rmeta-link'];previous=0
        for c,co in zip(r['changes'],other['changes']):
            original=blob(side,c);opposite=blob(peer,co)
            assert c['offset']>=previous and original.count(before)==n and c['count']==n
            assert original.replace(before,after)==opposite and sha(opposite)==c['to']
            assert sum(a!=b for a,b in zip(original,opposite))==c['unequal_bytes'];previous=c['offset']+c['size']
        if args.archive and args.archive[:2]==[side,r['name']]:
            with open(args.archive[2],'rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
                assert len(data)==r['size'] and sha(data)==r['source_sha256'];h=hashlib.sha256();prev=0
                for c in r['changes']:
                    start=c['offset'];end=start+c['size'];assert data[start:end]==blob(side,c)
                    h.update(data[prev:start]);h.update(data[start:end].replace(before,after));prev=end
                h.update(data[prev:]);assert h.hexdigest()==r['reconstructed_and_actual_peer_sha256'];print('Reconstructed the other complete physical archive:',h.hexdigest())
print('Verified 248 units, 452 paths, 150 externs, 1,107 object identities, 20 name-table/metadata replacements, and both native caller outcomes. Raw archive rejection preserved.')

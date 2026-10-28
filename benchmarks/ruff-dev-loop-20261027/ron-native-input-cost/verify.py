from pathlib import Path
import collections,gzip,hashlib,json,statistics
D=Path(__file__).resolve().parent
def unpack(p):return json.loads(gzip.decompress((D/p).read_bytes()))
x=unpack('costs.json.gz');t=x['tool'];assert t['archive']=='6d9e454fc11f76977dc803893aff6304ed33d6a26efae8696573bea74baa27ae' and t['known_answers']==['empty','abc']
assert t['sources']['hash-inputs.c']==hashlib.sha256((D/'run/hash-inputs.c').read_bytes()).hexdigest()
expected={'simple_tokenizer':(148,95005487,107),'document':(289,442853145,248),'ruff':(311,500166915,270)}
results={}
wanted={'Scrt1.o','crti.o','crtbeginS.o','libgcc_s.so','libgcc_s.so.1','libgcc.a','libutil.a','librt.a','libpthread.a','libm.so','libm.so.6','libmvec.so.1','libdl.a','libc.so','libc.so.6','libc_nonshared.a','ld-linux-x86-64.so.2','crtendS.o','crtn.o'}
common=None
for n,(num,sz,target)in expected.items():
    case=x['data'][n];r=case['native'];d=r['native_depfile_paths'];assert case['reproduced_one_exact_native'] and r['oracle']in case['workspace_outputs'].values()
    assert len(d)==len({tuple(f['node'])for f in d})==num and sum(f['bytes']for f in d)==sz
    assert r['native_binary']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5' and r['hasher']==t['hasher'] and r['explicit_width']==8 and r['affinity']==list(range(4,12))
    assert r['all_positive_operand_hashes_equal_throughout'] and len(set(r['selected_double_checked_blake3']))==3 and all(any(f['blake3']==u for f in d)for u in r['selected_double_checked_blake3'])
    assert collections.Counter(f['class']for f in d)=={'target':target,'sdk':22,'system':19}
    system={f['name']:f for f in d if f['class']=='system'};assert set(system)==wanted
    if common is None:common=system
    else:assert system==common
    assert {n for n,f in system.items()if f['kind']=='other'}=={'libgcc_s.so','libm.so','libc.so'}
    assert system['libgcc_s.so']['script_tokens']==['GROUP','(','libgcc_s.so.1','-lgcc',')']
    assert all('AS_NEEDED' in system[v]['script_tokens'] for v in ['libm.so','libc.so'])
    rows=r['rows'];assert [v['order']for v in rows]==['WH','HW','HW','WH','HW','WH'] and all(min(v['W'],v['H'])>0 for v in rows)
    wm=statistics.median(v['W']for v in rows);hm=statistics.median(v['H']for v in rows)
    results[n]={'positive_files':num,'bytes':sz,'link_median_ms':round(wm/1e6,3),'blake3_median_ms':round(hm/1e6,3),'paired_hash_over_link_median':round(statistics.median(v['H']/v['W']for v in rows),4)}
s=unpack('shared-inputs.json.gz');per=s['individual'];f=s['retained_literal_inputs'];assert len(per)==50 and len(f)==s['distinct_still_materialized']==3397
for t,q in per.items():
    v=[r for r in f.values()if t in r['locations']];assert len(v)==q['literal_positive_files_still_materialized'] and sum(w['size']for w in v)==q['bytes']
    assert q['not_still_materialized']==[['symbols.o','private-target']]
assert sum(v['size']for v in f.values())==s['inode_deduplicated_bytes']==1410373480 and sum(q['bytes']for q in per.values())==s['sum_still_materialized']==12656036748 and sum(q['literal_positive_files_still_materialized']for q in per.values())==s['total_still_materialized']==11779
print(json.dumps({'engineering_only':True,'targets':results,'distinct_still_materialized_bytes':s['inode_deduplicated_bytes'],'all_still_materialized_argument_bytes':s['sum_still_materialized'],'whole_command_wall_samples':0},sort_keys=True))

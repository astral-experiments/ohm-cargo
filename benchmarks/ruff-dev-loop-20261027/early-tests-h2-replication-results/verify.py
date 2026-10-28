from pathlib import Path
import collections,gzip,hashlib,json,sys
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root));from analyze import evaluate
p=json.loads((root/'plan.json').read_bytes());j=json.loads(gzip.decompress((root/'histories.json.gz').read_bytes()));exact=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
assert exact(root/'plan.json')==j['plan'];qual=j['mode']=='qualify';seen=0;count=0
for name,h in j['histories'].items():
    assert h['order']==('ABC' if qual else p['orders'][int(name[-2:])-1]);assert h['media']=='tmpfs' and h['affinity']==list(range(16));assert len(h['seed_commands'])>=2
    last=h['seed_commands']['seed-'+str(max(int(k.split('-')[1]) for k in h['seed_commands']))];assert last['dirty']==0 and (last['units'],last['native'],last['exe'])==(617,108,100)
    arms=h['arms'];first=list(arms.values())[0]['phases']
    for arm,r in arms.items():
        assert p['images'][arm]==r['cargo'] and r['snapshot']==h['seed']['uncompressed_inputs']
        q=r['phases'];pre=q['preselect-fresh'];assert (pre['units'],pre['exe'],len(pre['raw_native']))==(617,100,108) and not pre['typed_dirty']
        for ph in ('first','settled','restore','restored-settled'):
            z=q[ph];count+=1
            assert len(z['raw_native'])==110 and (z['units'],z['exe'],z['test_profile'],z['ordinary'])==(619,102,84,18)
            assert z['raw_native']==first[ph]['raw_native'] and z['roster']==first[ph]['roster'] and z['diagnostics']==first[ph]['diagnostics']
            assert hashlib.sha256(json.dumps(z['diagnostics'],sort_keys=True,separators=(',',':')).encode()).hexdigest()=='6d465066830c855472a3d30b1d88e0bdeb5961feac9f319f445db562ad24fa11'
            assert z['ty_library']['fresh'] and z['ty_library']['sha256']==pre['ty_library']['sha256']==last['ty_server']['sha256']
            assert not qual or z['cmd']['elapsed_ns'] is None
            if ph in ('first','restore'):
                a=z['ordinary_caller'];assert a==first[ph]['ordinary_caller'] and a['registered']>0 and a['test'].endswith('inlay_hints::default_inlay_hints')
                assert a['status']=='pass' if ph=='restore' else a['status'] in ('pass','old-snapshot-mismatch')
            if ph.endswith('settled'):
                assert not z['typed_dirty'];prev=q['first' if ph=='settled' else 'restore'];assert z['raw_native']==prev['raw_native']
            if qual:
                tr=z['trace'];assert tr['total']==len(tr['compilers']) and tr['wild']==sum(len(c) for c in tr['linkers'].values())
                if ph=='first':
                    e2e=tr['linkers'][z['e2e'][0]];k=1 if arm=='C' else 2;ty=Path(z['ty_library']['path']).name
                    assert tr['total']==tr['wild']==k+1 and tr['full']=={'full':k+1} and len(e2e)==k
                    assert all(len(s['ty_rlibs'])==1 and Path(s['ty_rlibs'][0]).name==ty for s in e2e)
                    comp=[v for v in tr['compilers'] if v['source']=='crates/ty_server/tests/e2e/main.rs'];assert len(comp)==k and len({v['signature'] for v in comp})==1 and all(v['end'][1]==0 for v in comp)
                if ph.endswith('settled'):assert not tr['total'] and not tr['wild']
        if not qual:seen+=1
        e=q['first']['e2e'][0];assert set(v for v in q['first']['raw_native'] if q['first']['raw_native'][v]!=q['restore']['raw_native'][v])=={e}
if qual:assert j['rows'] is None and seen==j['scored_calls']==0
else:
    assert seen==j['scored_calls']==24;row=j['rows']
    for v in row:
        h=j['histories']['block-%02d'%v['block']];assert h['order']==v['order'] and h['history_sha']==v['complete'] and v['ns']=={a:h['arms'][a]['phases']['first']['cmd']['elapsed_ns'] for a in h['order']}
    assert evaluate(p,row)==json.loads((root/'analysis.json').read_bytes())
print(json.dumps({'mode':j['mode'],'native_commands_examined':count,'matched_histories':len(j['histories']),'elapsed_observations':seen},sort_keys=True))

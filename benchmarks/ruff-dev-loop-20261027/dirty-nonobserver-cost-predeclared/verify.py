from pathlib import Path
import gzip,hashlib,json,sys
p=Path(__file__).resolve().parent;sys.path.insert(0,str(p))
from analyze import calc
a=json.loads(gzip.decompress((p/'control.json.gz').read_bytes()));plan=json.loads((p/'schedule.json').read_bytes())
assert hashlib.sha256(gzip.decompress((p/'control.json.gz').read_bytes())).hexdigest()==plan['source_qualification_sha']
for kind in ('check','build'):
    for phase,dirt in [('original',True),('edit',True),('unchanged_edit',False),('restore',True),('unchanged_restore',False)]:
        group=[]
        for arm in ('B','C','B2','C2'):
            z=a['qualified'][kind+'-'+arm][phase];tr=z['trace'];assert 'elapsed_ns' not in z and len(tr['jobs'])==int(dirt) and tr['observer_probes']==int(dirt and arm[0]=='C');assert z['checksummed_sources']==4 and z['foreign_marker'] is False and z['fresh']==(not dirt)
            if dirt:assert tr['jobs'][0]['depinfo_flag']==(arm[0]=='C')
            if 'edit' in phase:assert z['ordinary_api']=={'rc':1,'code':'E0599'}
            elif kind=='build':assert z['ordinary_api']=={'rc':0,'ordinary_output':'2-6'}
            else:assert z['ordinary_api']=={'rc':0,'metadata':True}
            group.append(z)
        assert len({z['outputs']['.rmeta'] for z in group})==len({z['depinfo_sha256'] for z in group})==1
        if kind=='build':
            for j in range(4):
                size={z['members'][j]['size'] for z in group};kindset={z['members'][j]['kind'] for z in group};assert len(size)==len(kindset)==1
                k=next(iter(kindset));field='exact_member_names_folded' if k=='lib.rmeta-link' else 'sha'
                assert len({z['members'][j][field] for z in group})==1
orders=[s['check'] for s in plan['schedule']];cases={}
for name,pair in [('null',[dict(B=10,C=10) for _ in orders]),('slot',[{o[0]:10,o[1]:13} for o in orders]),('known',[dict(B=10,C=12) for _ in orders])]:
    q=calc(orders,pair,2026102701);cases[name]=q['p_two_sided'];assert (q['p_two_sided']==1 and abs(q['geometric_mean_overhead_pct'])<1e-8) if name!='known' else (q['p_two_sided']<.00001 and abs(q['geometric_mean_overhead_pct']-20)<1e-6)
for f,d in plan['runner'].items():assert hashlib.sha256((p/f).read_bytes()).hexdigest()==d
print(json.dumps({'qualified':40,'caller_modes':2,'timed_slots':96,'selftests':cases},sort_keys=True))

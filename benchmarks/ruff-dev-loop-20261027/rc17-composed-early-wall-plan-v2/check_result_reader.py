"""Exercise the entire 48-slot offline reader with generated records, including a corrupt output."""
from pathlib import Path
import json
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import guards as g
from analysis import evaluate
from verify_result import run


def test():
    with tempfile.TemporaryDirectory(prefix='synthetic-scheduler-results-') as t:
        root=Path(t);admission=root/'native.json';out=root/'wall';out.mkdir()
        paths={str(i):f'{i:064x}' for i in range(110)}
        procs=[{'kind':'full','target':'ron','exit':0},{'kind':'wild','target':'0','exit':0}]
        p=dict(units=619, fresh=563, roster='roster',exes=list(paths)[:102],diagnostics=[],ty_server={'fresh':True},e2e=['0'],native=paths,counts={'full':1,'wild':1})
        events=[dict(reason='compiler-artifact',fresh=i<563,executable=str(i) if i<102 else None,filenames=[str(i)],
                package_id='path+file:///ruff#x' if i<110 else 'registry+x',manifest_path='/canonical/ruff/Cargo.toml',
                target={'kind':['test']},profile={'test':i<84},features=[]) for i in range(619)]
        schema=('package_id','manifest_path','target','profile','features','filenames','executable')
        p['roster']=g.digest(sorted(json.dumps({k:r[k] for k in schema},sort_keys=True) for r in events))
        listing=b'one: test\n';listing_hash=g.hashlib.sha256(listing).hexdigest()
        models=dict(subjects={'B':'b'*64,'C':'c'*64},allowed={k:[v] for k,v in paths.items()},roster=g.summary(p),
            repeat_roster=g.digest(sorted(g.row_roster(procs).items())),listing_sha256=listing_hash)
        registry={'registry-'+str(i):f'{i:064x}' for i in range(78)}
        models.update(registry=registry,registry_sha256=g.digest(registry))
        manifest=g.manifest(HERE)
        g.save(admission,{'native':models,'worker_manifest':manifest})
        g.save(out/'grant.json',{'native_sha256':g.sha(admission)})
        events.append({'reason':'build-finished','success':True})
        raw=''.join(json.dumps(e)+'\n' for e in events);rows=[];start=1
        for i,order in enumerate(g.P['order'],1):
            ns={}
            for j,arm in enumerate(order,1):
                d=out/f'{i:02d}-{j}-{arm}';d.mkdir();q=d/'ordinary';f=d/'unchanged';q.mkdir();f.mkdir()
                time=100 if arm=='B' else 65;ns[arm]=time
                g.save(q/'clock.json',{'returncode':0,'argv':g.P['command'],'elapsed_ns':time,'start':start,'stop':start+time});start+=time+1
                (q/'stdout').write_bytes(b'');(q/'stderr').write_text('Finished\n')
                (q/'e2e-list').write_bytes(listing);(q/'e2e-list.stderr').write_bytes(b'');(f/'e2e-list').write_bytes(listing)
                g.save(d/'first-78-registry.json',registry);g.save(f/'registry-native.json',registry)
                g.save(d/'first-110.json',paths);g.save(f/'physical.json',procs);g.save(f/'products.json',p);(f/'stdout').write_text(raw)
                ident={'block':i,'slot':j,'arm':arm,'image':models['subjects'][arm]}
                g.save(d/'start.json',dict(ident,native_binding=g.sha(admission)))
                g.save(d/'verified.json',dict(ident,elapsed_ns=time,registry_78=g.sha(d/'first-78-registry.json'),first_110=g.sha(d/'first-110.json'),follow_110=g.digest(paths),
                    follow_roster=g.summary(p),follow_counts=p['counts'],follow_fresh=563,
                    stdout=g.sha(q/'stdout'),stderr=g.sha(q/'stderr'),diagnostics={}))
            rows.append({'block':i,'order':order,'ns':ns,'matching_raw':110,'raw_differences':{}})
        g.save(out/'pairs.json',rows);g.save(out/'result.json',evaluate(g.P,rows))
        g.save(out/'complete.json',{'admission':g.sha(admission),'plan':manifest,'rows':g.sha(out/'pairs.json'),'analysis':g.sha(out/'result.json')})
        receipt=run(out,admission);assert receipt['verified_clocks']==48 and receipt['raw_crossarm_comparisons']==2640
        bad=next(out.glob('01-1-*/first-110.json'));p0=g.read(bad);p0['0']='e'*64;g.save(bad,p0)
        try:run(out,admission)
        except (AssertionError,ValueError):pass
        else:raise RuntimeError('Corrupt synthetic raw output accepted')
    return {'synthetic_clocks':48,'synthetic_raw_comparisons':2640,'known_reduction_pct':35,'changed_raw_result_rejected':True,'actual_cargo_executions':0}


if __name__=='__main__':
    print(json.dumps(test(),indent=2,sort_keys=True))

"""Exercise the entire 48-slot offline reader with generated records, including a corrupt output."""
from pathlib import Path
import json
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import guards as g
import native_registration as nr
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
        models['native_catalog']={'plan_ref':'a'*40,'catalog_result_ref':'b'*40,'ci_sha256':'c'*64,'historical_occurrences':297,'fresh_occurrences':297,
            'linked_targets':50,'exact_others':60,'widths':list(range(1,17)),'prior_failure_sha256':g.P['stopped_v2']['first_failure_sha256'],
            'registered_catalog_sha256':'d'*64,'native_protocol_ref':nr.SOURCE_REF,'native_protocol_manifest':nr.SOURCE_MANIFEST,'literal_recipes':297}
        models['native_catalog'].update(native_bootstrap_ref=nr.boot.BOOT,native_bootstrap_manifest=nr.boot.BOOT_MANIFEST,
            original_native_verifier_sha256=nr.boot.VERIFIER,bootstrap_startup_sha256=nr.boot.STARTUP_SHA,v3b_wall_ref=nr.boot.WALL_B,
            v3b_wall_manifest=nr.boot.WALL_B_MANIFEST,retained_occurrences=50,new_occurrences=249,native_continuation_ref=nr.HISTORICAL['continuation_ref'],
            native_continuation_manifest=nr.HISTORICAL['continuation_sha256'],stopped_native_ref=nr.HISTORICAL['stopped_evidence_ref'],
            stopped_native_manifest=nr.HISTORICAL['stopped_evidence_sha256'])
        manifest=g.manifest(HERE)
        g.save(admission,{'native':models,'worker_manifest':manifest})
        grant={'native_sha256':g.sha(admission),'go':'score exact v3c 24 fresh pairs','published_plan':'a'*40,'published_catalog':'b'*40,
               'published_native':'c'*40,'ci_sha256':'c'*64,'h5_clear':True,'other_host_measurement':False,'ci_review':'accepted','plan_manifest':manifest}
        published={'plan_ref':'a'*40,'catalog_ref':'b'*40,'admission_ref':'c'*40,'plan_manifest':manifest,
                   'admission_sha256':g.sha(admission),'catalog_publication_sha256':'d'*64,'ci_sha256':'c'*64}
        g.save(out/'grant.json',grant);g.save(out/'admission-publication.json',published)
        changes=[({'published_plan':nr.boot.WALL_B},{}),({'published_catalog':nr.boot.BOOT},{}),({'published_native':g.P['stopped_v2']['result_ref']},{}),({'published_plan':'b'*40},{}),
                 ({'published_native':nr.SOURCE_REF},{}),({'h5_clear':False},{}),({'ci_sha256':'a'*64},{}),
                 ({},{'admission_sha256':'a'*64}),({},{'catalog_publication_sha256':'a'*64}),
                 ({'published_plan':nr.WALL_PARENT},{}),({'published_catalog':nr.HISTORICAL['continuation_ref']},{}),
                 ({'published_native':nr.HISTORICAL['stopped_evidence_ref']},{})]
        for counterfeit,record in changes:
            try:nr.publication_grant(grant|counterfeit,published|record,models,manifest,g.sha(admission),g.P['stopped_v2'])
            except ValueError:pass
            else:raise AssertionError('invalid native, publication or scoring grant was accepted')
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
    return {'synthetic_clocks':48,'synthetic_raw_comparisons':2640,'known_reduction_pct':35,'changed_raw_result_rejected':True,
            'invalid_grants_rejected':len(changes),'actual_cargo_executions':0}


if __name__=='__main__':
    print(json.dumps(test(),indent=2,sort_keys=True))

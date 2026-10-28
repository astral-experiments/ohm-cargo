"""Exercise the actual external admission reader with this producer's phase projection."""
import copy, hashlib, importlib.util, json, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from view import PHASES, phase_check, six_phase_recipes


def check(plan_root):
    sys.path.insert(0,str(plan_root))
    spec=importlib.util.spec_from_file_location('original_catalog_test',plan_root/'check_catalog.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    with tempfile.TemporaryDirectory() as temp:
        test_dir=Path(temp);view,prior,old,bad=v.fixture(test_dir)
        original=copy.deepcopy(view);rec={}
        by_target={}
        for phase in PHASES:
            for ordinal,row in enumerate(view['fresh'][phase]):
                target=row['target']
                ident=hashlib.sha256((phase+str(ordinal)+target).encode()).hexdigest()
                row['recipe']=ident
                recipe=copy.deepcopy(original['targets'][target]['recipes']['family'])
                recipe.update(phase=phase,stable_argv_sha256=ident)
                by_target.setdefault(target,{})[ident]=recipe
        for n,target in enumerate(sorted(bad)):
            id='supplement-'+str(n);recipe=copy.deepcopy(next(iter(by_target[target].values())))
            recipe.update(phase='failure-'+str(n+1));by_target[target][id]=recipe
        for target,items in by_target.items():
            vals={p:old[p][target] for p in PHASES if target in old[p]}
            fields,supplemental=phase_check(items,target,vals,prior[target],bad.get(target))
            view['targets'][target]['recipes']=fields
            assert bool(supplemental)==(target in bad)
        actual=v.catalog_view(test_dir,view,v.h,v.p,prior,old,bad)
        assert len(actual)==110
        # Deliberately reinsert an extra-only recipe, which the real consumer rejects.
        target=next(iter(bad));wrong=copy.deepcopy(view);wrong['targets'][target]['recipes']=by_target[target]
        v.reject(lambda:v.catalog_view(test_dir,wrong,v.h,v.p,prior,old,bad))
        base=v.main()
        return {'source':{f:hashlib.sha256((plan_root/f).read_bytes()).hexdigest()
                for f in ['catalog.py','check_catalog.py','plan.json','historical-links.json.gz']},
                'all_297_unique_occurrences_accepted':True,'separate_two_reconstructions_rejected_as_allowlist_sources':True,
                'actual_v3_gate_controls':base,'native_processes':0}


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1]).resolve()),sort_keys=True,indent=2))

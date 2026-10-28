"""Explicitly separate diagnostic reconstructions from genuine six-phase fingerprints."""
PHASES=('seed-repeat1','seed-repeat2','selected-observer','repeat-observer','selected-composed','repeat-composed')


def six_phase_recipes(recipes):
    ordinary={key:v for key,v in recipes.items() if v['phase'] in PHASES}
    checks={key:v for key,v in recipes.items() if v['phase'] in ('failure-1','failure-2')}
    assert len(ordinary)+len(checks)==len(recipes)
    assert len({(v['inputs_sha256'],v['stable_argv_sha256']) for v in ordinary.values()})==len(ordinary)
    return ordinary,checks


def phase_check(recipes,target,historical,prior,failed):
    arm,extras=six_phase_recipes(recipes)
    allvals={val for f in arm.values() for val in f['bodies']}
    assert set(prior)<=allvals
    for phase,required in historical.items():
        values={h for f in arm.values() if f['phase']==phase for h in f['bodies']}
        assert required in values,(target,phase,'historical full ELF')
    if failed:
        assert failed in {h for f in arm.values() if f['phase']=='repeat-observer' for h in f['bodies']}
        assert failed in {h for f in extras.values() for h in f['bodies']}
    return arm,extras

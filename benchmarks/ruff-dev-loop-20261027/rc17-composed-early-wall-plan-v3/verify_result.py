"""Reconstruct every recorded time, order, independent listing and 110 physical output hashes."""
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from analysis import evaluate
import guards as g
import native_registration
from runner import top_diagnostics


def run(results,admission):
    complete=g.read(results/'complete.json');guard=g.read(admission);models=guard['native']
    assert g.sha(admission)==complete['admission'] and complete['plan']==guard['worker_manifest']==g.manifest(HERE)
    grant=g.read(results/'grant.json');catalog=guard['native']['native_catalog']
    native_registration.publication_grant(grant,g.read(results/'admission-publication.json'),models,guard['worker_manifest'],g.sha(admission),g.P['stopped_v2'])
    assert catalog['historical_occurrences']==catalog['fresh_occurrences']==297 and catalog['linked_targets']==50 and catalog['exact_others']==60
    assert catalog['widths']==list(range(1,17)) and catalog['prior_failure_sha256']==g.P['stopped_v2']['first_failure_sha256']
    assert set(f.name for f in results.iterdir() if f.is_dir())=={f'{i:02d}-{j}-{a}' for i,p in enumerate(g.P['order'],1) for j,a in enumerate(p,1)}
    rows=[];stop=0;all_exact=0
    for i,order in enumerate(g.P['order'],1):
        outputs={};times={}
        for j,a in enumerate(order,1):
            d=results/f'{i:02d}-{j}-{a}';clockdir=d/'ordinary';follow=d/'unchanged'
            b=g.read(d/'start.json');v=g.read(d/'verified.json');t=g.read(clockdir/'clock.json')
            assert (v['block'],v['slot'],v['arm'])==(i,j,a) and (b['block'],b['slot'],b['arm'])==(i,j,a)
            assert b['image']==v['image']==models['subjects'][a] and b['native_binding']==complete['admission']
            assert t['returncode']==0 and t['argv']==g.P['command'] and stop<t['start']<t['stop']
            assert t['stop']-t['start']==t['elapsed_ns']==v['elapsed_ns']
            stop=t['stop'];times[a]=t['elapsed_ns']
            assert not (clockdir/'stdout').read_bytes()
            for name in ('stdout','stderr'):
                assert g.sha(clockdir/name)==v[name]
            assert g.sha(clockdir/'e2e-list')==g.sha(follow/'e2e-list')==models['listing_sha256']
            assert not (clockdir/'e2e-list.stderr').read_bytes()
            assert g.sha(d/'first-110.json')==v['first_110'];outputs[a]=g.read(d/'first-110.json')
            registry=g.read(d/'first-78-registry.json')
            assert len(registry)==78 and g.digest(registry)==models['registry_sha256']
            assert g.sha(d/'first-78-registry.json')==v['registry_78'] and registry==models['registry']==g.read(follow/'registry-native.json')
            p=g.read(follow/'products.json')
            assert g.digest(p['native'])==v['follow_110'] and g.summary(p)==v['follow_roster']==models['roster']
            assert set(p['exes'])<=set(p['native']) and len(p['exes'])==102 and p['units']==619
            assert p['fresh']==v['follow_fresh'] and p['counts']==v['follow_counts']
            assert g.digest(sorted(g.row_roster(g.read(follow/'physical.json')).items()))==models['repeat_roster']
            assert top_diagnostics((clockdir/'stderr').read_text(),p)==v['diagnostics']
            for dataset in (p['native'],outputs[a]):g.check_raw(dataset,models['allowed'])
            events=[json.loads(line) for line in (follow/'stdout').read_bytes().splitlines()]
            g.cargo_roster(events,p)
        b,c=outputs['B'],outputs['C']
        eq=sum(b[key]==c[key] for key in b);all_exact+=eq
        rows.append(dict(block=i,order=order,ns=times,matching_raw=eq,raw_differences={key:[b[key],c[key]] for key in b if b[key]!=c[key]}))
    assert rows==g.read(results/'pairs.json') and g.sha(results/'pairs.json')==complete['rows']
    scores=evaluate(g.P,rows)
    assert scores==g.read(results/'result.json') and g.sha(results/'result.json')==complete['analysis']
    return dict(verified_pairs=len(rows),verified_clocks=len(rows)*2,only_timed_endpoint='first-selection',
                raw_crossarm_comparisons=110*24,raw_exact=all_exact,raw_qualified_variants=110*24-all_exact,
                verified_listings=2*48,test_bodies_timed=0,statistics=scores)


if __name__=='__main__':
    print(json.dumps(run(Path(sys.argv[1]),Path(sys.argv[2])),sort_keys=True,indent=2))

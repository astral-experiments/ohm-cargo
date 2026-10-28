"""Recompute the reported correlations, queue comparisons and source coverage."""
import hashlib
import json
from pathlib import Path
import statistics

here=Path(__file__).resolve().parent
read=lambda n:json.loads((here/n).read_bytes())
graph=read('release-queue.json');assert (graph['graph_units'],graph['edges'],graph['matched'],graph['unmatched'])==(689,29419,50,[])
assert hashlib.sha256((here/'release-queue.json').read_bytes()).hexdigest()=='a39c8a66a4a2674ed087e8ad997e1463b73bb0e6ef865324b9d196919a3bb2b5'
rows={r['file']:r for r in graph['records']};assert len(rows)==50 and all(r['priority']==200 and set(r['complete_edges'])=={'All'} for r in rows.values())
for r in rows.values():
    assert r['last_full_dependency_or_start']<=r['first_dispatch_after_all_prerequisites']<=r['start']<r['end']
    allowed={other['file'] for other in rows.values() if other['priority']==r['priority'] and other['size']<r['size'] and r['first_dispatch_after_all_prerequisites']<=other['start']<r['start']}
    assert sorted(allowed)==sorted(r['smaller_same_priority_dispatched_first'])
lens=[len(r['smaller_same_priority_dispatched_first']) for r in rows.values()];assert sum(bool(i) for i in lens)==43 and sum(lens)==457
for package,target,n,seconds in [('ty_ide','ty_ide',42,2.488),('ty_project','ty_project',46,2.763),('ty_server','ty_server',29,1.869),('ty_server','e2e',36,2.060)]:
    r,=[r for r in rows.values() if r['package']==package and r['target']==target];assert (len(r['smaller_same_priority_dispatched_first']),round(r['start']-r['first_dispatch_after_all_prerequisites'],3))==(n,seconds)
census=read('native-processes.json');events=census['wild'];assert census['root_exit']==0 and census['all_children_exit_zero']
assert census['counts']=={'rustc-full':1,'rustc-link-only':50,'gcc':50,'collect2':50,'stock-wild':50} and {e['file'] for e in events}==set(rows)
assert all(e['size']==rows[e['file']]['size'] and e['started_ns']<e['exited_ns'] for e in events)
native=statistics.correlation([e['size'] for e in events],[e['exited_ns']-e['started_ns'] for e in events]);assert round(native,3)==0.984
t=read('cargo-timings.json');runs=t['runs'];coeff=[]
for r in runs:
    assert (r['units'],r['fresh'],r['exit'])==(619,563,0)
    a=r['native_units'];assert len(a)==50 and {u['file'] for u in a}==set(rows) and all(u['size']==rows[u['file']]['size'] for u in a)
    coeff.append(round(statistics.correlation([u['size'] for u in a],[u['duration_seconds'] for u in a]),3))
assert coeff==[0.876,0.984,0.973,0.987]
s=read('source-survey.json');assert (s['branches'],s['all_state_prs'],s['distinct_tips'],len(s['product_tips']),len(s['other_tips']),len(s['blob_findings']))==(283,228,287,274,13,20)
for files in s['product_tips'].values():
    j,=[s['blob_findings'][i] for i in files.values() if s['blob_findings'][i]['type']=='job_queue'];assert j['fixed_100'] and not j['previous_artifact_size']
print(f'50 native jobs, 43 waiting behind smaller jobs, 457 ordered pairs. Wild correlation {native:.6f}. Cargo correlations {coeff}.')

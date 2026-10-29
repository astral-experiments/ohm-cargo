"""Replay the package admission, raw thread ledger, historical oracle, and real native choices."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,path=line.split('  ',1)
    assert sha((root/path).read_bytes())==digest,path
def zipped(name):
    return json.loads(gzip.decompress((root/name).read_bytes()))
q=zipped('qualified.json.gz')
study=json.loads((root/'admission.json').read_bytes())
assert q['base']['source']==study['ruff'] and q['base']['physical']['cargo']==study['cargo']
assert q['source']['admission.json']==sha((root/'admission.json').read_bytes()) and q['source']['amend-accounting.json']==sha((root/'amend-accounting.json').read_bytes())
assert q['base']['affinity']==[24,25,26,27] and q['base']['registry']==498
cal=q['calibration']
assert sha((root/'counter/edge-counter.c').read_bytes())==cal['source']
assert 3990000<cal['measured_thread_delta']<4010000 and abs(cal['multi_fork_delta'])<100000 and cal['eight_child_assigned_delta']==32000000
for mode in ('default','yes'):
    assert len(q['fresh_cold'][mode+'-cold']['dirty'])==147 and q['fresh_cold'][mode+'-settled']['dirty']==[]
    for label in ('fresh-H','edit-P','fresh-P','restore-H'):
        x=q['observations'][mode+'-v2-dr-'+label];c=x['counter'];lines=[s.split() for s in x['raw_counter']['data']]
        assert lines[0][0]=='B' and lines[-1]==['P',lines[0][1]] and x['command']['rc']==0
        starts=sorted(i[1] for i in lines if i[0]=='T');ends=[i for i in lines if i[0]=='F']
        assert starts==sorted(i[1] for i in ends) and len(set(starts))==len(starts)==c['threads']
        regions=[[int(z) for z in i[1:]] for i in lines if i[0]=='R']
        assert all(int(r[3])==int(r[4])==sum(k[0]==int(r[1]) for k in regions) for r in ends)
        assert (sum(int(i[2]) for i in ends),sum(r[1] for r in regions),len(regions))==(c['instructions'],c['inclusive'],c['prepare_calls'])
        assert [sum(i[j] for i in regions) for j in (3,4,5,6)]==[c[k] for k in ('edges','clones','lookups','inserts')]
        assert c['by_region']==[r[1:] for r in regions] and c['instructions']>100000000
        if label.startswith('fresh'):
            assert c['prepare_calls']==c['inclusive']==0
        else:
            assert sorted((r[2],*r[3:]) for r in regions)==[(1,16,16,16,16),(1,26,26,26,26),(1,26,26,26,26)]
            assert 0<c['inclusive']/c['instructions']<0.001
        assert x['native_postcheck']['units']==147 and not x['native_postcheck']['dirty']
        assert x['caller']['verdict']==('accepted' if label.endswith('P') else 'rejected: Star import cannot be parenthesized')
        assert x['caller']['products']['fixtures']['tests']==(557 if label.endswith('P') else 558)
        assert x['caller']['products']['generate_inline_tests']['tests']==1
    for phase in ('edit-P','restore-H','repeat-P','repeat-H'):
        r=q['native']['real-'+mode+'-'+phase];u=r['typed'];assert r['command']['rc']==0 and u['units']==147
        assert len(r['raw_exec_trace'])>0
        if phase.startswith('repeat'):
            assert not r['processes'] and u['dirty']==[]
        else:
            want={'ruff_python_parser':'full rustc','fixtures':'full rustc' if mode=='default' else 'cached rustc','generate_inline_tests':'full rustc' if mode=='default' else 'cached rustc'}
            assert set(u['dirty'])==set(want) and {x['crate']:x['kind'] for x in r['processes'] if x['kind']!='stock linker'}==want
            links=[x for x in r['processes'] if x['kind']=='stock linker'];assert len(links)==2 and all(x['exec_sha']==q['base']['physical']['wild'] for x in links)
            assert all(x['exec_sha']==q['base']['physical']['rustc'] for x in r['processes'] if x['kind']!='stock linker')
            assert r['caller']['verdict']==('accepted' if phase.endswith('P') else 'rejected: Star import cannot be parenthesized')
for phase in ('fresh-H','edit-P','fresh-P','restore-H'):
    a=q['observations']['default-v2-dr-'+phase]['caller']
    b=q['observations']['yes-v2-dr-'+phase]['caller']
    assert {k:v['elf'] for k,v in a['products'].items()}=={k:v['elf'] for k,v in b['products'].items()}
for mode in ('default','yes'):
    h=q['observations'][mode+'-v2-dr-fresh-H']['caller']['products']
    restored=q['observations'][mode+'-v2-dr-restore-H']['caller']['products']
    assert h==restored
graph=q['logical_graph'];assert sorted((x['target'],len(x['deps'])) for x in graph['matched'])==[('fixtures',26),('generate_inline_tests',26),('ruff_python_parser',16)] and all(d['mode']=='build' and d['kind']==d['crate_types']==['lib'] for x in graph['matched'] for d in x['deps'])
assert q['exceptions']['initial_destination']['rc']==101 and q['exceptions']['first_dirty_accounting']['physical_cargo']['rc']==0 and q['exceptions']['first_dirty_accounting']['observer_exit']==1
orig=q['exceptions']['first_dirty_accounting']['raw_counter']['data']; assert len([r for r in orig if r.startswith('F ')])>len([r for r in orig if r.startswith('T ')])
s=zipped('upstream.json.gz');assert [s[k] for k in ('branches','prs','heads_and_prs')]==[293,237,297] and len(s['excluded'])==13 and len(s['members'])==284 and len(s['analyzed'])==109
assert collections.Counter(s['analyzed'][v]['mode'] for v in s['members'].values())=={'unconditional build_runner.unit_deps':269,'absent':15}
assert set(s['with_new_consumer'])=={'5394ce8817e224971230b80a9066cc28d504ff94','8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b','a8f0c9aa0412aa259c686416a48aa8d2cf92da72'}
for k in ('default-v2-dr-edit-P','default-v2-dr-restore-H'):
    a=q['observations'][k]['counter'];print(k,a['inclusive'],a['instructions'],'%.5f%%'%(100*a['inclusive']/a['instructions']))
print('Verified eight instruction observations, eight kernel exec controls, both native-semantics histories and all public source dispositions.')

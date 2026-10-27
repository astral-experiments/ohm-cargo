"""Verify both the frozen six-contrast randomized design and its independent, unscored receipt checks."""
from pathlib import Path
from collections import Counter
from itertools import permutations
import hashlib,importlib.util,json
p=Path(__file__).resolve().parent;load=lambda name:json.loads((p/name).read_bytes())
a=load('prospective.json');f=load('fixed-width-plan.json');e=load('h1-qualification.json')
assert set(f['primary_endpoints'])=={'parser','stdlib','wasm-only'} and f['baseline_rustc']==e['subjects']['A']['rustc_driver_sha256']
for name in f['primary_endpoints']:
 edit=f['edits'][name];assert edit['patch_sha256']==hashlib.sha256((p/(name+'.patch')).read_bytes()).hexdigest()
 assert [[('parent' if v=='A' else 'candidate') for v in order if v!='B'] for order in f['orders'][name]]==a['endpoints'][name]['order']
for k,order in f['orders'].items():assert Counter(map(tuple,order))=={v:3 for v in permutations('ABC')}
for arm in 'ABC':
 assert f['arms'][arm]['cargo']==e['subjects'][arm]['cargo_sha256'] and f['baseline_rustc']==e['subjects'][arm]['rustc_driver_sha256']
 n=e['native'][arm]['negative_cases'];assert n['activated']['execution_rc']==[101,0]
 assert len(n['loader']['requested_files'])==2 and n['actual_gcc_specs']['marker']=='0000000000000089'
 assert n['earlier-library']['rc']==n['resolved-library']['rc']==101
 assert n['layout']['requested_bytes']>1000 and all(min(n[f'user-{ix}']['requested_output_bytes'])>30 for ix in range(2))
 assert n['collect2']['elf']==e['native']['A']['negative_cases']['collect2']['elf'] and n['ld.bfd']['elf']==e['native']['A']['negative_cases']['ld.bfd']['elf']
for arm in 'BC':
 s=e['scope'][arm];st=s['stdlib'];assert len(st['first-dirty']['rustc_crates'])==14 and len(st['first-dirty']['wild_outputs'])==4 and len(st['first-dirty']['API_explicitly_one_worker'])==2 and st['first-dirty']['API_full_or_link_only']==['full','full']
 for phase in ('trained-edit','trained-return','trained-return2'):
  r=st[phase];assert (len(r['rustc_crates']),len(r['wild_outputs']))==((14,4) if arm=='B' else (12,2))
  assert not st[phase+'-fresh']['rustc_crates'] and st[phase]['raw_ELFs']==st['independent-force']['raw_ELFs']==st['first-dirty']['raw_ELFs']
 assert st['independent-api-cold']['API_full_or_link_only']==['full','full'] and not st['independent-api-cold']['API_explicitly_one_worker']
 assert st['independent-force']['API_full_or_link_only']==['full','full'] and len(st['independent-force']['API_explicitly_one_worker'])==2
 for ph in ('edit','restore'):
  r=s['parser'][ph];assert (len(r['rustc_crates']),len(r['wild_outputs']))==((5,4) if arm=='B' else (3,2))
 assert e['native'][arm]['all_actual_commands']==44
assert e['scope']['B']['stdlib']['independent-force']['raw_ELFs']==e['scope']['C']['stdlib']['independent-force']['raw_ELFs']
assert 'active: test' in e['direct']['C']['rustc']['cases']['edit']['tests']
spec=importlib.util.spec_from_file_location('analysis',p/'analyze.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
o=f['orders']['stdlib'];null=[dict(A=1.,B=1.,C=1.) for _ in o];slot=[dict(zip(order,[1.,2.,4.])) for order in o];effect=[dict(A=2.,B=2.,C=1.) for _ in o]
for ctl in 'AB':
 assert m.evaluate(o,null,ctl,42)['exact_two_sided_p']==m.evaluate(o,slot,ctl,42)['exact_two_sided_p']==1
 assert m.evaluate(o,effect,ctl,42)['exact_two_sided_p']==2/8000
print('All native release controls and the three endpoint, six contrast randomization design passed.')

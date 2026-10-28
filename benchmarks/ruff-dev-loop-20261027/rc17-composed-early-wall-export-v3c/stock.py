"""Verify terminal aggregate, every recorded native status, raw ELF shape and portable path digest."""
from pathlib import Path
import collections,gzip,hashlib,json,re,sys
D=Path(__file__).resolve().parent
def decode(f):return json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_bytes())
def digest(o):return hashlib.sha256(json.dumps(o,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def whole(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def hex64(x):assert bool(re.fullmatch('[a-f0-9]{64}',x))
def verify(directory=None,verifier_file=None):
 global D
 if directory is not None:D=Path(directory).resolve()
 w=decode(D/'wall-view.json.gz');term=decode(D/'terminal.json');verification=Path(verifier_file) if verifier_file is not None else D/'independent.json';summary=decode(verification)
 assert hashlib.sha256(gzip.decompress((D/'wall-view.json.gz').read_bytes())).hexdigest()==(D/'wall-view.sha256').read_text().split()[0]
 assert w['terminal']['sha256']==whole(D/'terminal.json') and w['independent_verification']['sha256']==whole(verification)
 assert w['cpu']==list(range(16)) and w['jobs']==8 and w['widths']==list(range(1,17))
 assert w['wild_source']=='e856d81f6683cad80b9fe0ebf1a0c3c403c6fe11' and w['wild_sha256']=='0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5'
 fresh=collections.Counter();historical=collections.Counter();incidents=collections.Counter()
 for phase,rows in w['fresh'].items():
  for j in rows:
   assert j['exit']==0 and j['wild_sha256']==w['wild_sha256'];fresh[phase,j['target'],j['kind']]+=1
  for j in w['historical'][phase]:historical[phase,j['target'],j['kind']]+=1
 assert w['schema']==1 and w['native_ref']=='a75e5f17c07081cfcc9fabfcccd7a5022528641b'
 assert sum(fresh.values())==297 and historical==fresh
 commands=decode(D/'commands.json.gz')
 assert set(commands)==set(w['fresh'])
 for phase,row in commands.items():
  seed=phase.startswith('seed')
  assert row['units']==(617 if seed else 619) and row['fresh']==563 and row['exes']==(100 if seed else 102)
  assert len(row['native'])==(108 if seed else 110) and row['status']==0
  assert row['counts']['wild']==sum(v for (p,_,_),v in fresh.items() if p==phase)
 known={k for k in w['targets']};assert len(known)==50 and set(term)==known
 stock_n=0;counts=collections.Counter();allb=set();by_targets={}
 for file in sorted((D/'links').glob('*.json.gz')):
  target=decode(file);t=target['target'];known.remove(t)
  assert w['targets'][t]['evidence']['sha256']==target['raw_private_evidence']
  vals=target['exact_fields_and_unchanged_ranges'];ns={(v['normalized'],v['bytes'],digest(v['ranges'])) for v in vals.values()};assert len(ns)==1
  for h,v in vals.items():
   hex64(h);assert v['sha256']==h and v['fields']['build_id'][1]==v['build_id'] and v['rodata_entsize']==int.from_bytes(bytes.fromhex(v['fields']['rodata'][1]),'little')
   bounds=[[a,b] for a,b,hh in v['ranges']];assert len(bounds)==3
   for a,b,hh in v['ranges']:hex64(hh)
   for off,b in v['fields'].values():bounds.append([off,off+len(bytes.fromhex(b))])
   bounds.sort();assert bounds[0][0]==0 and bounds[-1][1]==v['bytes'] and all(a[1]==b[0] for a,b in zip(bounds,bounds[1:]))
  for key,recipe in target['recipes'].items():
   hex64(key); rows=recipe['widths'];assert sorted(q['width'] for q in rows)==list(range(1,17)) and len(rows)==16
   assert set(recipe['whole_bodies'])=={q['plain_sha256'] for q in rows} and set(recipe['whole_bodies'])<=set(vals)
   assert recipe['raw_default'] in recipe['whole_bodies'] and len(recipe['stock_processes'])==33
   inputs=recipe['resolved_positive_and_literal_inputs_as_recorded']
   for original,resolved,size,h in inputs:
    hex64(original);hex64(resolved);hex64(h);assert size>=0
   assert len(inputs)==recipe['positive_names'] and sum(i[2] for i in inputs)==recipe['positive_bytes'] and digest(inputs)==recipe['public_input_projection_sha256']
   for row in rows:
    assert row['plain_exit']==row['depfile_exit']==0 and row['plain_sha256']==row['depfile_sha256']
    for p in (row['plain_pid'],row['depfile_pid']):hex64(recipe['stock_processes'][str(p)])
   hex64(recipe['symbols_object_sha256'])
   phase=recipe['phase'];counts[phase]+=1;stock_n+=33;allb.update(recipe['whole_bodies'])
   if phase.startswith('failure-'):
    assert key not in w['targets'][t]['recipes']; see=decode(D/'reconstructions'/(phase+'.json'));assert set(see['raw'])==set(recipe['whole_bodies'])
   else:
    view=w['targets'][t]['recipes'][key]
    assert digest(recipe['stock_processes'])==view['stock_trace_set_sha256'] and recipe['exact_physical_input_json_sha256']==view['raw_input_file']['sha256']
    assert recipe['ordinal']==view['occurrence'] and view['phase']==phase and [(x['width'],x['plain_exit'],x['depfile_exit'],x['plain_sha256'],x['depfile_sha256']) for x in view['widths']]==[(x['width'],x['plain_exit'],x['depfile_exit'],x['plain_sha256'],x['depfile_sha256']) for x in recipe['widths']]
    assert all(re.fullmatch('[0-9a-f]{64}',x) for x in recipe['all_ordered_argv_fields_sha256']) and recipe['all_ordered_argv_fields_sha256']
    assert view['stable_argv_sha256']==recipe['raw_argv_sha256'] and set(view['bodies'])==set(recipe['whole_bodies'])
    match,=[a for a in w['fresh'][phase] if a['target']==t and a['recipe']==key];assert match['raw_sha256']==recipe['raw_default']
    incidents[phase,t,match['kind']]+=1
  by_targets[t]=len(vals)
 assert not known and incidents==fresh and len(allb)==summary['raw_bodies'] and stock_n==9867
 return {'native_occurrences':sum(counts.values()),'phases':dict(sorted(counts.items())),'stock_wild_processes':stock_n,
   'linked_targets':len(by_targets),'retained_raw_elf_hashes':len(allb),
   'distinct_raw_file_hashes_per_target':dict(sorted(collections.Counter(by_targets.values()).items())),'clocks':0}
if __name__=='__main__':print(json.dumps(verify(),indent=2,sort_keys=True))

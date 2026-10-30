import gzip
import hashlib
import json
from pathlib import Path
BASE=Path(__file__).resolve().parent
def digest(v):return hashlib.sha256(v).hexdigest()
def check():
 bindings={n:(size,raw,packed) for n,size,raw,packed in json.loads((BASE/'raw-bindings.json').read_bytes())}
 sets=[]
 for label,want in [('candidate',112),('signed19',56)]:
  fn=label+'-projection.json.gz';packed=(BASE/fn).read_bytes();blob=gzip.decompress(packed);assert bindings[fn]==(len(blob),digest(blob),digest(packed))
  data=json.loads(blob);assert data['raw_terminal_sha256']==bindings[label+'-native.json.gz'][1]
  assert len(data['per_visit_sha256'])==data['counts']['commands']==want
  for ability,entries in data['source_hashes'].items():
   location=BASE/'fixture'/ability/'source'
   assert {str(p.relative_to(location)):digest(p.read_bytes()) for p in location.rglob('*') if p.is_file()}==entries
  verdict={};elf=set();scored=0
  for contract,cases in data['cohort'].items():
   v={};verdict[contract]=v
   for phase,n in [('original',17),('insert',29),('overwrite',41),('malformed',None),('remove',17),('repair',73),('restore',17)]:
    rr=cases[phase];assert rr['force']['full_elf']==rr['clean']['full_elf']
    for mode,r in rr.items():
     natural=mode in ('ordinary','repeat')
     current=n if contract.startswith('declared-') or not natural else 17
     assert r['exit']==(0 if current is not None else 101)
     assert r['values']==({k:current for k in ('first_probe','second_probe')} if current is not None else {})
     assert len(r['full_elf'])==(2 if current is not None else 0)
     if not natural or (contract.startswith('declared-') and (mode=='ordinary' or current is None)) or (phase=='original' and mode=='ordinary'):assert set(r['links'])=={'first_probe','second_probe'}
     else:assert not r['links']
     elf.update(r['full_elf'].values());scored+=1
    v[phase]=[(m,r['exit'],r['values'],len(r['links'])) for m,r in sorted(rr.items())]
  assert scored==want and len(elf)==data['unique_reexecuted_elf']
  if label=='candidate':
   assert len(verdict)==4 and verdict['declared-default']==verdict['declared-off'] and verdict['undeclared-default']==verdict['undeclared-off']
  sets.append(verdict)
  print(label,data['counts'],data['raw_terminal_sha256'])
 assert all(sets[0][k]==v for k,v in sets[1].items())
if __name__=='__main__':check()

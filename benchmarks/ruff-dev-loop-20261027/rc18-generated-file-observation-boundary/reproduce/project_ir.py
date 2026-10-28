"""Reduce a terminating single-event Callgrind profile to the selected Cargo functions."""
import hashlib,json,re,sys
from pathlib import Path
NAMES=['cargo::compiler::fingerprint::worktree::result_digest','cargo::compiler::fingerprint::worktree::hash_tree','cargo::compiler::fingerprint::worktree::hash_file','cargo::compiler::fingerprint::read_checksum','cargo::compiler::custom_build::prev_build_output','<cargo::compiler::custom_build::BuildOutput>::parse','<cargo::compiler::custom_build::BuildOutput>::parse_file','cargo::sources::path::list_files']
def extract(p):
 raw=p.read_bytes();lines=raw.decode().splitlines();names={}
 for line in lines:
  m=re.match(r'c?fn=\((\d+)\) (.+)',line)
  if m:names[int(m[1])]=m[2]
 ids={i:name for i,name in names.items()if name in NAMES};out={n:{'incoming':{},'outgoing':{},'local_cost':0}for n in ids.values()}
 fn=cf=None;calls=0
 for line in lines:
  m=re.match(r'(c?fn)=\((\d+)\)',line)
  if m:
   if m[1]=='fn':fn=int(m[2]);cf=None;calls=0
   else:cf=int(m[2])
   continue
  if line.startswith('calls='):calls=int(line.split()[0].split('=')[1]);continue
  m=re.fullmatch(r'(?:[+-]?\d+|\*)\s+(\d+)',line)
  if not m:continue
  cost=int(m[1])
  if calls:
   for which,other,kind in ((fn,cf,'outgoing'),(cf,fn,'incoming')):
    if which not in ids:continue
    row=out[ids[which]][kind].setdefault(ids.get(other,str(other)),[0,0]);row[0]+=calls;row[1]+=cost
   calls=0
  elif fn in ids:out[ids[fn]]['local_cost']+=cost
 for v in out.values():v['inclusive_incoming']=sum(e[1]for e in v['incoming'].values())
 return {'sha256':hashlib.sha256(raw).hexdigest(),'last_totals_ir':int(next(l.split()[1]for l in lines if l.startswith('totals:'))),'executed_ir':int(next(l.split()[1]for l in lines if l.startswith('summary:'))),'events':next(l for l in lines if l.startswith('events:')),'normal_termination':'desc: Trigger: Program termination' in lines,'functions':out}
if __name__=='__main__':print(json.dumps(extract(Path(sys.argv[1])),sort_keys=True,indent=2))

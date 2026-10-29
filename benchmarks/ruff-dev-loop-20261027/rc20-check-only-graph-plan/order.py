"""Deterministic outcome-blind blocked registration."""
import hashlib,json,random,sys
from pathlib import Path
salt='8dc33c9cc641e2b641c5b8e7075652a3e9e1f70b/ec660ad8b5f3327924988ef3daa9e4444106b40e/f240bf849841cf6cb3ffd844db8bd6d6aa0b3026/check-only-graph-v1'
r=random.Random(int.from_bytes(hashlib.sha256(salt.encode()).digest(),'big'))
pairs=[];source_holdout=[]
for i in range(16):
 block=[(s,a)for s in ('old','new')for a in ('AB','BA')];r.shuffle(block)
 for s,a in block:pairs.append({'pair':len(pairs)+1,'block':i+1,'seed':s,'edit':'new' if s=='old' else 'old','case':'chronological' if s=='old' else 'reverse','order':a})
for i in range(8):
 local=['AB','BA'];r.shuffle(local)
 for order in local:source_holdout.append({'pair':65+len(source_holdout),'block':i+1,'seed':'new','edit':'source-only','case':'source-only','order':order})
v={'schema':1,'seed_material':salt,'pairs':pairs+source_holdout}
if __name__=='__main__':print(json.dumps(v,sort_keys=True,indent=2))

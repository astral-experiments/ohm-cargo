from pathlib import Path
import json,hashlib,subprocess,os
D=Path(__file__).resolve().parent;g=['git','-C','/home/dev-user/code/oss/ruff'];base=subprocess.check_output([*g,'rev-parse','93526150df']).decode().strip();idx=D/'private.index';env=dict(os.environ,GIT_INDEX_FILE=str(idx));subprocess.run([*g,'read-tree',base],env=env,check=True)
# Fixed ordering, full historical reverse patch must apply by a standard Git check in the pinned index.
classes={'ty-diagnostic':['362e2aebac','88ee6e53e9','bc28178ddf'],'formatter':['40a62bc699','63cef3f3','b3fb43af25']};selected={};candidates=[]
for topic,ids in classes.items():
 for rev in ids:
  h=subprocess.check_output([*g,'rev-parse',rev+'^{commit}']).decode().strip();diff=subprocess.check_output([*g,'diff','--no-ext-diff','--no-renames','--full-index','--binary',h+'^',h]);c=subprocess.run([*g,'apply','-R','--check','--cached'],input=diff,capture_output=True,env=env);names=subprocess.check_output([*g,'diff','--name-only','--no-renames',h+'^',h]).decode().splitlines();row={'topic':topic,'commit':h,'patch_sha256':hashlib.sha256(diff).hexdigest(),'paths':names,'reverse_check':c.returncode,'stderr':c.stderr.decode()};candidates.append(row)
  if c.returncode==0 and all(any(p.startswith(n) for n in ['crates/ty_python_semantic/'] if topic=='ty-diagnostic') if topic=='ty-diagnostic' else p.startswith('crates/ruff_python_formatter/') for p in names):selected[topic]=row;(D/(topic+'.patch')).write_bytes(diff);break
print(json.dumps({'base':base,'selected':selected,'examined':[(r['commit'][:10],r['reverse_check'],r['paths'][:7],r['stderr'][:120]) for r in candidates]},indent=2));(D/'selection.json').write_text(json.dumps({'base':base,'selected':selected,'candidates':candidates},sort_keys=True,indent=2)+'\n')

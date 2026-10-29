"""Check the real SDK driver and linker in the two traced native common warmups."""
import ast,hashlib,json,re,runpy,sys
from collections import Counter
from pathlib import Path
root=Path(sys.argv[1]);sdk=Path(sys.argv[2]);fn=runpy.run_path(str(root/'runner/native_execs.py'))
def hf(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
rust=hf(sdk/'bin/rustc');physical=(sdk/'lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd').resolve();wild=hf(physical)
frozen=json.loads((root/'enrollment.json').read_bytes());assert frozen['runtime_wild']==wild and frozen['runtime_rustc']==rust
rows=[]
for lane in ('mechanism','wall'):
 for mode in ('build','test'):
  d=root/lane/'results'/('toml-'+mode+'-v1');trace=d/'C/00-prepare.exec'; data=trace.read_bytes();raw=data.decode().splitlines()
  roles=Counter();std=Counter();examples={}
  runtime=json.loads((d/'C/runtime-identity.json').read_bytes()); cfg=json.loads((root/lane/'replay-config.json').read_bytes()); view=Path(cfg['scratch'])/'arena'
  def held(path):
   for prefix in (view/'sdk', view/'ru/toolchains/ohm'):
    if path.is_relative_to(prefix):return sdk/path.relative_to(prefix)
   return path
  assert Path(runtime['rustc'][0])==(sdk/'bin/rustc').resolve() and Path(runtime['ld.bfd'][0])==physical
  for r in fn['native_execs'](data):
   iscc,isld=fn['is_compile'](r),fn['is_link'](r)
   if not (iscc or isld):continue
   match=re.search(r'execve(?:at)?\((?:[^,]+, )?("(?:[^"\\]|\\.)*")',raw[r['lines'][0]-1]); assert match
   original=Path(ast.literal_eval(match[1]));name=r['program']
   if iscc:
    assert held(original).resolve()==(sdk/'bin/rustc').resolve() and hf(held(original))==rust, original
    roles['selected-rustc']+=1
   if isld:
    # The enclosing mounts can have gone. The complete installed linker/driver is still available
    # at the equivalent path through the immutable SDK symlink used by the replay.
    equivalent=held(original)
    assert equivalent.resolve()==physical and hf(equivalent)==wild,(name,original,equivalent,physical)
    roles['selected-stock-Wild']+=1
   std[name]+=1;examples[r['argv_sha256']]=name
  assert roles['selected-rustc']==(1 if mode=='build' else 15)
  assert roles['selected-stock-Wild']==(0 if mode=='build' else 6)
  rows.append(dict(mode=mode,lane=lane,roles=dict(roles),observed_basenames=dict(std),all_native_argv=examples,trace_hash=hf(trace)))
print(json.dumps(dict(expected_rustc=rust,expected_wild=wild,warmup=rows),indent=2,sort_keys=True))

"""Copy native cold products without touching the source target and verify each against the phase hash."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
P=Path('/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027');base=P/'results/cold-ron-v1';st=P/'states/cold-ron-v1';save=P/'results/ron-hashes-supplement-v1';save.mkdir(exist_ok=False);totals={}
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def from_state(path,arm):
 n=Path(path)
 for src,sink in [(P/'native-target','target'),(P/'shared','build')]:
  if n.is_relative_to(src):return arm/sink/n.relative_to(src)
 raise ValueError(path)
for arm in ('whole-trusted','whole-default'):
 dest=save/arm;dest.mkdir();cold=base/arm/'cold';warm=base/arm/'unchanged-1';donors=[st/arm,P/'states/parser/A',P/'states/parser/Stock11'];marked={}
 while not (cold/'raw-native.json').is_file():
  if (P/'cold-ron-v1-recovery-bind/launch.rc').is_file():raise RuntimeError(('stopped',cold))
  time.sleep(2)
 hh=json.loads((cold/'raw-native.json').read_bytes());assert len(hh)==110
 # Try the actual storage first. For already-changed outputs, match bytes from the independent retained stock donors, if available.
 for path,expected in hh.items():
  for donor in donors:
   orig=from_state(path,donor)
   if not orig.is_file() or sha(orig)!=expected:continue
   copied=dest/expected
   if not copied.exists():subprocess.run(['cp','-p','--reflink=auto',orig,copied],check=True)
   if sha(copied)!=expected:copied.unlink();continue
   marked[path]={'sha':expected,'verified_exact_copy':True,'donor':donor.name};break
 missing=set(hh)-marked.keys();totals[arm]={'copied':len(marked),'unavailable_cold_paths':sorted(missing),'paths':marked};(save/'summary.json').write_text(json.dumps(totals,indent=2)+'\n');print(arm,len(marked),'missing',list(missing),flush=True)

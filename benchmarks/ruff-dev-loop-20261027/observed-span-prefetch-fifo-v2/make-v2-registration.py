"""Commit the exact previously failed zero-sample custody and the single permitted protocol amendment."""
from pathlib import Path
import hashlib,json,sys
h=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(n):return json.loads((h/n).read_bytes())
plan=get('ruff-prefetch-registration.json');capture=get('rejected-v1-and-starting-state.json');original=sha(h/'ruff-prefetch-registration.json')
assert original=='9b0e4509b59703a7d6d3f517990067dd0d3b980ed7d97ba98253927099401eae'
assert capture['zero_timed_or_audited'] and capture['v1_queue_rc']==1 and len(capture['active_rustc'])==2 and capture['active_cargo_artifact']['features']==['default','std']
files=sorted(f for f in h.rglob('*') if f.is_file() and not any(n.startswith('.') or n=='__pycache__' for n in f.relative_to(h).parts) and f.name not in ['v2-registration.json','SHA256SUMS'])
j={'protocol':'ruff-sdk-observer-prefetch-fifo-v2-active-unit','registered_before':'All scored full-Ruff v1 and v2 observations were zero. Only v1 fallback training, a fully fresh JSON test anchor, two Rust compiler traces from the previous prerequisites, physical evidence reads and synthetic scope tests precede this registration.',
'original_registration_sha256':original,'original_registration':'https://github.com/astral-sh/ohm-cargo/blob/5f284b2b27f107da422101d772b985a90aef63db/benchmarks/ruff-dev-loop-20261027/observed-span-prefetch-fifo/ruff-prefetch-registration.json',
'original_failure_sha256':capture['v1_failure_sha256'],'starting_state_sha256':sha(h/'rejected-v1-and-starting-state.json'),
'previous_queue_rc':1,'previous_timed_or_audited_commands':0,'scores_inherited':0,'physical_stores':capture['physical_stores'],'source_index_sha256':capture['source_index_sha256'],
'claimed_change':'Scope the sole observed Ron to the verified fresh Cargo output and its corresponding actual prior rustc out-dir; strengthen controls to verify physical bytes and stat identities for both active and passive retained readers. Save the failed run and begin an entirely new 64-command series.',
'procedure':'Preflight clones only private trained Cargo-home proof payloads to new, equally routed homes, preserves the two trained target/shared paths, and requires two zero-work, all-fresh preparations and two structured anchors per endpoint. Prior and active registry input hashes and counts are bound. Independent anchors and ordinary native score require separate publication-bound grants; score also checks the exact four-anchor certificate. The original helper, inherited jobserver/FIFO, wrapper, SDK mutation, exact return-value, terminal output/ELF, full-workspace and retrospective independent-calculation gates continue to apply.',
'workload':plan['workload'] if 'workload'in plan else {'build':['cargo','+ohm','build','--locked','--offline'],'test':['cargo','+ohm','test','--no-run','--locked','--offline']},
'orders':plan['orders'],'subjects':plan['subjects'],'source_files':{str(f.relative_to(h)):sha(f) for f in files}}
for k in ['statistics','analysis','metrics','exclusions','endpoints']:
 if k in plan:j[k]=plan[k]
data=(json.dumps(j,indent=2,sort_keys=True)+'\n').encode();reg=h/'v2-registration.json'
if '--verify' in sys.argv:assert reg.read_bytes()==data
else:
 reg.write_bytes(data);(h/'SHA256SUMS').write_text(''.join(f'{sha(f)}  {f.relative_to(h)}\n' for f in sorted([*files,reg])))
print(hashlib.sha256(data).hexdigest())

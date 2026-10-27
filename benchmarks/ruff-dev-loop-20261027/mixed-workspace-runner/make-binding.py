"""Recreate the fixed source, storage and release-image binding without starting a Ruff process."""
import hashlib
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
base = Path('/home/dev-user/.cache/ohm-233-position-qualified-20261027')
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def get(path):
    return json.loads((here/path).read_bytes())
s = get('proof/subjects.json')
p = get('plan.json')
assert sha(here/'plan.json') == s['registered_plan_sha256']
assert p['base_compiler_driver'] == s['rust_base_driver']
assert p['base_cargo_pgo'] == s['cargo_base_binary']
assert sha(here/'analyze.py') == p['analyzer_sha256']
assert sha(here/'parser.patch') == p['reversed_patch_sha256']
arms = {}
for arm in 'ABC':
    cargo = s['cargo_base_binary' if arm == 'B' else 'cargo_head_binary']
    driver = s['rust_base_driver' if arm == 'A' else 'rust_head_driver']
    cb = base/'cargo-observer-fifo-qualification/guardv3' if arm == 'B' else base/'drivers'/('cargo-'+cargo)
    arms[arm] = {'cargo':str(cb), 'cargo_sha256':cargo,'driver':str(base/'drivers'/('driver-'+driver)),'driver_sha256':driver}
files = sorted([p for p in here.rglob('*') if p.is_file() and not any(n.startswith('.') or n == '__pycache__' for n in p.relative_to(here).parts)
        and p.name not in ('runner-binding.json','SHA256SUMS')])
value = {'protocol':'mixed-ordinary-full-abc-H2-v1', 'premeasurement':'No H2 training or graded commands of these paired products at freeze.',
         'plan_sha256':s['registered_plan_sha256'], 'source':s, 'cargo_base':s['cargo_base_binary'],
         'driver_base':s['rust_base_driver'],'arms':arms,'arm_order':p['endpoints'],'host':get('host-preflight.json'),
         'storage':{'new_result_path':str(base/'mixed-native-full-abc-v1'),
                    'expected_increment_bytes':82*2**30,'post_training_headroom_bytes':12*2**30,'fundamental_free_reserve_bytes':25*2**30,
                    'previous_native_measured_arm_target_bytes':{'build':5900541952,'test':12919971840},
                    'previous_private_registry_bytes':404938752,'primary_physical_targets':6,
                    'simultaneous_ephemeral_states':1,'medium':'H2 Linux ext4 /dev/vda1, same mount for all arm target/shared/registry stores',
                    'lifecycle':'Sequentially train three original empty arms per endpoint, then one independent edited forced-full gold per compiler, then one physically independent copy of the trained C state for both edit directions. Seal raw mixed products and bridge results before retiring each regenerable oracle. Preserve all six timed states.'},
         'prerequisite_rc':[str(base/n) for n in ['queue-cargo-ruff-v2.rc','stdlib-holdout-v1/queue.rc',
                        'cargo-observer-fifo-qualification/queue.rc','prefetch-fifo-qualified/queue.rc','corrected-native-rerun/queue.rc']],
         'prerequisite_json':[str(base/n) for n in ['qualification-posobs4fmt-c3/complete.json','cargo-observer-ruff-final/complete.json',
                       'stdlib-holdout-exact-v1/complete.json','cargo-observer-ruff-fifo-fixed/complete.json','cargo-observer-ruff-fifo-fixed/statistics.json',
                       'whole-ruff-observer-prefetch-fifo-v1/complete.json','whole-ruff-observer-prefetch-fifo-v1/public/statistics.json',
                       'corrected-toolchain-portable-rerun-v1/complete.json']],
         'reviewed_safety_sha256':{n.name:sha(n) for n in sorted((here/'proof').iterdir()) if n.is_file()},
         'runner_inputs':{str(n.relative_to(here)):sha(n) for n in files}}
out=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
f=here/'runner-binding.json'
if '--verify' in sys.argv:
    if f.read_bytes()!=out: raise SystemExit('runner binding differs')
else:
    f.write_bytes(out)
    (here/'SHA256SUMS').write_text(''.join(f'{sha(n)}  {n.relative_to(here)}\n' for n in sorted([*files,f])))
print(hashlib.sha256(out).hexdigest())

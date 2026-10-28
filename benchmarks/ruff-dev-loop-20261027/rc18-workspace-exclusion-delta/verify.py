"""Rebuild and compare the two recorded Rust functions and validate the qualification snapshot."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

here = Path(__file__).resolve().parent
e = json.loads((here/'evidence.json').read_bytes())
assert len(e['checks']) == 10
assert sum(c == 'SUCCESS' for pr in e['checks'] for _, _, c in pr['checks']) == 50
assert sum(c == 'SKIPPED' for pr in e['checks'] for _, _, c in pr['checks']) == 4
assert e['compiler_tree'] == '47e23eb4bab742e271ca9a3cf1bbd583d5b4a640'
assert len((here/'ruff-manifests.txt').read_text().splitlines()) == 57
assert e['ruff_workspace_members'] == ['crates/*'] and e['ruff_workspace_exclude'] == []
assert all(len({t['test'] for t in row['workspace_exclusion_tests'] if t['result']=='ok'}) >= 6 for row in e['cargo_ci'])
program = (here/'replay.rs.in').read_text()
for arm, method in [('old', 'prior'), ('new', 'next')]:
    fn = (here/(arm+'.rs')).read_text()
    assert fn.count('fn is_excluded(') == 1
    program = program.replace(arm.upper()+'_PREDICATE', fn.replace('fn is_excluded(', 'fn '+method+'('))
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root/'replay.rs').write_text(program)
    shutil.copy(here/'ruff-manifests.txt', root)
    subprocess.run(['rustc','+ohm','--edition=2024','replay.rs','-o','replay'],cwd=root,check=True)
    result = json.loads(subprocess.check_output([root/'replay'],cwd=root))
assert result['cases'] == 8442 and result['kept'] + result['excluded'] == result['cases']
if (here/'result.json').is_file():
    assert json.loads((here/'result.json').read_bytes()) == result
print(json.dumps(result, sort_keys=True))

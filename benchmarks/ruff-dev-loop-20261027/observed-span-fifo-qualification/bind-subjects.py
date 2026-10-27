"""Bind exact Cargo images to the registered Ruff study without changing the worker or analysis."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def put(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('original_harness', type=Path)
cli.add_argument('subject_manifest', type=Path)
cli.add_argument('output', type=Path)
args = cli.parse_args()
old = args.original_harness
out = args.output
registration = Path(__file__).with_name('registration.json')
plan = json.loads(registration.read_bytes())
subjects = json.loads(args.subject_manifest.read_bytes())
assert all(sha(old / name) == digest for name, digest in plan['harness_original_sha256'].items())
assert sha(old / 'plan.json') == plan['original_harness_plan_sha256']
assert subjects['compiler_commit'] == plan['compiler_commit']
assert subjects['compiler_driver'] == plan['compiler_driver']
assert subjects['parent_source'] == plan['parent_source']
assert subjects['candidate_base'] == plan['candidate_base']
assert subjects['fingerprint_source'] == plan['candidate_fingerprint_source_sha256']
assert subjects['fix_patch'] == plan['fix_patch_sha256']
assert len(subjects['candidate_source']) == 40
for field in ('parent_cargo', 'candidate_cargo', 'pgo_profile'):
    digest = subjects[field]
    assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
assert subjects['parent_cargo'] != subjects['candidate_cargo']
assert subjects['same_recipe'] and subjects['same_source_and_target_paths']

out.mkdir()
for name in plan['harness_original_sha256']:
    shutil.copyfile(old / name, out / name)
shutil.copyfile(args.subject_manifest, out / 'matched-subjects.json')
shutil.copyfile(registration, out / 'registration.json')
plan['binding'] = sha(args.subject_manifest)
spec = plan['cargo_companion_support']
spec['control_cargo'] = subjects['parent_cargo']
spec['candidate_cargo'] = {'source': subjects['candidate_source'], 'source_patch': subjects['fix_patch']}
put(out / 'plan.json', plan)
runner = (out / 'run.py').read_text()
oldplan = json.loads((old / 'plan.json').read_bytes())
replacements = {
    oldplan['cargo_companion_support']['control_cargo']: subjects['parent_cargo'],
    'a99a694c680f474bef2ae17de20533890dc536606021db93aaf531e3ef40919a': subjects['candidate_cargo'],
    plan['original_harness_plan_sha256']: sha(out / 'plan.json'),
}
for before, after in replacements.items():
    assert runner.count(before) == 1, before
    runner = runner.replace(before, after)
check = '    spec = plan["cargo_companion_support"]'
assert runner.count(check) == 1
runner = runner.replace(check, check + '\n    need(args.compiler_commit == plan["compiler_commit"] and driver_sha == plan["compiler_driver"], "incorrect compiler")')
(out / 'run.py').write_text(runner)
(out / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(out.iterdir())))

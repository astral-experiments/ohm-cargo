#!/usr/bin/env python3
"""Freeze a fresh matched production pair; do not launch or measure anything."""
import ast
import datetime
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / 'host3-sbom-stack179'
WORK = ROOT.parents[1]
CANDIDATE = WORK / 'workspace-inheritance-candidate'
SOURCE = WORK / 'cargo-shared-workspace-dependencies'
FROZEN = ROOT / 'frozen'
PINNED = '5e5d271d763d7beb38b48755e22bd59e93f02b97'
BASE = 'c40676e264501bc8a93095d3a273a1c300b80875'
OLD_REMOTE = '/tmp/ohm-hillclimb-20261021-production'
NEW_REMOTE = '/tmp/ohm-hillclimb-20261021-inheritance-production'
COHORT = 'host2-inheritance-stack180'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args])

assert not FROZEN.exists()
assert git('rev-parse', 'HEAD').decode().strip() == BASE
assert hashlib.sha256(git('diff', '--binary', '--full-index', BASE)).hexdigest() == 'cbace02bcebcce462e5912e832ade58e30822e0e83cece47039636fdfe58e4c9'
assert sha(PARENT / 'frozen/build_driver_host3_sbom_stack179.py') == '2bf88362cff689835a0e06d25d985c3b4b63fb611d25ab73727a9a9a6250c2e6'
FROZEN.mkdir()
(ROOT / 'results').mkdir()
replacements = {
    OLD_REMOTE: NEW_REMOTE,
    'charlie-oss-3': 'charlie-oss-2',
    'host3-sbom-stack179': COHORT,
    'host3_sbom_stack179': 'host2_inheritance_stack180',
    'sbom-stack179-baseline': 'inheritance-stack180-baseline',
    'sbom-stack179-lazy': 'inheritance-stack180-shared',
    'stack179-current.patch': 'stack180-baseline.patch',
    'stack179-lazy-sbom.patch': 'stack180-shared.patch',
    '19718e6d1637244ffbb193334f50bae3ffca1be5': BASE,
    'f4ce59f92aa17461fe3c8b68923c88539136045a': '0a392258c801cff734d223a3f9af73d5b5a4e3c0',
    'c377ade816d378aa75f629313ac7b116da10c6da': 'c4178b67e0b3a64a12b9b58f84b97323b99d734e',
    '5db5e4a8b09ffea58d8ee7f297d2d486c7bde0d159fe51e5adcb23db72bbb573': 'c6903b9c8d161553d8993b35744186a840163431f2da741c516bd12ae11b6435',
    'b514c63d12c25d2670a7e64e9219417d5e08d4fb43d719135067bfacc05a52d8': 'e03566d5109989053f94721ac430527f10b6ff079fb8dc03cb6ce8e139d8f086',
    'current179/lazy-SBOM': 'current180/shared-workspace-dependencies',
    'host3': 'host2',
}
def adapted(text):
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text

relocator = '''\n\ndef relocated_reference(value):
    """Compare the original reference after relocating this owned build root."""
    old = "/tmp/ohm-hillclimb-20261021-production"
    new = "/tmp/ohm-hillclimb-20261021-inheritance-production"
    if isinstance(value, str) and (value == old or value.startswith(old + "/")):
        return new + value[len(old):]
    if isinstance(value, dict):
        return {key: relocated_reference(item) for key, item in value.items()}
    if isinstance(value, list):
        return [relocated_reference(item) for item in value]
    return value
'''
parent_driver = (PARENT / 'frozen/build_driver_host3_sbom_stack179.py').read_text()
driver = adapted(parent_driver)
driver = driver.replace('\ndef main():', relocator + '\n\ndef main():', 1)
driver = driver.replace('if provenance[key] != original_provenance[key]:', 'if provenance[key] != relocated_reference(original_provenance[key]):')
driver = driver.replace('    provenance["cohort"] =', '    provenance["reference_path_relocation"] = {"from": ' + repr(OLD_REMOTE) + ', "to": ' + repr(NEW_REMOTE) + '}\n    provenance["cohort"] =')
driver_name = 'build_driver_host2_inheritance_stack180.py'
ast.parse(driver)
(ROOT / driver_name).write_text(driver)
(FROZEN / driver_name).write_text(driver)
(ROOT / 'driver.diff').write_text(''.join(difflib.unified_diff(parent_driver.splitlines(True), driver.splitlines(True), fromfile='reviewed-host3-sbom-driver', tofile=driver_name)))
for name in ('provision.py', 'collect_variant.py', 'audit.py'):
    source = (PARENT / name).read_text()
    content = adapted(source)
    if name == 'audit.py':
        content = content.replace('\ndef sha(path):', relocator + '\n\ndef sha(path):', 1)
        content = content.replace('provenance[key] == REFERENCE[key]', 'provenance[key] == relocated_reference(REFERENCE[key])')
        content = content.replace('host2-current-stack/results/cargo-stack179-current', 'host2-current-stack/results/cargo-stack179-path-cache')
        content = content.replace('current179', 'current180')
        content = content.replace('"host7_reference_fields_match": True,', '"host7_reference_fields_match_after_explicit_root_relocation": True,\n    "reference_path_relocation": provenance["reference_path_relocation"],')
    ast.parse(content)
    (ROOT / name).write_text(content)
    (ROOT / (name + '.diff')).write_text(''.join(difflib.unified_diff(source.splitlines(True), content.splitlines(True), fromfile='reviewed-host3/' + name, tofile='new-host2/' + name)))
for name in ('reference-host7-provenance.json', 'strip_binaries.py'):
    shutil.copy2(PARENT / 'frozen' / name, FROZEN / name)
patches = {
    'stack180-baseline.patch': 'stack180-baseline.full.patch',
    'stack180-shared.patch': 'stack180-shared-dependencies.full.patch',
}
for destination, source in patches.items():
    shutil.copy2(CANDIDATE / source, FROZEN / destination)
manifest = json.loads(json.dumps(json.loads((PARENT / 'frozen/manifest.json').read_text())))
manifest = json.loads(adapted(json.dumps(manifest)))
manifest.pop('host2_readonly_input_check_sha256')
manifest.update(driver_sha256=sha(FROZEN / driver_name),
                reviewed_driver_parent_sha256=sha(PARENT / 'frozen/build_driver_host3_sbom_stack179.py'),
                performance_protocol_sha256=sha(CANDIDATE / 'protocol.json'),
                source_manifest_sha256=sha(CANDIDATE / 'source.json'),
                owned_build_root=NEW_REMOTE,
                reference_path_relocation={'from': OLD_REMOTE, 'to': NEW_REMOTE},
                frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
for variant, ref in (('inheritance-stack180-baseline', BASE), ('inheritance-stack180-shared', None)):
    args = ['diff', '--binary', '--full-index', PINNED]
    if ref:
        args.append(ref)
    manifest['expected_variants'][variant]['canonical_diff_sha256'] = hashlib.sha256(git(*args)).hexdigest()
(FROZEN / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'cohort': COHORT, 'manifest_sha256': sha(FROZEN / 'manifest.json'), 'driver_sha256': sha(FROZEN / driver_name), 'remote_root': NEW_REMOTE}, indent=2))

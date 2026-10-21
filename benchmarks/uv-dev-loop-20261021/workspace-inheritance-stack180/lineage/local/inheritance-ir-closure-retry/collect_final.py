#!/usr/bin/env python3
"""Collect a completed IR closure or native phase, preserving the failed capture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
CONTROLS = HERE.parent / 'inheritance-measurement'
sys.path.insert(0, str(HERE / 'reviewer'))
import closure_contract as contract
from closure_binding import verify_closed_ir, verify_failed_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('ir', 'native'), required=True)
    parser.add_argument('--source-freeze-sha256', required=True)
    args = parser.parse_args()
    assert contract.sha(HERE / 'source-freeze.json') == args.source_freeze_sha256
    source = contract.read(HERE / 'source-freeze.json')
    for name, digest in source['files'].items():
        assert contract.sha(contract.regular(HERE, name)) == digest
    manifest_sha = source['files']['closure-manifest.json']
    _, captured = contract.verify_manifest(HERE, manifest_sha)
    assert verify_failed_capture(CONTROLS) == captured
    assert contract.sha(CONTROLS / 'launch-ir.json') == contract.FAILED_LAUNCH
    closure_launch = contract.read(HERE / 'launch-finalize.json')
    assert closure_launch['returncode'] == 0 and closure_launch['source_freeze_sha256'] == args.source_freeze_sha256
    assert closure_launch['closure_manifest_sha256'] == manifest_sha
    for suffix in ('stdout', 'stderr'):
        assert contract.sha(HERE / ('launch-finalize.' + suffix)) == closure_launch[suffix + '_sha256']
    if args.phase == 'native':
        assert contract.read(CONTROLS / 'launch-native.json')['returncode'] == 0
    destination = CONTROLS / 'collections' / ('ir-closed-postguard' if args.phase == 'ir' else 'native')
    destination.mkdir(parents=True, exist_ok=False)
    remote = r'''
import hashlib,importlib.util,io,json,os,socket,sys,tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
phase,closure_sha,source_sha=sys.argv[1:]
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert socket.gethostname()=='charlie-oss-2' and os.getuid()==1000
assert root.resolve()==root and root.stat().st_uid==1000 and Path('/').stat().st_uid==0
here=root/'closures/ir-postguard'
assert here.resolve()==here and here.stat().st_uid==1000
assert sha(here/'closure-manifest.json')==closure_sha and sha(here/'source-freeze.json')==source_sha
closure_manifest=json.loads((here/'closure-manifest.json').read_text())
assert sha(here/'closure_contract.py')==closure_manifest['files']['closure_contract.py']
spec=importlib.util.spec_from_file_location('inheritance_collection_contract',here/'closure_contract.py')
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
contract.verify_manifest(here,closure_sha)
assert sha(root/'delivery.json')==contract.DELIVERY
assert json.loads((root/'ownership.json').read_text())['delivery_sha256']==contract.DELIVERY
script=root/'controller/driver.py';assert sha(script)==contract.DRIVER
spec=importlib.util.spec_from_file_location('inheritance_collection_driver',script)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
driver.reference('ir').quiet()
driver.verify_assets();driver.verify_seal(contract.SEAL)
assert driver.read(driver.phase_status('ir'))['state']=='complete'
if phase=='ir':assert not driver.phase_status('native').exists()
else:assert driver.read(driver.phase_status('native'))['state']=='complete'
failed=contract.read(here/'failed-capture/transfer-manifest.json')
receipt=contract.read(here/'finalization.json')
assert receipt['state']=='complete' and receipt['original_raw_bytes_preserved'] is True
assert receipt['closure_manifest_sha256']==closure_sha and receipt['source_freeze_sha256']==source_sha
assert receipt['failed_capture_sha256']==contract.FAILED_CAPTURE
assert receipt['failed_launch_sha256']==contract.FAILED_LAUNCH
assert receipt['original_files_sha256_before']==failed['files']
assert receipt['original_files_sha256_after']==contract.original_hashes(root,failed,allow_status_update=True)
assert receipt['final_status_sha256']==sha(driver.phase_status('ir'))
assert set(receipt['analysis_files_sha256'])==contract.ANALYSES
assert all(sha(root/name)==digest for name,digest in receipt['analysis_files_sha256'].items())
assert receipt['workload_invocations']==0 and receipt['original_sample_count']==56
assert sha(here/'started.json')==receipt['started_receipt_sha256']
def selected():
 paths=[root/name for name in ('delivery.json','ownership.json','delivery-occupancy.json')]
 for directory in ('controller','metadata','logs','benchmark','results','closures/ir-postguard'):
  for path in (root/directory).rglob('*'):
   assert not path.is_symlink(),path
   if path.is_dir():continue
   assert path.is_file() and path.resolve()==path,path
   if path.is_relative_to(root/'controller/binaries'):continue
   paths.append(path)
 return {str(path.relative_to(root)):sha(path) for path in sorted(set(paths))}
files=selected()
core=driver.load_module('paired',driver.CORE,driver.CORE_SHA)
for workflow,seed in driver.STAGES['ir']['plan']:driver.audit_ir(core,workflow,seed)
if phase=='native':
 for workflow,seed in driver.STAGES['native']['plan']:
  driver.reference('native').audit_complete(core,workflow,seed)
  directory=driver.paths('native',workflow)['output']
  driver.audit_sample_tables(directory,driver.read(directory/'samples.json'),'native')
manifest={'phase':phase,'root':str(root),'seal_sha256':contract.SEAL,'delivery_sha256':contract.DELIVERY,
 'driver_sha256':contract.DRIVER,'files':files,
 'operational_closure':{'closure_manifest_sha256':closure_sha,'source_freeze_sha256':source_sha,
 'failed_capture_sha256':contract.FAILED_CAPTURE,'finalization_sha256':sha(here/'finalization.json')},
 'scope':'Completed phase with exact retained operational failure and metadata-only closure; no analysis or sampling.'}
data=(json.dumps(manifest,indent=2)+'\n').encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 info=tarfile.TarInfo('transfer-manifest.json');info.size=len(data);info.mode=0o644
 archive.addfile(info,io.BytesIO(data))
 for name in files:archive.add(root/name,arcname='remote/'+name,recursive=False)
assert selected()==files
contract.verify_manifest(here,closure_sha)
assert contract.original_hashes(root,failed,allow_status_update=True)==receipt['original_files_sha256_after']
driver.verify_assets();driver.verify_seal(contract.SEAL)
'''
    command = ['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh', contract.HOST,
               '--', '/usr/bin/env', '-u', 'PYTHONPATH', '-u', 'PYTHONHOME', '-u', 'PYTHONUSERBASE',
               '-u', 'VIRTUAL_ENV', '/usr/bin/python3', '-I', '-B', '-c', remote,
               args.phase, manifest_sha, args.source_freeze_sha256]
    with (destination / 'payload.tar').open('xb') as stdout, (destination / 'transfer.stderr').open('xb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr)
    (destination / 'transport.json').write_text(json.dumps({'returncode': result.returncode,
        'archive_sha256': contract.sha(destination / 'payload.tar'),
        'stderr_sha256': contract.sha(destination / 'transfer.stderr')}, indent=2) + '\n')
    assert result.returncode == 0
    seen = set()
    with tarfile.open(destination / 'payload.tar', 'r:') as archive:
        first = archive.next()
        assert first.name == 'transfer-manifest.json' and first.isfile()
        data = archive.extractfile(first).read()
        manifest = json.loads(data)
        assert manifest['phase'] == args.phase and manifest['root'] == str(contract.ROOT)
        assert manifest['seal_sha256'] == contract.SEAL and manifest['delivery_sha256'] == contract.DELIVERY
        assert manifest['driver_sha256'] == contract.DRIVER
        (destination / first.name).write_bytes(data)
        for member in iter(archive.next, None):
            name = contract.relative(member.name)
            assert member.isfile() and not member.issym() and not member.islnk()
            assert name.parts[0] == 'remote' and member.name not in seen
            relative = str(name.relative_to('remote'))
            assert relative in manifest['files']
            seen.add(member.name)
            archive.extract(member, destination, filter='data')
            assert contract.sha(destination / name) == manifest['files'][relative]
    assert seen == {'remote/' + name for name in manifest['files']}
    copied = destination / 'remote'
    assert contract.sha(copied / 'delivery.json') == contract.DELIVERY
    assert contract.sha(copied / 'controller/measurement-seal.json') == contract.SEAL
    assert contract.sha(copied / 'controller/source-freeze.json') == contract.FREEZE
    for relative, digest in contract.read(copied / 'controller/assets.json')['files'].items():
        if relative in manifest['files']:
            assert contract.sha(copied / relative) == digest
    for filename, digest in contract.read(copied / 'controller/measurement-seal.json')['file_sha256'].items():
        path = Path(filename)
        if path.is_relative_to(contract.ROOT):
            relative = str(path.relative_to(contract.ROOT))
            if relative in manifest['files']:
                assert contract.sha(copied / relative) == digest
    closure = verify_closed_ir(CONTROLS, copied, manifest['files'], HERE, manifest)
    for name, digest in source['files'].items():
        assert contract.sha(contract.regular(HERE, name)) == digest
    assert verify_failed_capture(CONTROLS) == captured
    receipt = {'status': 'passed', 'phase': args.phase, 'files': len(seen),
               'transfer_manifest_sha256': contract.sha(destination / 'transfer-manifest.json'),
               'measurement_seal_sha256': contract.SEAL,
               'closure_finalization_sha256': closure['receipt_sha256'],
               'failed_capture_sha256': contract.FAILED_CAPTURE,
               'scope': 'All transferred bytes and original raw observations verified; failed launch/status retained. No analysis or sampling.'}
    (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()

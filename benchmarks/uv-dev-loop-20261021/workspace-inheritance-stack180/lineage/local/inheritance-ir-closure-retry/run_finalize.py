#!/usr/bin/env python3
"""Stage and execute the reviewed one-shot metadata closure; never sample Cargo."""
from __future__ import annotations

import argparse
import datetime
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
CONTROLS = HERE.parent / 'inheritance-measurement'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'reviewer'))
import closure_contract as contract
from closure_binding import verify_failed_capture


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-freeze-sha256', required=True)
    args = parser.parse_args()
    assert contract.sha(HERE / 'source-freeze.json') == args.source_freeze_sha256
    frozen = contract.read(HERE / 'source-freeze.json')
    for name, digest in frozen['files'].items():
        assert contract.sha(contract.regular(HERE, name)) == digest, name
    manifest_sha = frozen['files']['closure-manifest.json']
    manifest, capture = contract.verify_manifest(HERE, manifest_sha)
    assert verify_failed_capture(CONTROLS) == capture
    assert contract.sha(CONTROLS / 'launch-ir.json') == contract.FAILED_LAUNCH
    for suffix in ('json', 'stdout', 'stderr'):
        assert (CONTROLS / ('launch-ir.' + suffix)).read_bytes() == (HERE / ('failed-capture/launch-ir.' + suffix)).read_bytes()
    for name in ('launch-finalize.json', 'launch-finalize.stdout', 'launch-finalize.stderr'):
        assert not (HERE / name).exists()
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name in list(manifest['files']) + ['closure-manifest.json', 'source-freeze.json']:
            archive.add(HERE / name, arcname=name, recursive=False)
    remote = r'''
import hashlib,importlib.util,io,json,os,socket,sys,tarfile
from pathlib import Path,PurePosixPath
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-measurement')
manifest_sha,source_sha=sys.argv[1:]
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
assert socket.gethostname()=='charlie-oss-2' and os.getuid()==1000 and Path('/').stat().st_uid==0
assert root.resolve()==root and root.stat().st_uid==1000
assert sha(root/'delivery.json')=='9cb40f6d074706a713b60c2c1b17e4ac44bf8294f1fc3ba3973f46912a2e15ec'
assert json.loads((root/'ownership.json').read_text())['delivery_sha256']==sha(root/'delivery.json')
script=root/'controller/driver.py';assert sha(script)=='1585116beaab26655de1e86459feb030ebdd31e636a613991241018ace5f3ef3'
spec=importlib.util.spec_from_file_location('inheritance_closure_stage_driver',script)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
driver.reference('ir').quiet()
assert not driver.phase_status('native').exists()
assert sha(driver.phase_status('ir'))=='f3199c1c5ee27609f56874fda658e651e1bbe174d10ea194584c2d5426f5c868'
content={}
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:') as archive:
 for member in archive:
  name=PurePosixPath(member.name)
  assert member.isfile() and not member.issym() and not member.islnk()
  assert not name.is_absolute() and '..' not in name.parts and str(name)==member.name and '\\' not in member.name
  assert member.name not in content
  content[member.name]=archive.extractfile(member).read()
assert hashlib.sha256(content['closure-manifest.json']).hexdigest()==manifest_sha
assert hashlib.sha256(content['source-freeze.json']).hexdigest()==source_sha
manifest=json.loads(content['closure-manifest.json']);source=json.loads(content['source-freeze.json'])
assert source['files']['closure-manifest.json']==manifest_sha
assert set(content)==set(manifest['files'])|{'closure-manifest.json','source-freeze.json'}
for name,digest in manifest['files'].items():
 assert hashlib.sha256(content[name]).hexdigest()==digest==source['files'][name]
parent=root/'closures'
if not parent.exists():parent.mkdir()
assert parent.resolve()==parent and parent.is_dir() and parent.stat().st_uid==1000
here=parent/'ir-postguard';here.mkdir(exist_ok=False)
for name,data in content.items():
 path=here/name;path.parent.mkdir(parents=True,exist_ok=True)
 assert path.parent.resolve()==path.parent
 with path.open('xb') as stream:stream.write(data)
 os.chmod(path,0o644)
 assert sha(path)==hashlib.sha256(data).hexdigest()
# Replace the setup interpreter. The unchanged guard excludes only its own PID.
env=os.environ.copy()
for name in list(env):
 if name.startswith('PYTHON') or name=='VIRTUAL_ENV':env.pop(name)
os.execve('/usr/bin/python3',['/usr/bin/python3','-I','-B',str(here/'finalize.py'),
          '--closure-manifest-sha256',manifest_sha,'--source-freeze-sha256',source_sha],env)
'''
    command = ['/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh', contract.HOST,
               '--', '/usr/bin/env', '-u', 'PYTHONPATH', '-u', 'PYTHONHOME', '-u', 'PYTHONUSERBASE',
               '-u', 'VIRTUAL_ENV', '/usr/bin/python3', '-I', '-B', '-c', remote,
               manifest_sha, args.source_freeze_sha256]
    receipt = {'operation': 'finalize-ir-postguard', 'host': contract.HOST, 'root': str(contract.ROOT),
               'started_at': now(), 'source_freeze_sha256': args.source_freeze_sha256,
               'closure_manifest_sha256': manifest_sha, 'measurement_seal_sha256': contract.SEAL,
               'failed_capture_sha256': contract.FAILED_CAPTURE,
               'transfer_payload_sha256': __import__('hashlib').sha256(payload.getvalue()).hexdigest()}
    with (HERE / 'launch-finalize.stdout').open('xb') as stdout, (HERE / 'launch-finalize.stderr').open('xb') as stderr:
        result = subprocess.run(command, input=payload.getvalue(), stdout=stdout, stderr=stderr)
    receipt.update(returncode=result.returncode, finished_at=now(),
                   stdout_sha256=contract.sha(HERE / 'launch-finalize.stdout'),
                   stderr_sha256=contract.sha(HERE / 'launch-finalize.stderr'))
    with (HERE / 'launch-finalize.json').open('x') as stream:
        json.dump(receipt, stream, indent=2);stream.write('\n')
    for name, digest in frozen['files'].items():
        assert contract.sha(contract.regular(HERE, name)) == digest
    assert contract.sha(CONTROLS / 'launch-ir.json') == contract.FAILED_LAUNCH
    assert verify_failed_capture(CONTROLS) == capture
    print(json.dumps(receipt, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()

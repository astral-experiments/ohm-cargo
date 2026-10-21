#!/usr/bin/env python3
"""Import the exact local bundle and launch the fresh, isolated host2 SBOM cohort."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "frozen"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest-sha256", required=True)
args = parser.parse_args()
assert hashlib.sha256((FROZEN / "manifest.json").read_bytes()).hexdigest() == args.manifest_sha256
manifest = json.loads((FROZEN / "manifest.json").read_text())
files = {
    "pinned.bundle": ROOT.parent / "pinned.bundle",
    "build_driver_host2_inheritance_stack180.py": FROZEN / "build_driver_host2_inheritance_stack180.py",
    "host2-inheritance-stack180-inputs.json": FROZEN / "manifest.json",
    "reference-host7-provenance.json": FROZEN / "reference-host7-provenance.json",
    "tools/strip_binaries.py": FROZEN / "strip_binaries.py",
    "stack180-baseline.patch": FROZEN / "stack180-baseline.patch",
    "stack180-shared.patch": FROZEN / "stack180-shared.patch",
}
hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}
assert hashes["build_driver_host2_inheritance_stack180.py"] == manifest["driver_sha256"]
assert hashes["pinned.bundle"] == manifest["source_bundle_sha256"]
assert hashes["tools/strip_binaries.py"] == manifest["strip_helper_sha256"]
assert hashes["reference-host7-provenance.json"] == manifest["reference_host7_provenance_sha256"]
for name, expected_hash in manifest["patch_sha256"].items():
    assert hashes[name] == expected_hash
archive_path = ROOT / "provision-inputs.tar"
with tarfile.open(archive_path, "x:") as archive:
    for name, path in files.items():
        archive.add(path, arcname=name, recursive=False)
(ROOT / "provision-input-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")

remote = r'''
import hashlib,io,json,os,subprocess,sys,tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-production')
assert root.resolve()==root and os.getuid()==1000
assert not root.exists() and not root.is_symlink(), 'task root already exists'
assert subprocess.check_output(['hostname'],text=True).strip()=='charlie-oss-2'
expected=json.loads(sys.argv[1]); payload={}
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:') as archive:
 for member in archive.getmembers():
  assert member.isfile() and member.name in expected and member.name not in payload
  data=archive.extractfile(member).read()
  assert hashlib.sha256(data).hexdigest()==expected[member.name], member.name
  payload[member.name]=data
assert set(payload)==set(expected)
scope={'__name__':'frozen_preflight','__file__':str(root/'build_driver_host2_inheritance_stack180.py')}
exec(compile(payload['build_driver_host2_inheritance_stack180.py'],'frozen_driver','exec'),scope)
occupancy=scope['occupancy']()
print(json.dumps({'preflight':occupancy,'input_sha256':expected},indent=2),flush=True)
assert not occupancy['other_workloads'], 'host2 is occupied; no files or build started'
root.mkdir(mode=0o700)
for name in ['logs','binaries','cargo-home','tmp','tools']:(root/name).mkdir()
for name,data in payload.items():
 with (root/name).open('xb') as f:f.write(data)
(root/'preflight-host2-inheritance-stack180.json').write_text(json.dumps(occupancy,indent=2)+'\n')
owner={'cohort':'host2-inheritance-stack180','root':str(root),'uid':os.getuid(),
       'inputs_sha256':hashlib.sha256(payload['host2-inheritance-stack180-inputs.json']).hexdigest()}
with (root/'ownership-host2-inheritance-stack180.json').open('x') as stream:
 stream.write(json.dumps(owner,indent=2)+'\n')
source=root/'source' 
subprocess.run(['git','init','--quiet',str(source)],check=True)
subprocess.run(['git','-C',str(source),'bundle','unbundle',str(root/'pinned.bundle')],check=True)
(source/'.git/shallow').write_text('5e5d271d763d7beb38b48755e22bd59e93f02b97\n')
subprocess.run(['git','-C',str(source),'update-ref','refs/heads/ohm-pinned','5e5d271d763d7beb38b48755e22bd59e93f02b97'],check=True)
subprocess.run(['git','-C',str(source),'symbolic-ref','HEAD','refs/heads/ohm-pinned'],check=True)
subprocess.run(['git','-C',str(source),'reset','--hard','5e5d271d763d7beb38b48755e22bd59e93f02b97'],check=True)
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip()=='f359174bb51dd7adb6a6e94dac43661d27086193'
with (root/'logs/host2-inheritance-stack180.driver.stdout').open('xb') as stdout,(root/'logs/host2-inheritance-stack180.driver.stderr').open('xb') as stderr:
 process=subprocess.Popen([sys.executable,str(root/'build_driver_host2_inheritance_stack180.py')],cwd=root,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
(root/'host2-inheritance-stack180.pid').write_text(str(process.pid)+'\n')
print(json.dumps({'launched_pid':process.pid,'source_commit':'5e5d271d763d7beb38b48755e22bd59e93f02b97','source_tree':'f359174bb51dd7adb6a6e94dac43661d27086193'}),flush=True)
'''
with archive_path.open("rb") as stream:
    result = subprocess.run([
        "/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh",
        "charlie-oss-2", "--", "python3", "-c", remote, json.dumps(hashes),
    ], stdin=stream, capture_output=True, text=True)
for extension, output in (("stdout", result.stdout), ("stderr", result.stderr)):
    with (ROOT / f"provision.{extension}").open("x") as stream:
        stream.write(output)
    print(output)
raise SystemExit(result.returncode)

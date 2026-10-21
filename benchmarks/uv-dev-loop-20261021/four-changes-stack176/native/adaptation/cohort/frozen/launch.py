#!/usr/bin/env python3
"""Stage frozen inputs and launch only after the original host2 pair completes."""

import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "frozen"
manifest = json.loads((FROZEN / "manifest.json").read_text())
paths = {
    "build_driver_host2_current_stack.py": FROZEN / "build_driver_host2_current_stack.py",
    "host2-current-stack-inputs.json": FROZEN / "manifest.json",
}
paths.update({filename: FROZEN / filename for filename in manifest["patch_sha256"]})
expected = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
assert expected["build_driver_host2_current_stack.py"] == manifest["driver_sha256"]
for name, digest in manifest["patch_sha256"].items():
    assert expected[name] == digest
remote = r'''
import hashlib,io,json,os,runpy,subprocess,sys,tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-production')
assert root.resolve()==root and root.stat().st_uid==os.getuid()
expected=json.loads(sys.argv[1]); old_driver_hash=sys.argv[2]
old_manifest_hash=sys.argv[3]; initial_tree=sys.argv[4]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old_driver=root/'build_driver_host2_pr175_sbom.py'
assert sha(old_driver)==old_driver_hash
assert sha(root/'host2-pr175-sbom-inputs.json')==old_manifest_hash
previous=json.loads((root/'status-host2-pr175-sbom.json').read_text())
assert previous['state']=='complete' and previous['completed_variants']==['pr175','pr175-lazy-sbom'],previous
namespace=runpy.run_path(str(old_driver),run_name='read_only_preflight')
occupied=namespace['occupancy']()
if occupied['other_workloads']:
 print(json.dumps({'state':'blocked-by-occupancy','occupancy':occupied}));raise SystemExit(2)
assert namespace['current_source_tree']()==initial_tree
for name in ('status-host2-current-stack.json','provenance-host2-current-stack.json',
             'host2-current-stack.prior-binary-manifest.json','host2-current-stack.pid',
             'logs/host2-current-stack.driver.stdout','logs/host2-current-stack.driver.stderr'):
 assert not (root/name).exists(),name
payload=sys.stdin.buffer.read()
with tarfile.open(fileobj=io.BytesIO(payload),mode='r:') as archive:
 members=archive.getmembers()
 assert len(members)==len(expected) and {m.name for m in members}==set(expected)
 contents={}
 for member in members:
  assert member.isfile() and Path(member.name).name==member.name
  data=archive.extractfile(member).read()
  assert hashlib.sha256(data).hexdigest()==expected[member.name]
  contents[member.name]=data
 for name,data in contents.items():
  destination=root/name
  if destination.exists():assert sha(destination)==expected[name]
  else:
   with destination.open('xb') as stream:stream.write(data)
new=runpy.run_path(str(root/'build_driver_host2_current_stack.py'),run_name='read_only_preflight')
occupied=new['occupancy']()
if occupied['other_workloads']:
 print(json.dumps({'state':'staged-blocked-by-occupancy','occupancy':occupied}));raise SystemExit(2)
with (root/'logs/host2-current-stack.driver.stdout').open('xb') as stdout,(root/'logs/host2-current-stack.driver.stderr').open('xb') as stderr:
 process=subprocess.Popen([sys.executable,str(root/'build_driver_host2_current_stack.py')],cwd=root,
                          stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
with (root/'host2-current-stack.pid').open('x') as stream:stream.write(str(process.pid)+'\n')
print(json.dumps({'state':'launched','pid':process.pid,'occupancy':occupied,'input_sha256':expected}))
'''
ast.parse(remote)
archive_path = ROOT / "launch-inputs.tar"
with archive_path.open("xb") as stream:
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, path in paths.items():
            data = path.read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
with (ROOT / "launch-input-sha256.json").open("x") as stream:
    json.dump({"files": expected, "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest()}, stream, indent=2)
    stream.write("\n")
command = [
    "/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh",
    "charlie-oss-2", "--", "python3", "-c", remote, json.dumps(expected),
    manifest["preceding_driver_sha256"], manifest["preceding_cohort_manifest_sha256"],
    manifest["initial_source_tree"],
]
with archive_path.open("rb") as stdin, (ROOT / "launch.stdout").open("xb") as stdout, (ROOT / "launch.stderr").open("xb") as stderr:
    result = subprocess.run(command, stdin=stdin, stdout=stdout, stderr=stderr)
print((ROOT / "launch.stdout").read_text(), end="")
if result.returncode:
    print((ROOT / "launch.stderr").read_text(), end="", file=sys.stderr)
    raise SystemExit(result.returncode)

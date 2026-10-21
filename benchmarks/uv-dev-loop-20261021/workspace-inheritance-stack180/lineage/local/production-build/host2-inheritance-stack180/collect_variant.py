#!/usr/bin/env python3
"""Collect immutable artifacts from the isolated host2 production cohort."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
variant = sys.argv[1]
if variant not in {'inheritance-stack180-baseline', 'inheritance-stack180-shared'}:
    raise SystemExit("unknown host2 variant")
remote = r'''
import io,json,os,socket,sys,tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-inheritance-production')
assert socket.gethostname()=='charlie-oss-2' and root.resolve()==root and root.stat().st_uid==os.getuid()==1000
variant=sys.argv[1]
assert variant in {'inheritance-stack180-baseline', 'inheritance-stack180-shared'}
status=json.loads((root/'status-host2-inheritance-stack180.json').read_text())
assert variant in status['completed_variants'],status
name=f'cargo-{variant}'
record=json.loads((root/'binaries/manifest.json').read_text())[name]
files={name:root/'binaries/stripped'/name,
       name+'.strip.json':root/'binaries/stripped'/(name+'.json'),
       'provenance.json':root/'provenance-host2-inheritance-stack180.json',
       'ownership.json':root/'ownership-host2-inheritance-stack180.json'}
for extension in ('source.patch','occupancy.json','stdout','stderr'):
 files[f'{variant}.{extension}']=root/'logs'/f'{variant}.{extension}'
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for filename,path in files.items():archive.add(path,arcname=filename,recursive=False)
 for filename,value in {name+'.build.json':record,variant+'.batch-status.json':status}.items():
  data=(json.dumps(value,indent=2)+'\n').encode()
  member=tarfile.TarInfo(filename);member.size=len(data);member.mode=0o644
  archive.addfile(member,io.BytesIO(data))
'''
with tempfile.TemporaryFile() as output:
    subprocess.run([
        "/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh",
        "charlie-oss-2", "--", "python3", "-c", remote, variant,
    ], stdout=output, check=True)
    output.seek(0)
    with tarfile.open(fileobj=output, mode="r:") as archive:
        for member in archive.getmembers():
            if Path(member.name).name != member.name or not member.isfile():
                raise RuntimeError(f"unexpected archive member: {member.name}")
            data = archive.extractfile(member).read()
            destination = RESULTS / member.name
            if destination.exists():
                if destination.read_bytes() != data:
                    raise RuntimeError(f"immutable artifact changed: {destination}")
            else:
                with destination.open("xb") as stream:
                    stream.write(data)
                destination.chmod(member.mode & 0o777)
name = f"cargo-{variant}"
record = json.loads((RESULTS / f"{name}.build.json").read_text())
proof = json.loads((RESULTS / f"{name}.strip.json").read_text())
expected = json.loads((ROOT / "frozen/manifest.json").read_text())["expected_variants"][variant]
actual = hashlib.sha256((RESULTS / name).read_bytes()).hexdigest()
assert actual == proof["stripped_sha256"]
assert proof["source_sha256"] == proof["original_linker_output_sha256"] == record["original_linker_output_sha256"]
assert (RESULTS / name).stat().st_size == proof["stripped_bytes"]
assert record["observed_source_tree"] == record["expected_source_tree_from_patches"] == expected["tree"]
assert record["patch_sha256"] == expected["patch_sha256"]
assert hashlib.sha256((RESULTS / f"{variant}.source.patch").read_bytes()).hexdigest() == record["observed_diff_sha256"] == expected["canonical_diff_sha256"]
for extension in ("stdout", "stderr"):
    assert hashlib.sha256((RESULTS / f"{variant}.{extension}").read_bytes()).hexdigest() == record[f"{extension}_sha256"]
print(json.dumps({"cohort": "host2-inheritance-stack180", "variant": variant,
                  "binary": str(RESULTS / name), "sha256": actual,
                  "bytes": proof["stripped_bytes"]}, indent=2))

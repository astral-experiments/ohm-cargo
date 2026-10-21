#!/usr/bin/env python3
"""Collect immutable artifacts from the one authorized production-build host."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

VARIANTS = {"baseline", "path-cache", "build-output-remap", "pr175",
            "pr175-build-output-remap", "pr175-path-cache", "pr175-lazy-git",
            "pr175-loader-v2", "pr175-build-output-remap-loader-v2", "pr175-lazy-sbom"}
variant = sys.argv[1]
if variant not in VARIANTS:
    raise SystemExit("unknown variant")
root = Path(__file__).resolve().parent
destination = root / "results"
destination.mkdir(exist_ok=True)
remote = r'''
import io, json, sys, tarfile
from pathlib import Path
root=Path('/tmp/ohm-hillclimb-20261021-production')
variant=sys.argv[1]
assert variant in {'baseline','path-cache','build-output-remap','pr175','pr175-build-output-remap','pr175-path-cache','pr175-lazy-git','pr175-loader-v2','pr175-build-output-remap-loader-v2','pr175-lazy-sbom'}
batch='-accepted-sbom' if variant in {'pr175-build-output-remap-loader-v2','pr175-lazy-sbom'} else ('-'+variant if variant in {'pr175-lazy-git','pr175-path-cache','pr175-loader-v2'} else ('-pr175' if variant.startswith('pr175') else ''))
status=json.loads((root/f'status{batch}.json').read_text())
assert variant in status['completed_variants'], status
name=f'cargo-{variant}'
record=json.loads((root/'binaries/manifest.json').read_text())[name]
files={name:root/'binaries/stripped'/name,
       name+'.strip.json':root/'binaries/stripped'/(name+'.json'),
       f'provenance{batch}.json':root/f'provenance{batch}.json'}
for extension in ('source.patch','occupancy.json','stdout','stderr'):
    files[f'{variant}.{extension}']=root/'logs'/f'{variant}.{extension}'
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
    for filename,path in files.items():
        archive.add(path,arcname=filename,recursive=False)
    metadata={name+'.build.json':record}
    if batch=='-accepted-sbom':
        metadata[variant+'.batch-status.json']=status
    for filename,value in metadata.items():
        data=(json.dumps(value,indent=2)+'\n').encode()
        item=tarfile.TarInfo(filename); item.size=len(data); item.mode=0o644
        archive.addfile(item,io.BytesIO(data))
'''
with tempfile.TemporaryFile() as archive_file:
    subprocess.run([
        "/home/dev-user/.codex/skills/applied/applied-devbox/scripts/devbox_ssh",
        "charlie-oss-7", "--", "python3", "-c", remote, variant,
    ], stdout=archive_file, check=True)
    archive_file.seek(0)
    with tarfile.open(fileobj=archive_file, mode="r:") as archive:
        for member in archive.getmembers():
            if Path(member.name).name != member.name or not member.isfile():
                raise RuntimeError(f"unexpected archive member: {member.name}")
            data = archive.extractfile(member).read()
            path = destination / member.name
            if path.exists():
                if path.read_bytes() != data:
                    raise RuntimeError(f"immutable local artifact changed: {path}")
            else:
                with path.open("xb") as output:
                    output.write(data)
                path.chmod(member.mode & 0o777)
name = f"cargo-{variant}"
proof = json.loads((destination / f"{name}.strip.json").read_text())
record = json.loads((destination / f"{name}.build.json").read_text())
actual = hashlib.sha256((destination / name).read_bytes()).hexdigest()
assert actual == proof["stripped_sha256"]
assert proof["source_sha256"] == record["original_linker_output_sha256"]
assert proof["source_sha256"] == proof["original_linker_output_sha256"]
assert (destination / name).stat().st_size == proof["stripped_bytes"]
for extension in ("stdout", "stderr"):
    assert hashlib.sha256((destination / f"{variant}.{extension}").read_bytes()).hexdigest() == record[f"{extension}_sha256"]
assert hashlib.sha256((destination / f"{variant}.source.patch").read_bytes()).hexdigest() == record["observed_diff_sha256"]
if variant.startswith("pr175"):
    expected = json.loads((root / "expected-pr175-source-trees.json").read_text())[variant]
    assert record["observed_source_tree"] == expected["tree"]
    assert record["patch_sha256"] == expected["patch_sha256"]
print(json.dumps({"variant": variant, "binary": str(destination / name),
                  "sha256": actual, "bytes": proof["stripped_bytes"]}, indent=2))

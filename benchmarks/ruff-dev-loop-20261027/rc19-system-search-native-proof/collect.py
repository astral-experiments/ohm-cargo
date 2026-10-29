"""Collect results from the two retained private mount-namespace experiments."""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import os
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument("raw_root", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
q = args.raw_root.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
sha = lambda data: hashlib.sha256(data).hexdigest()
report = {}
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as tar:
    for kind, group in [("explicit", "private-system-native-provider-v1"),
                        ("implicit", "private-system-implicit-driver-v1"),
                        ("explicit-fixed", "private-system-native-provider-fixed-dev-v1"),
                        ("implicit-fixed", "private-system-implicit-driver-fixed-dev-v1")]:
        b = q / group
        info = json.loads((b / "mount-identity.json").read_bytes())
        host = Path("/usr/lib/x86_64-linux-gnu/libohm_rc20_native_choice_20261029.a")
        if kind.startswith("implicit"):
            host = Path("/usr/lib/gcc/x86_64-linux-gnu/13/libgcc_s.so")
            assert sha(host.read_bytes()) == info["original"] == sha((b / "materials/absent.a").read_bytes())
        else:
            assert info["unique_name_absent"] and not host.exists()
        rows = {}
        for f in sorted(b.glob("*/result.json")):
            arm = f.parent.name
            raw = json.loads(f.read_bytes())
            raw["raw_result_sha256"] = sha(f.read_bytes())
            for row in raw["rows"]:
                d = f.parent / row["phase"]
                assert set(row["outputs"]) == {s.name for s in d.iterdir() if s.is_file()}
                for name in sorted(row["outputs"]):
                    s = (d / name).read_bytes()
                    assert row["outputs"][name] == sha(s)
                    for old, new in [(str(f.parent).encode(), b"@STORE@"),
                                     (str(b).encode(), b"@PRIVATE@"),
                                     (str(q).encode(), b"@QA@"),
                                     (str(q.parent).encode(), b"@CACHE@"),
                                     (os.fsencode(Path.home()), b"@HOME@")]:
                        s = s.replace(old, new)
                    assert os.fsencode(Path.home()) not in s
                    row.setdefault("normalized", {})[name] = sha(s)
                    item = tarfile.TarInfo(f"{kind}/{arm}/{row['phase']}/{name}")
                    item.size = len(s)
                    tar.addfile(item, io.BytesIO(s))
            rows[arm] = raw
        fixture = {}
        for name in ("Cargo.toml","app/Cargo.toml","app/src/lib.rs","app/tests/probe.rs"):
            fixture[name] = (b / "on/project" / name).read_text()
        report[kind] = {"histories":rows,"source":fixture,"archived_inputs":{
            name:sha((b/"materials"/(name+".a")).read_bytes()) for name in ("absent","valid","malformed")},
            "intact_host": {"path":str(host),"sha256":info.get("original")},
            "private_mount":info, "actual_workers":{n:sha((b/n).read_bytes()) for n in
            ("initialize.py","namespace.py","replay.py")}}
        if kind.startswith("implicit"):
            (out/"observer.S").write_bytes((b/"probe.S").read_bytes())
            (out/"system-linker-script.txt").write_bytes((b/"materials/absent.a").read_bytes())
(out/"streams.tar.gz").write_bytes(gzip.compress(buffer.getvalue(),mtime=0))
(out/"records.json.gz").write_bytes(gzip.compress(json.dumps(report,sort_keys=True,separators=(",",":")).encode(),mtime=0))

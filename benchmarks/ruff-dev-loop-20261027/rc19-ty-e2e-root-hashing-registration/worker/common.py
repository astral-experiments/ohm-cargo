"""Study paths and authenticated, metadata-preserving artifact reads."""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

K = Path(__file__).resolve().parent.parent
M = K.parent / "ohm-rc20-ty-e2e-proofless-20261029"
F = M / "forensics-v1"
DESIGN = K / "design"
REPORTS = K / "reports"
LANES = K / "lanes"
ROOT = M / "source"
LIVE = M / "live"
NAME = "e2e-8945421a8b988468"
WORKSPACE = "bc28a8806aa42354"
SCHEMA = json.loads((DESIGN / "requirements.json").read_bytes())
ARGS = SCHEMA["command"]
E2E = LIVE / "target/debug/build/workspaces" / WORKSPACE / "v2-c7a7162545fa7bb4/ty_server/8945421a8b988468/out" / NAME
INC = LIVE / "target/debug/incremental" / WORKSPACE / "e2e-1a54awrrqxqet"
EDIT = Path("crates/ty_server/tests/e2e/inlay_hints.rs")
SCRATCH = Path(json.loads((K/"binding/host.json").read_bytes())["existing_reserve_device"])
REF = M / "reports/parent/06-restore/qualified.json"
sys.path.insert(0, str(M))
import operations as prior

def get(path):
    return json.loads(Path(path).read_bytes())

def put(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")

def rawsha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()

def signature(path):
    return hashlib.sha256(json.dumps(path, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def datafile(path):
    path = Path(path)
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode), path
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOATIME), "rb") as handle:
        st = os.fstat(handle.fileno())
        assert (st.st_dev, st.st_ino) == (before.st_dev, before.st_ino)
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
        after = os.fstat(handle.fileno())
    assert (after.st_ctime_ns, after.st_size) == (st.st_ctime_ns, st.st_size)
    return {"sha256": digest, "size": st.st_size, "mode": stat.S_IMODE(st.st_mode)}

def free():
    return {"home": shutil.disk_usage(K).free, "scratch": shutil.disk_usage(SCRATCH).free}

def floors(reserve=0):
    now = free()
    assert now["home"] >= SCHEMA["home_floor"] + reserve and now["scratch"] >= SCHEMA["scratch_floor"], now
    return now

def trusted():
    assert os.geteuid() == os.getuid() == 1000
    assert set(os.sched_getaffinity(0)) == set(SCHEMA["cpus"])
    assert all(Path(p).stat().st_uid in (0, os.getuid()) for p in ["/", "/home", K, M, ROOT, LIVE])
    assert os.path.ismount(LIVE) and os.path.ismount(ROOT) and os.path.ismount(M / "sdk/bin/cargo")
    return prior.V.env()

def enrolled(arm):
    cfg = get(K / "binding/physical.json")
    assert cfg["plan"] == rawsha(K / "registration/SHA256SUMS")
    image = cfg["subjects"][arm]
    assert Path(image["cargo"]).samefile(M / "sdk/bin/cargo")
    assert rawsha(M / "sdk/bin/cargo") == image["sha256"]
    assert rawsha(M / "sdk/bin/rustc") == get(M / "prepared.json")["rustc"]
    return image

def source(mode):
    old = ROOT / EDIT
    inputs = SCHEMA["source_sha256"]
    assert rawsha(old) in {inputs[k] for k in ("original", "edited", "invalid")}
    wanted = (DESIGN / (mode + ".rs")).read_bytes()
    assert hashlib.sha256(wanted).hexdigest() == inputs[mode]
    if old.read_bytes() != wanted:
        old.write_bytes(wanted)
    actual = {str(EDIT): rawsha(old)}
    assert actual[str(EDIT)] == inputs[mode]
    for relative, expected in get(REF)["source"].items():
        assert rawsha(ROOT / relative) == expected
        actual[relative] = expected
    assert rawsha(ROOT / "Cargo.lock") == get(M / "prepared.json")["source_lock"]
    return actual

def typed_identity(arts):
    clean = [{key: row[key] for key in ("package_id", "manifest_path", "target", "profile", "features", "filenames", "executable")} for row in arts]
    return sorted(clean, key=lambda r: (r["package_id"], str(r["target"]), str(r["profile"]), str(r["features"]), str(r["filenames"])))

def artifacts(transcript):
    arts = [x for x in transcript if x["reason"] == "compiler-artifact"]
    paths = [Path(f) for row in arts for f in row["filenames"] if f != str(E2E)]
    assert len(paths) == len(set(paths)), "duplicate path in typed artifacts"
    all_files = {str(p): datafile(p) for p in sorted(paths)}
    scripts = {}
    for row in transcript:
        if row["reason"] != "build-script-executed":
            continue
        here = Path(row["out_dir"])
        assert here.is_relative_to(LIVE) and here.is_dir() and not here.is_symlink()
        contents = {}
        for p in sorted(here.rglob("*")):
            if p.is_symlink():
                contents[str(p.relative_to(here))] = {"symlink": os.readlink(p), "target": datafile(p.resolve(strict=True))}
            elif p.is_file():
                contents[str(p.relative_to(here))] = datafile(p)
            else:
                assert p.is_dir(), p
        assert str(here) not in scripts
        scripts[str(here)] = {"row": row, "files": contents}
    return {"typed_files": all_files, "build_script_outputs": scripts}

def expected_roster():
    old = M / "forensics-v1/donor/H-settled/cargo.stdout"
    return typed_identity([x for line in old.read_bytes().splitlines() if (x := json.loads(line))["reason"] == "compiler-artifact"])

def safe_name(text):
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,90}", text), text
    return text

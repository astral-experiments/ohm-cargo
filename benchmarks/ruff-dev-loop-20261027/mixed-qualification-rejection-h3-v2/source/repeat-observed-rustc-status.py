"""Replay the same 30 saved readers, additionally persisting the OS rustc exit status."""
import hashlib, json, os, subprocess, sys
from pathlib import Path

x = Path.home() / ".cache/ohm-233-position-qualified-20261027"
primary = x / "mixed-native-full-abc-h3-v2"
s = x / "mixed-h3-v2-rejected"
w = x / "mixed-native-abc-protocol-h3-v2"
remote_inputs = x / "mixed-registry-seed-programs-20261027"
worker = remote_inputs / "bridge-status-worker.py"
runner = remote_inputs / "reader-status-repeat.py"
for f in (runner, worker):
    assert not f.exists()
base = (w / "bridge_worker.py").read_text()
assert base.count("need(proc.returncode==0") == 1
worker.write_text(base.replace("sys.path.insert(0,str(Path(__file__).resolve().parent))", f"sys.path.insert(0,{str(w)!r})")
                    .replace("need(proc.returncode==0","dump(a.out/'rustc-status.json',{'rustc_status':proc.returncode})\nneed(proc.returncode==0"))
program = (s / "readers-after-rejection.py").read_text()
for old, new in [
    ("'readers-ablation';sys.path", "'readers-real-exitcodes';sys.path"),
    ("p=s/'exports'/(digest+suffix)", "p=s.parent/'readers-ablation'/'exports'/(digest+suffix)"),
    ("str(w/'bridge_worker.py')", repr(str(worker))),
]:
    assert program.count(old) == 1, old
    program = program.replace(old, new)
runner.write_text(program)
p = subprocess.run([sys.executable, "-B", str(runner)], check=True)
result = s / "readers-real-exitcodes"
rows = json.loads((result / "all-readers.json").read_bytes())
original = json.loads((s / "readers-ablation/all-readers.json").read_bytes())
def invariant(row):
    return [row[k] for k in ("case","crate","status","codes","stderr","argv_sha","runtime","producer_full_svh","producer_rmeta_sha","producer_archive_sha")]
assert list(map(invariant, rows)) == list(map(invariant, original))
out = {row["case"]: json.loads((result / row["case"] / "receipt/rustc-status.json").read_bytes())["rustc_status"] for row in rows}
assert all(out[row["case"]] == row["status"] for row in rows)
(result / "actual-rustc-exits.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")
print("Replayed 30 original rustc argv and identical stderr, metadata and runtime with actual exit capture.")

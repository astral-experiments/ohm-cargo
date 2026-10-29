"""Check the real Ruff test edit and recreate all three source states in a temporary directory."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

packet = Path(__file__).resolve().parent
project = Path(sys.argv[1]).resolve()
study = json.loads((packet / "source.json").read_bytes())
base = study["ruff_base"]
history = study["ruff_history_commit"]
filename = study["sole_historical_git_path"]


def git(*args):
    return subprocess.check_output(["git", "-C", str(project), *args])


def digest(data):
    return hashlib.sha256(data).hexdigest()


assert git("diff-tree", "--no-commit-id", "--name-only", "-r", history).decode().splitlines() == [filename]
assert git("rev-parse", history + "^").decode().strip() == study["history_parent"]
for rev, key in ((base, "base_git_blob"), (history + "^", "historical_before_blob"), (history, "historical_after_blob")):
    assert git("rev-parse", rev + ":" + filename).decode().strip() == study[key]
subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", history, base], check=True)
patch = git("diff", "--binary", "--full-index", history + "^", history, "--", filename)
assert patch == (packet / "historical.patch").read_bytes()
assert digest(patch) == study["historical_patch_sha256"]
original = git("show", base + ":" + filename)
with tempfile.TemporaryDirectory(prefix="ohm-ruff-e2e-source-") as tmp:
    root = Path(tmp)
    path = root / filename
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    for operation in (["--reverse", "--check"], ["--reverse"]):
        subprocess.run(["git", "apply", *operation, "-"], cwd=root, input=patch, check=True)
    edited = path.read_bytes()
    subprocess.run(["git", "apply", "-"], cwd=root, input=patch, check=True)
    assert path.read_bytes() == original != edited
    indent = b"fn default_inlay_hints() -> Result<()> {\n"
    assert edited.count(indent) == 1
    invalid = edited.replace(indent, indent + study["invalid_statement"].encode() + b"\n")
    assert invalid.splitlines()[study["invalid_line"] - 1].decode() == study["invalid_statement"]
    assert {name: digest(raw) for name, raw in (("original", original), ("edited", edited), ("invalid", invalid))} == study["source_sha256"]
print("Genuine one-file Ruff edit, inverse, invalid control, and exact restoration verified.")

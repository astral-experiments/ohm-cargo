"""Read back an existing ty_server qualification from native traces and Cargo JSON."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

def digest(path):
    with path.open("rb") as src:
        return hashlib.file_digest(src, "sha256").hexdigest()

def executions(path):
    pending = None
    for line in path.read_text().splitlines():
        if line.endswith("<unfinished ...>"):
            assert pending is None
            pending = line.removesuffix("<unfinished ...>")
            continue
        if line.startswith("<... "):
            name, line = line.split(" resumed>", 1)
            assert pending is not None and pending.startswith(name[5:] + "(")
            line, pending = pending + line, None
        if not (line.startswith(("execve(", "execveat(")) and re.search(r"= 0\s*$", line)):
            continue
        m = re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), .*?\)\s*= 0', line)
        assert m is not None, line[:150]
        yield Path(ast.literal_eval(m[1])), ast.literal_eval(m[2])
    assert pending is None

def read(p):
    return json.loads(p.read_bytes())

root, sdk = (Path(arg).resolve() for arg in sys.argv[1:])
w = root / "work"
state = read(w / "terminal.json")
assert (root/"exit").read_text() == "0\n" and len(state) == 15
assert digest(w/"terminal.json") == "721b192a55c7749987c8ccf4a7e654270b33b48b153f192e73538429c69e9d3f"
rustc = sdk/"bin/rustc"
wild = sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
assert digest(rustc) == (w/"rustc.sha256").read_text().strip()
assert digest(wild) == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
assert digest(sdk/"lib/librustc_driver-15d35e5526bb94f8.so") == "5becad96c462ebded234e1cfe87d9ed86f66d7ef364a26cff507495165a7ad82"
expected_tests = ["inlay_hints::default_inlay_hints", "notebook::hover_past_end_of_cell", "notebook::inlay_hints_range_past_end_of_cell"]
out = {}
selected = None
for i, (label, reported) in enumerate(sorted(state.items()), 1):
    d = w/label
    assert reported == read(d/"result.json") and label.startswith(f"{i:02d}-")
    cargo_rows = [json.loads(line) for line in (d/"stdout").read_bytes().splitlines()]
    assert cargo_rows[-1] == {"reason":"build-finished","success":reported["cargo"] == 0}
    artifacts = [v for v in cargo_rows if v["reason"] == "compiler-artifact"]
    assert (len(artifacts), sum(a["fresh"] for a in artifacts)) == (reported["typed"], reported["fresh"])
    if reported["cargo"] == 0:
        exe, = [Path(a["executable"]) for a in artifacts if a["target"]["kind"] == ["test"] and a["target"]["name"] == "e2e" and Path(a["manifest_path"]).parts[-3:] == ("crates", "ty_server", "Cargo.toml")]
        selected = exe
    counts = Counter()
    members = hashlib.sha256()
    paths = sorted((d/"trace").glob("exec.*"))
    for path in paths:
        members.update(path.name.encode()+b"\0"+bytes.fromhex(digest(path)))
        for name, args in executions(path):
            if name.name == "rustc" and ("--crate-name" in args and "--out-dir" in args or "link-only" in args or "-Zlink-only" in args):
                assert name.samefile(rustc), name
                kind = "cached_rustc" if "link-only" in args or "-Zlink-only" in args else "full_rustc"
                counts[kind] += 1
            if name.name in ("ld.bfd", "ld.wild", "wild") and "-o" in args:
                assert name.samefile(wild), name
                counts["wild"] += 1
                if Path(args[args.index("-o")+1]) == selected:
                    counts["e2e_wild"] += 1
    assert (counts["wild"], counts["e2e_wild"]) == (reported["wild"], reported["e2e_wild"])
    assert counts["e2e_wild"] == (0 if i == 6 else 1)
    assert (reported["cargo"] == 101) == (i in (6,11,13))
    if i == 6:
        errors = [v["message"] for v in cargo_rows if v["reason"]=="compiler-message" and (v["message"].get("code") or {}).get("code") == "E0308"]
        assert len(errors)==1 and any(s["is_primary"] and s["line_start"]==22 for s in errors[0]["spans"])
    if i in (11,13):
        assert b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in (d/"stdout").read_bytes()+(d/"stderr").read_bytes()
    n = 0
    if reported["list"] is not None:
        assert digest(d/"listing") == reported["list"]
        names = [v[:-6].decode() for v in (d/"listing").read_bytes().splitlines() if v.endswith(b": test")]
        assert len(set(names)) == len(names) == 200
        for ix, name in enumerate(expected_tests):
            assert name in names
            case = (d/f"case-{ix}").read_text().splitlines()
            assert f"test {name} ... ok" in case and any("1 passed; 0 failed;" in s for s in case)
            n += 1
    out[label] = dict(**reported,full_rustc=counts["full_rustc"],cached_rustc=counts["cached_rustc"],raw_exec_files=len(paths),raw_exec_sha256=members.hexdigest(),case_passes=n)
assert selected is not None and selected.is_file()
retained = [selected,w/"warm-edited-elf",w/"10-forced-higher.incumbent",w/"13-forced-malformed.incumbent"]
phases = [15,4,9,12]
loader = Path("/lib64/ld-linux-x86-64.so.2")
actual = []
for path, i in zip(retained, phases, strict=True):
    expected = list(out.values())[i-1]
    assert digest(path) == expected["elf"]
    cmd = subprocess.run([loader,path,"--list"],capture_output=True,cwd=w/"ruff"/"crates"/"ty_server")
    assert cmd.returncode == (83 if i==9 else 0) and not cmd.stderr
    if i == 9:
        assert not cmd.stdout
    else:
        assert hashlib.sha256(cmd.stdout).hexdigest()==expected["list"]
    actual.append(dict(visit=i,bytes=path.stat().st_size,sha256=digest(path),list_exit=cmd.returncode))
subprocess.run(["cmp","--",retained[0],retained[1]],check=True)
print(json.dumps(dict(rust="05efba7a06f5bb71d1efb4b86805800f8b810779",cargo="7277e6cdaba44c43294a07c0661fc8e69fd8e3e7",sdk=read(root/"started.json")["physical_sdk"],terminal=digest(w/"terminal.json"),execution="Optimized Linux stage1, release source pins, stock Wild",phases=out,programs=actual),sort_keys=True,indent=2))

"""Recompute the matched RC results from process clocks and independently verify the outputs."""
from pathlib import Path
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda files, n: json.loads(files[n])
if (root / "SHA256SUMS").exists():
    subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=root, check=True)
index = json.loads(gzip.decompress((root / "inventory.json.gz").read_bytes()))
seen = set()

def archive(name):
    files = {}
    with tarfile.open(root / (name + ".tar.gz")) as t:
        for m in t:
            assert m.isfile() and m.name not in seen and m.name in index, m.name
            old, new, old_size, new_size, replacements = index[m.name]
            b = t.extractfile(m).read()
            assert sha(b) == new and len(b) == new_size
            assert replacements or (old == new and new_size == old_size)
            files[m.name] = b
            seen.add(m.name)
    return files

def cargo_stream(raw):
    stream = [json.loads(line) for line in raw.splitlines()]
    assert stream[-1] == {"reason": "build-finished", "success": True}
    units = [r for r in stream if r["reason"] == "compiler-artifact"]
    columns = ("package_id", "manifest_path", "target", "profile", "features", "filenames", "executable")
    ordered = lambda rows: sorted(json.dumps(v, sort_keys=True) for v in rows)
    return (ordered({k: r[k] for k in columns} for r in units),
            ordered(r for r in stream if r["reason"] == "compiler-message"),
            sorted(r["target"]["name"] for r in units if not r["fresh"]),
            sorted({r["executable"] for r in units if r["executable"]}))

def retained(a, b):
    assert a["normalized"] == b["normalized"] and a["bytes"] == b["bytes"] > 0
    assert len(a["normalized"]) == 64
    assert a["rodata_entsize"] == b["rodata_entsize"] or min(a["rodata_entsize"], b["rodata_entsize"]) == 0

c = archive("controls")
protocol = "protocol/"
plan = read(c, protocol + "plan.json")
grant = read(c, protocol + "grant.json")
terminal = read(c, "trial/complete.json")
assert c[protocol + "outer.exit"] == b"0" and not c[protocol + "outer.stderr"]
assert terminal["commands"] == 96 and terminal["grant"] == index[protocol + "grant.json"][0]
assert terminal["manifest"] == grant["manifest"] == index[protocol + "SHA256SUMS"][0] == "3f221463ac73479db4bd4e5601aa6ed133869e3cfdc886c259291d127c12cea6"
frozen = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in c[protocol+"SHA256SUMS"].decode().splitlines()}
for name in ("plan.json", "score.py", "statistics_local.py", "clock.py", "amendment.json","checked-pairs.json","namespace_paths.py"):
    assert frozen[name] == index[protocol+name][0]
assert plan["sources"] == grant["sources"] and grant["profile_gate"] and grant["safety_gate"]
assert grant["plan_commit"] == "176bd9de89b2d834aad953afa6ebc7b024b5f811"
assert plan["debug_qualification"] == "4dd4b47a36089dae1fa0a5f8900ce8fcb8d99179"
assert grant["safety_commit"] == "3f1fe2a410368d527055d9fcd2c2fd9f663d8fae"
for a, functions, samples, digest in (
    ("B", 13384, 159565724571, "a2552b8b128e30d019cdf00a8e8d2a15c57b9769771330e3b931728ca212653f"),
    ("C", 13381, 159565719144, "8d8f55631196157f9017974caaeeed33602f20e3c5760754b40d138a27141563"),
):
    assert grant["profiles"][a] == dict(functions=functions, samples=samples, stale_pct=5.3, report_sha256=digest)
assert all(read(c, "trial/elf-selftest.json").values())
assert sha((root/"namespace_paths.py").read_bytes()) == frozen["namespace_paths.py"]
sys.path.insert(0,str(root))
import namespace_paths as names
assert names.selftest()
cross = read(c, "trial/cross-arm.json")
assert cross == read(c, "protocol/checked-pairs.json")
rows = {}
last_stop = 0
counts = {}
for w, (units, files, executables, base_dirty, selection) in {
    "package": (303, 4, 1, 6, ["-p", "ty_project"]),
    "workspace": (619, 110, 102, 56, ["--workspace"]),
}.items():
    refs, lists, errors = {}, {}, {}
    shared_stream = None
    for a in "BC":
        suffix = w + "-" + a + "/"
        ref = "reference/" + suffix
        product = read(c, ref + "product.json")
        refs[a] = product["native"]
        assert len(refs[a]) == files and len(product["executables"]) == executables
        assert product["units"] == units and product["tests_executed"] == 0
        assert product["wild"] == (0 if a == "C" else (1 if w == "package" else 50))
        expected = {"full": 2, "link-only": 1} if w == "package" else {"full": 1, "link-only": 50}
        assert product["rustc"] == (expected if a == "B" else {})
        assert len(product["dirty"]) == (base_dirty if a == "B" else 0)
        lists[a] = c[ref + "list.stdout"]
        errors[a] = c[ref + "list.stderr"]
        assert lists[a] and index[ref + "list.stdout"][0] == product["oracle"]
        binding = read(c, "priming/" + suffix + "binding.json")
        image = grant["arms"][a]["binding"]
        assert set(binding["hashes"].values()) == {image[k] for k in ("driver", "frontend", "cargo_sha", "wild")}
        assert binding["sysroot"].endswith("/Ohm-SDK" if w == "package" else "/Ohm SDK")
        arm_stream = None
        for where in (ref + "stdout", "priming/"+suffix+"fresh.stdout", "final/"+suffix+"fresh.stdout"):
            roster, diag, dirty, exes = cargo_stream(c[where])
            assert len(roster) == units and len(exes) == executables and exes == sorted(product["executables"])
            assert dirty == sorted(product["dirty"])
            if arm_stream is None:
                arm_stream = (roster, diag, exes)
            assert (roster,diag,exes)==arm_stream
            typed = (names.units(w,a,roster), diag, sorted(names.key(w,a,n) for n in exes))
            if shared_stream is None:
                shared_stream=typed
            assert typed==shared_stream
            assert b"Blocking waiting" not in c[where.replace("stdout", "stderr")]
    assert lists["B"] == lists["C"] and errors["B"] == errors["C"]
    paths = {a:names.products(w,a,refs[a]) for a in "BC"}
    assert paths["B"].keys()==paths["C"].keys()
    expected={}
    for n in paths["B"]:
        raw=[refs[a][paths[a][n]] for a in "BC"]
        if raw[0]!=raw[1]:expected[n]=raw
    assert expected==cross[w] and len(expected)==(4 if w=="workspace" else 0)
    rows[w] = []
    differences = 0
    for i, order in enumerate(plan["orders"][w], 1):
        d = archive(w + f"-{i:02}")
        ns = {}
        for a in order:
            prefix = w + f"/{i:02}-" + a + "/"
            v = read(d, prefix + "verified.json")
            clock = read(d, prefix + "clock.json")
            assert clock["start"] > last_stop and clock["stop"] > clock["start"]
            last_stop = clock["stop"]
            assert clock["argv"] == ["cargo", "+ohm", "test", "--no-run", *selection, "--locked", "--offline", "-j4"]
            assert v["ns"] == clock["elapsed_ns"] == clock["stop"] - clock["start"] and clock["returncode"] == 0
            assert v["workflow"] == w and v["role"] == a
            assert not d[prefix+"stdout"] and b"Finished" in d[prefix+"stderr"] and b"Blocking waiting" not in d[prefix+"stderr"]
            assert d[prefix + "list.stdout"] == lists[a] and d[prefix + "list.stderr"] == errors[a]
            assert v["list"] == index[prefix+"list.stdout"][0]
            assert set(v["native"]) == set(refs[a])
            changed = {n for n, h in v["native"].items() if h != refs[a][n]}
            assert changed == set(v["variation"]) and (a == "B" or not changed)
            for x, y in v["variation"].values():
                retained(x, y)
            differences += len(changed)
            ns[a] = v["ns"]
        rows[w].append(dict(order=order, ns=ns))
    assert len(rows[w]) == 24 and rows[w] == read(c, "trial/ledger-"+w+".json")
    counts[w] = {"native_count": files, "bound_debug_pairs": len(cross[w]), "baseline_differences_across_slots": differences}
assert rows == read(c, "trial/all.json") and seen == index.keys()
assert sha((root/"statistics_local.py").read_bytes()) == frozen["statistics_local.py"]
sys.path.insert(0, str(root))
from statistics_local import analyze
results = analyze(plan, rows)
assert results == read(c, "trial/result.json")
print(json.dumps(dict(commands=96, results=results, outputs=counts), sort_keys=True))

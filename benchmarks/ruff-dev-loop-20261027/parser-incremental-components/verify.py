"""Verify the saved component split, ordinary callers, raw syscall evidence and graph."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def raw(p):
    p = ROOT / p
    return gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()

def load(p):
    return json.loads(raw(p))

def sha(b):
    return hashlib.sha256(b).hexdigest()

def table_path(r):
    return r["recipient"] + "-" + r["kind"] + ("-" + r["bridge"] if r["bridge"] else "")

manifest = (ROOT/"SHA256SUMS").read_text().splitlines()
expected = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
observed = set()
for line in manifest:
    digest, name = line.split("  ", 1)
    assert name in expected and name not in observed and digest == sha((ROOT/name).read_bytes()), name
    observed.add(name)
assert expected == observed

design = load("cargo/design.json")
full = load("cargo/results.json.gz")
complete = load("cargo/complete.json")
assert complete["unscored"] and complete["experiments"] == 14
assert complete["results_sha256"] == sha(raw("cargo/results.json.gz"))
warm = {"all", "no-prefix", "no-metadata", "no-work-products"}
cold = {"empty", "no-query", "no-graph"}
runtime = "Bytes literal cannot be mixed with non-bytes literals at byte range 0..18"
identities = {
    "A": ("8738be14814a2dad789dee6fb3ba1914", "4b38929971381640e894a8a9ecce65a0"),
    "B": ("25535f27dd2a2861b88a8bdc1d645bfb", "0853fb0709f6e7b1c1a30289347a0a02"),
}
assert set(full) == set(identities)
aliases = load("syscall-audit/cargo-alias-to-mapped-path.json")
graph = load("graph/comparison.json")
for arm, rows in full.items():
    assert set(rows) == warm | cold
    base = rows["all"]
    for label, row in rows.items():
        data = f"cargo/{arm}/{label}"
        assert row == load(f"{data}/result.json")
        stdout = [json.loads(z) for z in raw(f"{data}/stdout.gz").splitlines()]
        assert sum(x["reason"] == "compiler-artifact" for x in stdout) == row["unit_count"] == 501
        assert stdout[-1] == {"reason":"build-finished","success":True}
        assert row["command"] == ["cargo","+ohm","build","--locked","--offline","--message-format=json"]
        assert row["driver"] == design["driver"][arm] and row["cargo"] == design["cargo"][arm]
        assert row["status"] == 0 and row["source"] == "edited" and len(row["rustc_jobs"]) == 9
        assert row["rustc_jobs"].count(["ruff_python_parser",False]) == 1
        assert all(row[k] == base[k] for k in ("externs","rustc_argv","started_from","git_index"))
        assert row["parser_header"]["private"] == identities[arm][label in cold]
        assert row["parser_header"]["public"] == base["parser_header"]["public"]
        assert row["parser_header"]["stable"] == "6850405913612383189"
        md = row["rmeta_sha256"]
        assert md == rows["empty" if label in cold else "all"]["rmeta_sha256"]
        assert md == sha(raw(f"raw-rmeta/{md}.rmeta.gz"))
        assert row["parser_header"]["private"].encode() in raw(f"{data}/parser.root.txt")
    assert len({r["rmeta_sha256"] for r in rows.values()}) == 2
    for name in ("ordinary","syscall-audit"):
        prefix = f"{name}/{arm}"
        done = load(f"{prefix}/complete.json")
        results = load(f"{prefix}/readers.json")
        assert done["rows_sha256"] == sha(raw(f"{prefix}/readers.json"))
        subset = warm | cold if name == "ordinary" else {"all","empty"}
        assert len(results) == len(subset) * (len(subset) + 1) == done["commands"]
        assert done["failed"] == (24 if name=="ordinary" else 2) and done["timed_samples"] == 0
        assert {(r["recipient"],r["bridge"]) for r in results} == {(s,t) for s in subset for t in [None,*subset]}
        for r in results:
            p = f"{prefix}/{table_path(r)}"
            assert r["argv_sha"] == sha(raw(f"{p}/argv.json"))
            assert r["diagnostics"] == raw(f"{p}/stderr").decode()
            assert r["target_rlib_sha"] == rows[r["recipient"]]["rlib_sha256"]
            passed = not r["bridge"] or (r["bridge"] in warm) == (r["recipient"] in warm)
            assert (r["compiler_exit"] == 0) == passed
            if not passed:
                assert 'error[E0460]' in r["diagnostics"] and 'crate `ruff_python_parser` which `ordinary_parser_bridge` depends on' in r["diagnostics"]
            assert r["runtime"] == (runtime if passed and r["bridge"] else None)
            if name != "syscall-audit":
                continue
            assert r["mapped"] == load(f"{p}/observed-paths.json") and r["actual_driver"] == design["driver"][arm]
            mapped = r["mapped"]
            imgs = load(f"{p}/decoded-images.json")
            assert len(imgs)==2 and all(img["private"] == rows[r["recipient"]]["parser_header"]["private"] for img in imgs.values())
            rcpts = load(f"{p}/selected-syscalls.json")
            for path, m in mapped.items():
                assert m["opens"] >= 1 and m["mmaps"] >= 1 and any(path in line and "mmap(" in line for _, line in rcpts)
                if "ordinary_parser_bridge" in path:
                    assert m["sha256"] == r["bridge_sha"]
                else:
                    suffix = Path(path).suffix
                    other = aliases[arm][r["recipient"]][suffix]
                    assert other["rustc_mapped"] == path and other["same_inode"]
                    assert [m["dev"],m["ino"]] == other["rustc_dev_ino"] == other["Cargo_dev_ino"]
                    assert other["sha256"] == m["sha256"] == imgs[other["Cargo_advertised"]]["sha"]
            assert len(mapped) == (3 if r["bridge"] else 1)
    by = graph[arm]
    lhs, rhs = [load(f"graph/{arm}-{g}-roots.json.gz")["roots"] for g in ["all","empty"]]
    assert set(lhs) == set(rhs) and not by["warm_only"] and not by["cold_only"]
    counts = dict(collections.Counter(k.split("|",1)[0] for k in lhs))
    assert counts == by["groups_shared"] and counts["lower_to_hir"] == 4204 and counts["source_span"] == 2169
    changed = {k:[lhs[k]["value_fingerprint"],rhs[k]["value_fingerprint"]] for k in lhs if lhs[k]["value_fingerprint"] != rhs[k]["value_fingerprint"]}
    assert changed == by["changed"] and list(changed) == [by["root_key"]] and by["local_direct_edges"] == [0,0]
print("Verified 14 full-Cargo variations, 112 ordinary Rust compiles, 12 syscall-audited compiles, four raw parser metadata files, and both query-graph comparisons.")

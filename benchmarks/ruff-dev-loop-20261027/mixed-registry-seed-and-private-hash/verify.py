"""Recompute the exact registry selection, primary context failures and causal parser/readers evidence."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import re

root = Path(__file__).resolve().parent

def raw(name):
    file = root / name
    return file.read_bytes() if file.is_file() else gzip.decompress((root / (name + ".gz")).read_bytes())

def read(name):
    return json.loads(raw(name))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    manifest = root / "SHA256SUMS"
    expected_paths = set()
    for line in manifest.read_text().splitlines():
        expected, name = line.split("  ", 1)
        assert name not in expected_paths and not name.startswith(("/", "./", "../"))
        assert expected == sha((root / name).read_bytes()), name
        expected_paths.add(name)
    assert expected_paths == {str(f.relative_to(root)) for f in root.rglob("*") if f.is_file() and f != manifest}

    ref = read("preregistration.json")["fixed_reference"]
    fixed = ref["entire_shared_object_sha256"]
    attempts = read("selection/all-attempts.json")
    selected = read("selection/complete.json")
    assert selected["winner"] == selected["attempt_count"] == len(attempts) == 23 < 24
    assert selected["reference_registration"] == sha(raw("preregistration.json"))
    assert selected["timed_samples"] == 0 and raw("exclusions/cross-natural.rc").strip() == b"1"
    variants = read("selection/native-sections.json")
    assert len(variants) == len({v["sections"][".text"] for v in variants.values()}) == 6
    same_sources = set()
    for i, attempt in enumerate(attempts, 1):
        folder = f"selection/attempt-{i:02d}"
        assert attempt == read(folder + "/producer.json")
        assert attempt["attempt"] == i and attempt["target_artifact"]["fresh"] is False
        assert attempt["matches"] == (attempt["entire_so_sha256"] == fixed) == (i == 23)
        assert attempt["interrupted_after_rejected_producer"] == (i < 23)
        assert i in variants[attempt["entire_so_sha256"]]["attempts"]
        assert "metadata=" + ref["rustc_crate_disambiguator"] in attempt["rustc_argv"]
        same_sources.add(tuple(attempt["rustc_argv"]))
        observed = [row for line in raw(folder + "/stdout").splitlines()
                    if (row := json.loads(line)).get("target", {}).get("name") == "get_size_derive2"]
        assert observed == [attempt["target_artifact"]]
    assert len(same_sources) == 1 and attempts[-1]["command_exit"] == 0 and attempts[-1]["full_json_artifacts"] == 501
    assert variants[fixed]["sections"][".text"] == ref["text_sha256"]

    for arm in "ABC":
        d = "seed/" + arm
        projection, finished, inventory = (read(d + "/" + n) for n in ["projected.json", "complete.json", "projected-inventory.json"])
        assert projection["previous_workspace_artifacts"] == projection["previous_shared_files"] == 0
        assert projection["registry_units"] == len(read(d + "/registry-reported-units.json")) == 479
        assert projection["packages"] == len(read(d + "/verified-registry-packages.json")) == 346
        assert projection["included_files"] == len(inventory) == 5524
        assert projection["inventory_sha256"] == sha(raw(d + "/projected-inventory.json"))
        assert projection["expected_sha"] == finished["root_sha"] == fixed
        assert all(v["independent_inode"] and v["package"].startswith("registry+") for v in inventory.values())
        assert finished["actual_compiler_commands"] == finished["workspace_compiler_units"] == 68
        assert finished["fresh_workspace_units"] == finished["scored_commands"] == 0
        rows = [r for line in raw(d + "/cargo.stdout").splitlines() if (r := json.loads(line))["reason"] == "compiler-artifact"]
        assert len(rows) == finished["units"] == 501
        assert sum(r["fresh"] for r in rows) == finished["fresh_registry_units"] == 433
        assert all(r["fresh"] == r["package_id"].startswith("registry+") for r in rows)
    assert raw("seed/B/projected-inventory.json") == raw("seed/C/projected-inventory.json")
    plugins = read("matched-plugin/all.json")
    for arm, plugin in plugins.items():
        assert plugin["native_product_sha256"] == fixed and plugin["text_sha256"] == ref["text_sha256"]
        assert plugin["diagnostic"] == [ref["expected_first_conflict"]] and plugin["compiler_exit"] == 1
        assert plugin["compiled_extern_receipt"]["fresh"] and ref["public_and_private_rust_hash"] in raw(f"matched-plugin/{arm}/plugin.root.txt").decode()
    for crate in ["ref-cast", "rustversion", "serde_core", "terminfo", "thiserror"]:
        rows = [plugins[a]["leaves"][crate]["generated"] for a in "ABC"]
        key, = rows[0]
        a, b, c = (r[key] for r in rows)
        assert a["sha256"] == b["sha256"] == c["sha256"] and a["logical_path"] != b["logical_path"] == c["logical_path"]
        assert all(x["rustc_dep_files_containing_full_path"] for x in (a, b, c))

    for name, edge in [("same-compiler", "warm-B"), ("three-images", "cold-A")]:
        d = "mixed/" + name
        report, outcomes = read(d + "/comparisons.json"), read(d + "/readers.json")
        assert len(outcomes) == 24 and Counter(r["rustc_exit"] for r in outcomes) == {0: 16, 1: 8}
        assert read(d + "/complete.json")["scored"] == 0
        for r in outcomes:
            mismatch = r["action"] == "caller" and ((r["bridge_origin"] == edge) != (r["state"] == edge))
            assert (r["rustc_exit"] != 0) == mismatch
            if mismatch:
                assert "E0460" in r["stderr"] and "`" + r["crate"] + "`" in r["stderr"]
        for label, result in report.items():
            assert ("mismatch" in result["full_qualified_or_first_mismatch"]) == (edge in label)
            if label == "cold-B--cold-C":
                assert len(result["different_library_bytes"]) == 6
                for fields in result["mixed"].values():
                    assert all(left == right for left, right in fields.values())
            elif name == "three-images":
                assert len(result["different_library_bytes"]) == 87
                assert sum(k.startswith("registry+") for k in result["different_library_bytes"]) == 43
    diff = read("mixed/same-compiler-headers/differences.json")["warm-B--cold-B"]
    changed = {key.split("|")[1] for key,val in diff.items() if val["private"][0] != val["private"][1]}
    assert changed == {"ruff_python_parser", "ruff_wasm", "ty_wasm"}
    assert all(not d["changed_deps"] and len(set(d["public"])) == len(set(d["stable"])) == 1 for d in diff.values())
    assert len(read("mixed/cross-image-headers/first.json")) == 5

    rows = read("parser/controlled/variants.json")
    assert len(rows) == len({(r["ICH"], r["AST"]) for r in rows}) == 4
    assert len({r["starting_ich_sha256"] for r in rows}) == len({tuple(r["actual_parser_argv"]) for r in rows}) == 1
    assert len({r["direct_AST_sha256"] for r in rows}) == 2
    assert len({r["direct_AST_header"]["private"] for r in rows}) == 1
    assert all(r["command"][:3] == ["cargo", "+ohm", "build"] and r["after_parser"]["public"] == "924e1081fcbca11f1cdc1c1667ea69c8" for r in rows)
    ids = {"retained": "25535f27dd2a2861b88a8bdc1d645bfb", "empty": "0853fb0709f6e7b1c1a30289347a0a02"}
    for r in rows:
        assert r["after_parser"]["private"] == ids[r["ICH"]]
        assert sha(raw("parser/raw/" + r["parser_raw"] + ".rmeta")) == r["parser_raw"]
        assert r["after_parser"]["private"] in raw("parser/controlled/" + r["name"] + "/parser.after.root").decode()
    controls = read("parser/source-and-flags/summary.json")
    assert all(r["source_equal"] and not r["argv_differences"] for r in controls.values())
    assert set(controls["ruff_python_parser"]["changed_direct_inputs"]) == {"ruff_python_ast"}
    readers = read("parser/readers/readers.json")
    assert len(readers) == 20 and Counter(r["compiler_exit"] for r in readers) == {0: 12, 1: 8}
    for r in readers:
        base = r["recipient"] + "-" + r["kind"] + ("-" + r["bridge"] if r["bridge"] else "")
        assert sha(raw("parser/readers/" + base + "/argv.json")) == r["argv_sha"]
        assert raw("parser/readers/" + base + "/stderr").decode() == r["diagnostics"]
        if r["kind"] == "caller":
            compatible = r["recipient"].split("-")[0] == r["bridge"].split("-")[0]
            assert (r["compiler_exit"] == 0) == compatible
            if compatible:
                assert r["runtime"] == "Bytes literal cannot be mixed with non-bytes literals at byte range 0..18"
            else:
                assert "E0460" in r["diagnostics"] and "`ruff_python_parser`" in r["diagnostics"]
    assert read("exclusions/parser-extern-basename/complete.json")["failed"] == 16
    print("Verified 23 registered attempts, 3 registry-seeded full builds, 48 mixed bridge/caller commands, 4 isolated parser recompiles and their 20 reader commands. Zero timing samples.")

if __name__ == "__main__":
    main()

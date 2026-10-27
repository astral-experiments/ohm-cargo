"""Describe each ELF difference against independent warm, cold and unchanged-compiler controls."""
import argparse
import json
from pathlib import Path
import re


def compare(left, right):
    assert left["products"].keys() == right["products"].keys()
    def roster(items):
        return {(pkg, name, tuple(kind), test): path for pkg, name, kind, test, path in items}
    a_paths, b_paths = roster(left["executables"]), roster(right["executables"])
    assert len(a_paths) == len(left["executables"]) and len(b_paths) == len(right["executables"])
    assert a_paths.keys() == b_paths.keys()
    routes = set()
    path_changes = 0
    for item, a_path in a_paths.items():
        b_path = b_paths[item]
        if a_path == b_path:
            continue
        a_parts, b_parts = Path(a_path).parts, Path(b_path).parts
        assert len(a_parts) == len(b_parts)
        (difference,) = [(x, y) for x, y in zip(a_parts, b_parts) if x != y]
        assert all(re.fullmatch(r"v2-[0-9a-f]{16}-all-native-all", part) for part in difference)
        routes.add(difference)
        path_changes += 1
    assert left["samples"] == right["samples"]
    differences = {}
    for name, a in left["products"].items():
        b = right["products"][name]
        if a["raw_sha256"] == b["raw_sha256"]:
            continue
        x, y = a["sections"], b["sections"]
        missing = sorted(set(x) ^ set(y))
        changed = sorted(k for k in x.keys() & y if x[k] != y[k])
        allocated = [k for k in changed if x[k]["flags"] & 2 or y[k]["flags"] & 2]
        symbols = {}
        for k in x.keys() & y:
            if "decoded_set" in x[k] and x[k]["digest"] != y[k]["digest"]:
                symbols[k] = {"decoded_order_identical": x[k]["decoded_order"] == y[k]["decoded_order"],
                              "decoded_multiset_identical": x[k]["decoded_set"] == y[k]["decoded_set"]}
        differences[name] = {"missing_sections": missing, "changed_sections": changed, "allocated": allocated, "symbols": symbols}
    return {"identical_raw": len(left["products"]) - len(differences), "total": len(left["products"]),
            "executable_keys": len(a_paths), "paths_with_different_toolchain_namespace": path_changes,
            "toolchain_namespaces": sorted(routes),
            "exact_compiler_diagnostics": left["diagnostics"] == right["diagnostics"], "differences": differences}


cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument("directory", type=Path)
directory = cli.parse_args().directory
assert json.loads((directory / "complete.json").read_bytes())["source_clean"]
pairs = [("parent-warm", "candidate-warm"), ("parent-cold", "candidate-cold"),
         ("parent-warm", "parent-cold"), ("candidate-warm", "candidate-cold"),
         ("parent-cold", "candidate-warm")]
report = {}
for mode in ("build", "test"):
    inputs = {label: json.loads((directory / f"{label}-{mode}-edited.json").read_bytes()) for p in pairs for label in p}
    report[mode] = {"samples": inputs["parent-cold"]["samples"]}
    for a, b in pairs:
        report[mode][f"{a}--{b}"] = compare(inputs[a], inputs[b])
print(json.dumps(report, indent=2))

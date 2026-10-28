"""Re-read the untouched native Mac CI artifact and compare the two isolated compilers."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def h(x):
    return hashlib.sha256(x).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def verify(root):
    root = Path(root)
    host = (root / "host.txt").read_text()
    assert "47e23eb4bab742e271ca9a3cf1bbd583d5b4a640" in host.splitlines()
    assert "7181bfa6256f94da142f80fd6af09cee02ec2c78" in host.splitlines()
    assert "Darwin arm64" in host.splitlines()
    assert (root / "stock-archive.txt").read_text().strip() == "ohm-1.99.0-17-aarch64-apple-darwin.tar.gz: OK"
    harness = (root / "checked-in-run-make.txt").read_text()
    assert re.search(r"test result: ok\. 1 passed; 0 failed; 0 ignored;", harness), harness
    phases = ["original", "edited", "repeat", "edited-empty", "restored", "restored-empty"]
    builds = ["original", "edited", "restored"]
    reports = {}
    for arm in ("stock", "fixed"):
        folder = root / arm
        summary = read_json(folder / "result.json")
        assert summary["arm"] == arm
        assert "host: aarch64-apple-darwin" in (folder / "version.stdout").read_text()
        assert {k for k in summary["inputs"] if k.startswith("librustc_driver")} and "rustc" in summary["inputs"]
        assert set(summary["native"]) == set(builds)
        for target in ("object", "dylib"):
            functions = [summary["native"][n][target]["sections"]["__TEXT,__text"] for n in builds]
            assert functions[0] != functions[1] and functions[0] == functions[2]
        commands = read_json(folder / "commands.json")
        index = {r["label"]: r for r in commands}
        expect = ["version", "sysroot"]
        for phase in phases:
            if phase in builds:
                expect.extend([phase + "-cc", phase + "-macro"])
            expect.extend([phase + "-rustc", phase + "-run"])
        assert [r["label"] for r in commands] == expect and len(index) == len(expect) == 20
        for c in commands:
            assert c["exit"] == 0
            for ext in ("stdout", "stderr"):
                assert h((folder / (c["label"] + "." + ext)).read_bytes()) == c[ext + "_sha256"]
        run_values = {n: (folder / (n + "-run.stdout")).read_text().strip() for n in phases}
        assert run_values == summary["values"]
        assert run_values["original"] == run_values["restored-empty"] == "17,17"
        assert run_values["edited-empty"] == "29,29"
        for n in phases:
            assert re.fullmatch(r"(17|29),(17|29)", run_values[n])
        if arm == "fixed":
            assert run_values["edited"] == run_values["repeat"] == "29,29" and run_values["restored"] == "17,17"
        argsets = {n: index[n + "-rustc"]["argv"] for n in phases}
        assert all(argsets[n] == argsets["original"] for n in ("edited", "repeat", "restored"))
        eq_args = lambda n: [arg for arg in argsets[n] if not arg.startswith("-Cincremental=")]
        assert all(eq_args(n) == eq_args("original") for n in phases)
        assert all(a in eq_args("original") for a in ("-Zcache-proc-macros", "reader.rs", "native=libnative.dylib"))
        paths = {n: next(a for a in argsets[n] if a.startswith("-Cincremental=")) for n in phases}
        assert len({paths["original"], paths["edited-empty"], paths["restored-empty"]}) == 3
        for n in builds:
            assert index[n + "-cc"]["argv"] == ["cc", "-fPIC", "-c", "value.c", "-o", "value.o"]
            assert index[n + "-macro"]["argv"][-2:] == ["native.rs", "-Clink-arg=value.o"]
        first, second = [summary["native"][n]["dylib"]["sections"] for n in ("original", "edited")]
        reports[arm] = {"values": run_values, "commands": len(commands), "reader_rustcs": len(phases),
                        "c_compiles": len(builds), "proc_macro_rustcs": len(builds), "inputs": summary["inputs"],
                        "dylib_sections_changed": sorted(k for k in first.keys() | second.keys() if first.get(k) != second.get(k)),
                        "checked_in_fixture_result": "passed on candidate" if arm == "fixed" else "stock fixture measured by the direct native replay"}
    for source in ("native.rs", "reader.rs"):
        assert reports["fixed"]["inputs"][source] == reports["stock"]["inputs"][source]
    assert reports["stock"]["inputs"]["rustc"] != reports["fixed"]["inputs"]["rustc"]
    return reports


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact_dir")
    ns = ap.parse_args()
    print(json.dumps(verify(ns.artifact_dir), indent=2, sort_keys=True))

"""Verify the finite recorded Ruff comparison from the typed workspace and native records."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import re


def read(name):
    value = (packet / name).read_bytes()
    if name.endswith(".gz"):
        value = gzip.decompress(value)
    return json.loads(value)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def multiset(row, role, argument):
    return Counter((e["target"], e[argument]) for e in row["rust"] if e["role"] == role)


packet = Path(__file__).resolve().parent
manifest = packet / "SHA256SUMS"
listed = {}
for line in manifest.read_text().splitlines():
    digest, name = line.split("  ", 1)
    assert name not in listed and Path(name).name == name
    assert sha((packet / name).read_bytes()) == digest
    listed[name] = digest
assert set(listed) == {p.name for p in packet.iterdir() if p.name != manifest.name}
deny = re.compile(
    rb"openai[.](org|com|internal)|artifactory[.]|authorization" rb": bearer|github_" rb"pat_|ghp_[a-z0-9]{16}|"
    rb"/home/dev" rb"-user/|/mnt/devbox" rb"-scratch/|charlie-" rb"ohm-",
    re.I,
)
for name in listed:
    b = (packet / name).read_bytes()
    assert len(b) < 8_000_000
    b = gzip.decompress(b) if name.endswith(".gz") else b
    assert not deny.search(b), name

result = read("result.json")
provenance = read("provenance.json")
typing = read("typed-units.json.gz")
diag = read("elf-fields.json.gz")
compare = read("comparison.json.gz")
spec = importlib.util.spec_from_file_location("stock_elf_fields", packet / "elf.py")
elf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elf)
assert listed["elf.py"] == diag["fields_source_sha256"]
assert elf.selftest() == diag["selftest"]
assert result["schema"] == 1 and result["complete"]
assert result["admissible"] == all(result["checks"].values())
assert set(result["fatal_checks"]) == {k for k, v in result["checks"].items() if not v}
assert listed["result.json"] == provenance["raw_functional_result"]
assert provenance["comparison"] == result["receipts"]["comparison"]
assert provenance["diagnostics"] == result["receipts"]["elf_fields_diagnostic"]
assert result["independent_configured_native_matrix"]["commands"] == 132
assert result["independent_configured_native_matrix"]["configurations"] == 18
assert result["independent_configured_native_matrix"]["manifest_sha256"] == "c118586cacf970fcef2d9ab350c3967da41d4ffe1f3f3401de686d8d71d3c7e5"
assert {k for k, v in compare["checks"].items() if not v} <= set(result["fatal_checks"])

raw_catalogs = typing["typed_rosters"]
assert len(raw_catalogs) >= 1
for units in raw_catalogs.values():
    assert len(units) == 619
    assert all(len(e["unit_sha256"]) == 64 and e["name"] and e["kind"] for e in units)
assert len(typing["original_roster_files"]) == 10
assert result["checks"]["all_619_typed_rosters_identical"] == (len(raw_catalogs) == 1)
rows = {}
command = ["cargo", "+ohm", "test", "--workspace", "--no-run", "--locked", "--offline", "-j8", "--message-format=json"]
image = {"A": "a20b7097d6c0591464583de00bea1ee8d39bddfe461d56318532fb57991a8db7",
         "B": "8e10b884f56d6807872c61d587b7cf152c03f04fe11e10b8bc412880f15c0ad0"}
oracle = {"original": "be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7",
          "notebook": "d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8"}
named = {"notebook::hover_past_end_of_cell", "notebook::inlay_hints_range_past_end_of_cell"}
full = "rustc-full"
partial = "rustc-link-only"
cases = {state: set() for state in oracle}
for arm, arm_info in result["arms"].items():
    assert arm_info["sha256"] == image[arm] and len(arm_info["source_phases"]) == 5
    for phase, bound in arm_info["source_phases"].items():
        key = arm + "-" + phase
        r = read(key + ".json.gz")
        rows[arm, phase] = r
        assert r["command"] == command and (r["arm"], r["phase"]) == (arm, phase)
        assert r["units"] == bound["units"] == 619
        assert r["inputs"]["execs"] == bound["native_exec_argv_and_exit_sha256"]
        assert r["inputs"]["rust_args"] == bound["rust_argv_sha256"]
        assert r["inputs"]["native_elf"] == bound["native_outputs_sha256"]
        assert r["inputs"]["raw_result"] == bound["result_sha256"]
        assert r["inputs"]["typed619"] == typing["original_roster_files"][key]
        src = typing["source_phases"][key]
        assert src["source_head"] == result["tools"]["source"]
        assert src["image_sha256"]["cargo"] == image[arm]
        assert src["image_sha256"]["rustc"] == result["tools"]["rustc"]
        assert src["image_sha256"]["stock-wild"] == result["tools"]["wild"]
        assert src["native_driver_sha256"] == result["tools"]["driver"]
        assert r["runtime"] == bound["selected_rust_tests"] and set(r["runtime"]) == named
        rc = 101 if r["state"] == "notebook" else 0
        assert set(r["runtime"].values()) == {rc}
        assert {(e["line"].split()[1], e["line"].split()[-1]) for e in r["actual_test_stdout"]} == {
            (name, "FAILED" if rc else "ok") for name in named
        }
        assert bound["e2e_list_count"] == 200
        assert r["listing_sha256"] == "e3254bff0fba6072df809c053ef4e7d7b6490d144568bf3fb4cd6916bd4db316"
        assert r["e2e"]["sha256"] == bound["e2e_sha256"]
        cases[r["state"]].add(r["e2e"]["sha256"])
        assert Counter(e["role"] for e in r["events"]) == r["counts"] == bound["counts"]
        assert {e["pid"] for e in r["events"] if e["exit"]} == {e["pid"] for e in r["configure"]}
        assert all(e["exit"] == 1 and e["role"] in ("gcc", "collect2") for e in r["configure"])
        if r["mode"] != "cold":
            assert not r["configure"]
        actual_rust = Counter((e["role"], e["crate"], e["sha256_of_original_nul_argv"]) for e in r["events"] if e["role"] in (full, partial))
        assert actual_rust == Counter((e["role"], e["target"], e["arg_sha256"]) for e in r["rust"])
        for e in r["rust"]:
            assert e["exit"] == 0 and e["flag_pos"] > 0
            assert e["flag"] == ("-Zthreads=1" if arm == "B" and e["role"] == partial else "-Zthreads=8")
        wilds = Counter(e["out"] for e in r["events"] if e["role"] == "stock-wild")
        assert set(wilds) == set(r["native_elf"])
        if r["mode"] == "cold":
            assert r["fresh"] == 0 and r["counts"][full] >= 619
        if r["mode"] == "repeat":
            assert sorted(e["target"] for e in r["rust"] if e["role"] == full) == ["ron"]
            assert r["counts"][partial] == sum(wilds.values()) == len(wilds) == 50
        assert all(e["exit"] == 0 for e in r["events"] if e["role"] in ("cargo", full, partial, "stock-wild"))
assert result["checks"]["e2e_matches_independent_cold_endpoints"] == all(len(v) == 1 for v in cases.values())
assert result["checks"]["both_clean_worlds_match_independently_qualified_release"] == (
    rows["A", "seed"]["e2e"]["sha256"] == oracle["original"] and rows["B", "seed"]["e2e"]["sha256"] == oracle["notebook"]
)
for phase in ("notebook-edit", "notebook-restore", "final-repeat"):
    tag = phase + "__" + phase
    a, b = rows["A", phase], rows["B", phase]
    c = compare["comparisons"][tag]
    assert c["full_argv_matched"] == (multiset(a, full, "arg_sha256") == multiset(b, full, "arg_sha256"))
    assert c["link_only_all_other_arg_bytes_matched"] == (
        multiset(a, partial, "all_other_argv_sha256") == multiset(b, partial, "all_other_argv_sha256")
    )
    left, right = a["native_elf"], b["native_elf"]
    shared = set(left) & set(right)
    unequal = {k for k in shared if left[k] != right[k]}
    assert c["raw_common_native_outputs"] == len(shared)
    assert c["raw_matched_native_outputs"] == len(shared - unequal)
    assert set(c["unmatched_native_output_records"]) == unequal == set(diag["results"][tag])
    assert result["stock_elf_comparisons"][tag]["dispositions"] == dict(Counter(v["disposition"] for v in diag["results"][tag].values()))
    for k in unequal:
        detail = diag["results"][tag][k]
        raw = detail.get("raw_sha256") or [detail.get("sha256_A"), detail.get("sha256_B")]
        assert raw == [left[k]["sha256"], right[k]["sha256"]]
        if diag["results"][tag][k]["disposition"] != "stock-rodata-and-build-id-only":
            continue
        x, y = left[k]["stock_width_fields"], right[k]["stock_width_fields"]
        assert x["bytes"] == y["bytes"] and x["normalized"] == y["normalized"] and x["build_id"] != y["build_id"]
        assert min(x["rodata_entsize"], y["rodata_entsize"]) == 0
        assert max(x["rodata_entsize"], y["rodata_entsize"]) in (1, 2, 4, 8, 16, 32, 64, 128, 256)
print(json.dumps({"workspace_commands": len(rows), "typed_units_per_command": 619,
                  "actual_process_events": sum(len(r["events"]) for r in rows.values()),
                  "eligible_for_parent_admission": result["admissible"], "failed_checks": result["fatal_checks"],
                  "stock_elf_comparisons": result["stock_elf_comparisons"]}, sort_keys=True))

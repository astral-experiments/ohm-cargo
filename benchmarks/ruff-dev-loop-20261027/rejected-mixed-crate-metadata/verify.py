from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
for line in (root / "SHA256SUMS").read_text().splitlines():
    expected, name = line.split("  ", 1)
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
data = json.loads((root / "real.json").read_bytes())
for arm, row in data["controls"].items():
    children = row["edit"]["rustcs"]
    assert row["edit"]["cargo_units"] == 362 and row["edit"]["reported_dirty"] == 20
    assert {ch["crate"] for ch in children} == {"ruff_wasm", "ty_wasm", "ruff_python_parser"}
    assert {ch["crate"] for ch in children if ch["link_only"]} == ({"ruff_wasm", "ty_wasm"} if arm == "paired" else set())
    assert row["immediate_noop_rustcs"] == []
    assert row["initial_noop_rustcs"] == (365 if arm == "cargo_only" else 0)
    assert row["fresh_direct_callers"] == data["controls"]["paired"]["fresh_direct_callers"]
for crate, item in data["deltas"].items():
    x, y = item["paired"], item["compiler_only"]
    assert x["public_svh"] == y["public_svh"] and x["stable_crate_id"] == y["stable_crate_id"]
    assert x["ordered_object_payloads_sha256"] == y["ordered_object_payloads_sha256"]
    assert x["object_count"] == y["object_count"]
    if crate == "ruff_python_parser":
        assert item["different_count"] == 0 and x["standalone_sha256"] == y["standalone_sha256"]
        continue
    assert item["different_count"] == item["last_different_offset"] - item["first_different_offset"] + 1 == 16
    assert x["cdylib_sha256"] == y["cdylib_sha256"]
    assert x["standalone_sha256"] != y["standalone_sha256"]
    assert x["archived_metadata_object_sha256"] != y["archived_metadata_object_sha256"]
    for arm in ["paired", "compiler_only"]:
        assert bytes.fromhex(item[arm + "_private_bytes_hex"])[::-1].hex() == item[arm]["private_svh"]
    warm = data["warm_private_repeats"].copy()
    assert warm.pop("v3candidate-cold")[crate] == x["standalone_sha256"]
    assert len(warm) == 6 and {row[crate] for row in warm.values()} == {y["standalone_sha256"]}
for row in data["ordinary_bridges"]:
    same = row["bridge"] == row["current_inputs"]
    assert (row["rc"] == 0) == same
    if not same:
        assert row["diagnostic"] == "E0460" and row["crate"] == row["case"]
assert len(data["ordinary_bridges"]) == 8
assert data["native_abi"]["paired"] == data["native_abi"]["compiler_only"]
for k, rows in json.loads((root / "tiny.json").read_bytes()).items():
    if k.startswith("foreign-"):
        assert all(not row["first_library_linkonly"] and not row["keys_with_mismatches"] for row in rows)
    else:
        assert all(row["expected"] == row["observed"] for row in rows)
        body = next(row for row in rows if row["name"] == "body")
        assert body["observed"] == ("relink" if k in {"direct", "transitive"} else "full")
print("All structural counts, hashes, eight ordinary bridge results and tiny controls passed.")

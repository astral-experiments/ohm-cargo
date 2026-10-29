"""Check the release-source verdicts and physical process counts in the retained receipt."""
from hashlib import sha256
import json
from pathlib import Path

raw = (Path(__file__).parent / "receipt.json").read_bytes()
assert sha256(raw).hexdigest() == "bb98e46f1ec3e2232f587cbaecc4430d331b4ebfc432331fd4768b102497e521"
run = json.loads(raw)
assert run["rust_commit"] == "ad005f99d0b51fd62b5c237bc13b31b371a1686e"
assert run["cargo_commit"] == "7277e6cdaba44c43294a07c0661fc8e69fd8e3e7"
assert run["stock_wild_sha256"] == "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
phases = run["phases"]
providers = run["provider"]
cold = run["independently_empty_edited"]
assert len(phases) == 8 and len(providers) == 6 and cold["fresh"] == 0
edited = phases["04-edited"]
before = phases["01-original-cold"]
assert before["elf"] != edited["elf"] == cold["elf"]
assert phases["08-recovery"]["elf"] == edited["elf"]
assert phases["09-restored"]["elf"] == before["elf"]
assert before["fresh"] == cold["fresh"] == 0 and before["typed"] == cold["typed"] == 300
assert run["artifact_comparison"]["all_200_names_identical"]
assert run["artifact_comparison"]["memcmp_bytes"] == edited["elf_bytes"] == cold["elf_bytes"] == 212_524_936
for sample in (edited, cold):
    assert sample["cargo"] == sample["reader_exit"] == 0
    assert sample["listing_sha256"] == run["inventory_sha256"]
    assert sample["tests"] == run["tests"] and len(sample["tests"]) == 3
    assert sample["native"]["e2e_stock_wild"] == 1
invalid = phases["06-invalid"]
assert invalid["cargo"] == 101 and invalid["native"]["e2e_stock_wild"] == 0
assert run["source_fixture"]["invalid_line"] == 22 and "E0308" in json.dumps(invalid)
for expected, prefix in (("valid", "higher"), ("malformed", "malformed")):
    selected = [row for row in providers.values() if row["provider"] == expected]
    assert len(selected) == 2 and {row["forced"] for row in selected} == {False, True}, prefix
    for row in selected:
        assert row["native"]["stock_wild"] == 2 and row["native"]["e2e_stock_wild"] == 1
        if expected == "valid":
            assert row["cargo"] == 0 and row["runtime"] == 83
            assert "native-hook" in row["root_wild_opened"]
        else:
            assert row["cargo"] == 101 and row["malformed_diagnostic"]
            assert "psm-script" in row["root_wild_opened"]
for tag in ("04-remove", "06-final-remove"):
    row = providers[tag]
    assert row["cargo"] == row["runtime"] == 0 and row["elf"] == before["elf"]
print("15 Cargo builds. Warm and clean edited e2e outputs match all 212,524,936 bytes.")
print("Both valid providers exit 83, both malformed inputs fail, and both recoveries restore the original ELF.")

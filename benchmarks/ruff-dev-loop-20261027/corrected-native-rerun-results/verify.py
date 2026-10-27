"""Check the portable Ruff replay against the four outcomes frozen before launch."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re


root = Path(__file__).resolve().parent
results = json.loads((root / "receipts.json").read_bytes())
complete = results["complete"]
driver = "dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"
cargo = "dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1"
expected = {
    "doc-build": (2, 2, 3, 501),
    "doc-test": (4, 16, 19, 619),
    "parser-build": (3, 6, 8, 501),
    "parser-test": (6, 62, 67, 619),
}
assert complete["pin"] == "93526150df078af7dd8fc4226cdcc469539d2001"
assert re.fullmatch(r"[0-9a-f]{64}", complete["index"]) and complete["source_clean"]
assert set(expected) == set(complete["outcomes"]) == set(results["witnesses"])
assert results["code_sha256"] == {
    "SHA256SUMS": "e28aaf7382f56732043183b221980b373c1fb9084ad7e1421f4a614ca0dd398a",
    "replacement.json": "dc003b93377d9ba15b6d80897764a14344c76835501f5b11e94a55e004727d52",
    "rerun-native-edit.py": "3305b50f0384607210650a75e1029e1bdeeedcbcfe982e03cf0f3de80b28813f",
    "run.py": "5d2c22c7c3045c31a2b0fde3ad351c7b44bcc54bc7f1c40e1785cf77dfd07e45",
}
assert complete["reproducer_sha256"] == results["code_sha256"]["rerun-native-edit.py"]
for label, (full, link_only, wild, fresh) in expected.items():
    witness = results["witnesses"][label]
    outcome = complete["outcomes"][label]
    summary = witness["summary"]
    edit, mode = label.split("-")
    command = ["cargo", "+ohm", mode]
    if mode == "test":
        command.append("--no-run")
    command += ["--locked", "--offline"]
    assert outcome["command"] == summary["command"] == command and summary["edit"] == edit
    assert summary["toolchain"] == {"cargo": cargo, "rustc_driver": driver}
    assert outcome["cargo"] == cargo and outcome["driver"] == driver
    assert outcome["source_restored"] and summary["source_restored"]
    assert outcome["fresh_units"] == summary["fresh_units"] == fresh
    assert summary["edit_seconds"] is None
    assert re.fullmatch(r"[0-9a-f]{64}", witness["helper_stdout_sha256"])
    events = witness["execs"]
    for event in events:
        assert re.fullmatch(r"[0-9a-f]{64}", event["sha256"])
        assert re.fullmatch(r"exec\.\d+", event["trace"])
        assert Path(event["image"]).name == event["image"]
    assert any(event["image"] == "cargo" for event in events)
    rustcs = sorted([event["crate"], event["mode"]] for event in events if "crate" in event)
    linkers = sorted(event["image"] for event in events if event.get("wild"))
    assert all(event["image"] == "rustc" for event in events if "crate" in event)
    assert rustcs == outcome["rustcs"] and linkers == outcome["linkers"] == ["ld.bfd"] * wild
    assert Counter(mode for crate, mode in rustcs) == {"full": full, "link-only": link_only}
    print(f"{label}  full={full}  link-only={link_only}  Wild={wild}  fresh={fresh}")

for line in (root / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ", 1)
    assert Path(name).name == name and hashlib.sha256((root / name).read_bytes()).hexdigest() == digest

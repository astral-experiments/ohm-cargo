"""Verify the independent Linux stage-1 compiler controls from the sealed receipts."""
from pathlib import Path
import hashlib
import json
import tarfile

root = Path(__file__).resolve().parent
archive = root / "product-b1-independent-stage1.tar.gz"
digest = lambda b: hashlib.sha256(b).hexdigest()
assert digest(archive.read_bytes()) == "aa1142318a5554fc363134c0ee9a5d3260302dea2e35b0acb298aed99146d842"
with tarfile.open(archive) as packed:
    files = {r.name: packed.extractfile(r).read() for r in packed if r.isfile()}
manifest = json.loads(files.pop("manifest.json"))
assert {f: digest(b) for f,b in files.items()} == manifest and len(files) == 37
def read(case, name="results"):
    return json.loads(files[f"runs/{case}/{name}.json"])
plain, wrapper, warning = "product-b1-ffi", "product-b1-wrapper-mir", "product-b1-warnings"
subject = read(plain, "identity")
assert subject["driver"] == "89858eaea3fea90551c58c4072835576611d8e257961720ca3819cd956de75be"
assert subject["cargo"] == "07c3133de765ceed62a07cdb8baeb5e6ba35c7bd22890ec99d55b7850c73fee7"
for case in (wrapper, warning):
    assert all(read(case, "identity")[k] == subject[k] for k in ("frontend", "driver", "cargo"))
rows = {r["phase"]: r for r in read(plain)}
accepted = ("edit", "restore", "edited-again", "direct-seed")
for phase, value in zip(accepted, (100, 94, 100, 121), strict=True):
    r = rows[phase]
    assert r["value"] == value and r["checked_option"] and r["bundle_rustc"] == 1
    assert r["rlink_identical"] and not r["rlink_writes"] and not r["old_link_option"]
for phase,value in (("local-env",101), ("local-include",106), ("macro-output",110), ("replaced-physical-and-upstream",116)):
    r = rows[phase]
    assert r["value"] == value and r["rlink_writes"] and r["bundle_rustc"] == 1
for k in ("ELF", "rmeta", "value"):
    assert rows["replaced-physical-and-upstream"][k] == rows["independent"][k]
assert not rows["fresh"]["dirty"] and not rows["warm-repeat"]["dirty"]
tamper = read(plain,"physical-negative")
assert tamper["old_sha256"] != tamper["new_sha256"] and tamper["atomic_replace"] and tamper["preserved_mtime_ns"]
archive_check = read(plain,"archive-bytes")
first,second = archive_check["members"]
assert archive_check["all_archive_bytes_equal_after_exact_name_replacement"]
assert first["archive_sha256"] != second["archive_sha256"] and first["native_member"] != second["native_member"]
assert first["name_occurrences"] == second["name_occurrences"] == 2
assert all(first[k] == second[k] for k in ("native_sha256","metadata_sha256"))
for case in ("probe-emit-stable2","rejected-v3-emit"):
    rs = read(case)
    assert rs[0]["MIR"] and rs[-1]["MIR"] and all(r["MIR"] is None for r in rs[2:5])
rs = read(wrapper)
assert rs[-1]["MIR"] and all(x["MIR"] == rs[-1]["MIR"] and x["bundle_rustc"] == 1
                             and not x["checked_option"] for x in rs[2:5])
without_mir,with_mir = read(plain,"direct-compiler-output")
assert without_mir["recipe_identity_preserved"] and without_mir["MIR"] is None
assert not with_mir["recipe_identity_preserved"] and with_mir["MIR"] and with_mir["requested_MIR"]
assert without_mir["returncode"] == with_mir["returncode"] == 0
diags = read(warning,"diagnostics")
assert len(diags) == 6 and len({d["diagnostic_sha256"] for d in diags}) == 1
old = read("new-cargo-rejected-driver")
assert all(not r["checked_option"] and r["rlink_writes"] for r in old[2:5])
print("Verified the four guarded links, compiler and Cargo fallbacks, caller results, clean products and warning output.")

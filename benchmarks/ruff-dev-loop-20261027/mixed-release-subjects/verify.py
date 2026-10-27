"""Verify the frozen release identities, rebuild comparison and independent guard controls."""
import hashlib
import json
from pathlib import Path
import tarfile

here=Path(__file__).resolve().parent
digest=lambda b: hashlib.sha256(b).hexdigest()
read=lambda n: json.loads((here/n).read_bytes())
s=read("subjects.json")
assert digest((here/"rust.patch").read_bytes())==s["rust_diff_sha256"]
assert digest((here/"cargo.patch").read_bytes())==s["cargo_diff_sha256"]
rust=read("rust-release.json")
assert rust["compiler_commit"]==s["rust_head"] and rust["base_commit"]==s["rust_base"]
assert rust["candidate_postbolt"]==s["rust_head_driver"] and rust["frontend"]==s["rustc_frontend"]
assert rust["sources"]=={k:v[1] for k,v in read("rust-overlay.json").items()} and len(rust["sources"])==26
assert len(rust["profiles"])==5 and read("rust-compile.json")["rc"]==read("rust-bolt.json")["rc"]==0
assert read("rust-source.json")["parent"] == s["rust_base"]
cargo=read("cargo-release.json")
assert cargo["commit"]==s["cargo_head"] and cargo["binary_sha256"]==s["cargo_head_binary"]
assert cargo["blobs_and_modes"]==3107 and cargo["stamp"]==["b0a4df740b57589ecec3c83e30d5d326ab52a56d","b0a4df740","2026-10-27"]
assert len(cargo["build_inputs"])==4
proof=read("cargo-control-rebuild.json")["fifo-sealed"]
assert proof["base"]==s["cargo_base_binary"] and proof["symbol_addresses_sizes_types_identical"]
assert proof["differing_sections"]==[".note.gnu.build-id",".strtab"]
assert proof["symbol_count"]==69410 and proof["llvm_private_symbol_names_different"]==852
assert all(v["base_sha256"]==v["rebuilt_sha256"] for k,v in proof["alloc_sections"].items() if k!=".note.gnu.build-id")
assert len(proof["load_segments"])==4
assert all(v["unexpected_differences"]==v["different_section_table_offset_header_bytes"]==0 for v in proof["load_segments"])
assert sum(v["different_build_id_note_bytes"] for v in proof["load_segments"])==32
run=read("rust-run-make.json")
assert run["driver"]==s["rust_head_driver"] and run["source"]==s["rust_head"] and run["test_exit"]==0
w=run["rustc_witnesses"]
assert len(w)==7 and sum(x["bundle"] for x in w)==5 and sum(x["caller"] for x in w)==2
assert sum(x["checked"] for x in w)==3 and sum(x["explicit_mir"] for x in w)==1
host=read("host.json")
assert host["host_tools"]["rustc_frontend"]["sha256"]==s["rustc_frontend"] and host["cargo_jobs"]==8
p=here/"independent-release-controls.tar.gz"
assert digest(p.read_bytes())=="901a19cd0bbdd53f5fbb8456f20f056e42d1db20a5cfcb2a24a9adda957f040e"
with tarfile.open(p) as t:
    payload={x.name:t.extractfile(x).read() for x in t if x.isfile()}
assert json.loads(payload.pop("sha256.json"))=={k:digest(v) for k,v in payload.items()}
case=lambda name,f:json.loads(payload[name+"/"+f+".json"])
fixtures=("ffi","mir","warnings","old-cargo","old-rustc")
for name in fixtures:
    identity=case(name,"identity")
    assert identity["frontend"]==s["rustc_frontend"]
    assert identity["cargo"]==(s["cargo_head_binary"] if name!="old-cargo" else s["cargo_base_binary"])
    assert identity["driver"]==(s["rust_head_driver"] if name!="old-rustc" else s["rust_base_driver"])
rows={name:{r["phase"]:r for r in case(name,"results")} for name in fixtures}
assert sum(map(len,rows.values()))==36
ffi=rows["ffi"]
for k,v in (("edit",100),("restore",94),("edited-again",100),("direct-seed",121)):
    r=ffi[k]; assert r["value"]==v and r["bundle_rustc"]==1 and r["checked_option"] and r["rlink_identical"] and not r["rlink_writes"]
for k,v in (("local-env",101),("local-include",106),("macro-output",110),("replaced-physical-and-upstream",116)):
    r=ffi[k]; assert r["value"]==v and r["bundle_rustc"]==1 and r["rlink_writes"]
assert all(ffi["independent"][k]==ffi["replaced-physical-and-upstream"][k] for k in ("ELF","rmeta","value"))
physical=case("ffi","physical-negative")
assert physical["old_sha256"]!=physical["new_sha256"] and physical["atomic_replace"] and physical["preserved_mtime_ns"]
for name in ("old-cargo","old-rustc","warnings","mir"):
    rs=rows[name]
    assert rs["edited-again"]["ELF"]==rs["clean"]["ELF"] and rs["fresh"]["dirty"]==[]
    assert all(not rs[k]["checked_option"] for k in ("edit","restore","edited-again"))
assert all(r["MIR"]==rows["mir"]["clean"]["MIR"] for r in rows["mir"].values()) and rows["mir"]["clean"]["MIR"]
assert all(r["diagnostics"]==rows["warnings"]["clean"]["diagnostics"] for r in rows["warnings"].values())
assert rows["warnings"]["clean"]["diagnostics"][0]["code"]=="dead_code"
a,b=case("ffi","direct-compiler-output")
assert a["recipe_identity_preserved"] and not a["MIR"] and b["MIR"] and not b["recipe_identity_preserved"]

# Appended to the verifier for the preceding compiler controls.
from pathlib import PurePosixPath
assert digest((here/"runner-binding.json").read_bytes())=="42b1f9068c603ec48d848a1dfb51519f1ba82782db235d396e1bc9bac2d3d064"
assert s["cargo_head"]=="190d261a8546f121e3aa1adf237d85e02164eb18"
proof=read("cargo-test-only-rebuild.json")["bounded-repeat"]
assert proof["binary"]==s["cargo_head_binary"] and proof["symbol_count"]==69473
assert proof["symbol_addresses_sizes_types_identical"] and proof["llvm_private_symbol_names_different"]==1716
assert proof["differing_sections"]==[".note.gnu.build-id",".strtab",".symtab"]
assert all(v["base_sha256"]==v["rebuilt_sha256"] for k,v in proof["alloc_sections"].items() if k!=".note.gnu.build-id")
assert sum(x["unexpected_differences"] for x in proof["load_segments"])==0
assert sum(x["different_build_id_note_bytes"] for x in proof["load_segments"])==31
assert sum(x["different_section_table_offset_header_bytes"] for x in proof["load_segments"])==2
for name in ("deprecation-warn","deprecation-deny"):
    ident=case(name,"identity")
    assert ident["driver"]==s["rust_head_driver"] and ident["cargo"]==s["cargo_head_binary"]
    r=case(name,"upstream-deprecation")
    assert r["original_leaf"]!=r["changed_leaf"] and r["warm"]["diagnostics"]==r["clean"]["diagnostics"]
    assert not r["warm"]["checked_option"] and r["warm"]["bundle_rustc"]==1
    phase=next(x for x in case(name,"results") if x["phase"]=="private")
    assert phase["checked_option"] and phase["rlink_identical"]
    if name=="deprecation-deny":
        assert r["warm"]["returncode"]==r["clean"]["returncode"]==101
    else:
        assert r["warm"]["ELF"]==r["clean"]["ELF"] and r["warm"]["diagnostics"][0]["code"]=="deprecated"
with tarfile.open(here/"cargo-release-controls.tar.gz") as t:
    entries={}
    for m in t:
        assert m.isfile() and m.name not in entries and not PurePosixPath(m.name).is_absolute() and ".." not in PurePosixPath(m.name).parts
        entries[m.name]=t.extractfile(m).read()
manifest=entries.pop("SHA256SUMS")
assert manifest==(here/"independent-cargo-control-manifest").read_bytes()
assert digest(manifest)=="0904cd0554f394819ae53bafdac700efd33c504cb3cbd6aa5a3e4b7d767d7aa0"
assert {name:digest(data) for name,data in entries.items()}=={line[66:]:line[:64] for line in manifest.decode().splitlines()}
assert len(entries)==260
print("Verified the exact final release builds, seven run-make compiler witnesses, 44 compiler-control Cargo commands, two explicit-output checks, 260 Cargo control payloads and the registered worker.")

"""Verify every physical Cargo command, program oracle and type error in the final-pair corpus."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re

root=Path(__file__).resolve().parent
read=lambda f:json.loads((root/f).read_bytes())
sha=lambda data:hashlib.sha256(data).hexdigest()
manifest={n:h for h,n in (row.split("  ",1) for row in (root/"SHA256SUMS").read_text().splitlines())}
assert set(manifest)=={str(f.relative_to(root)) for f in root.rglob("*") if f.is_file() and f.name!="SHA256SUMS"}
assert all(sha((root/n).read_bytes())==h for n,h in manifest.items())
admission=read("admission.json")
assert admission["rust"]=="5e3de497d41f4d4fa98fce3082ea43076779de5d"
assert admission["cargo_source"]=="34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31" and admission["cargo_source"] in admission["cargo_version"]
assert admission["cargo"]=="a9c1b18bbb02f541bcf089db9d4286c215ffc8036fa1ff443e59c9210e77771c"
assert admission["driver"]=="887bf8fc3c90090c1dd5be4af51e8c4a0f319a93db99b454dae35e96c7afde8b"
assert admission["frontend"]=="fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
assert admission["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
assert admission["stdlib_entries"]==53 and admission["euid"]==1000 and admission["root_owner"]==0 and admission["cpus"]==[24,25,26,27]
assert admission["previous_comparison_manifest"]=="dd1e13adc9d983fa65e098b238ca0215191e9643d4d1699cda9879d69614c1b6"
assert sha((root/"typed-dso.py").read_bytes())=="f244a8affb28b11af4b89e4ceefde3cd65a615a28a1f02adb13fec91fde5d728"
histories=read("histories.json")
comparison=read("previous-comparison.json")
exceptions=read("legacy-reader-stops.json")
assert set(exceptions)=={"known-rmeta-current","known-rmeta-preserved"}
expected={f"{training}-{kind}-{stamp}" for training in ("trained","first") for kind in ("tracked-file","include-bytes","include-str") for stamp in ("current","preserved")}
expected|={f"{training}-{kind}-{stamp}" for training in ("known","first","conventional") for kind in ("dso","rmeta") for stamp in ("current","preserved")}
expected|={"typed-dso-current","typed-dso-preserved"}
assert set(histories)==set(comparison)==expected and len(expected)==26
oracles=read("oracles.json")
assert all(sha(v.encode())==k for k,v in oracles["terminal_stdout"].items())
assert all(sha(json.dumps(v,sort_keys=True,separators=(",",":")).encode())==k for k,v in oracles["structured_diagnostics"].items())
seen_stdout=set()
seen_errors=set()
counts=Counter()
for label,h in histories.items():
    assert h["seen_before_swap"]=="17" and h["before"]!=h["after"]
    if h["inode_changed"] is None:
        assert label in exceptions and h["legacy_assertion_rejected"]==exceptions[label]
    else:
        assert h["inode_changed"] and h["mtime_preserved"]==label.endswith("-preserved")
    if "dso_sections" in h:
        assert h["same_rust_source"] and h["mapped_old_native_dso"] and h["before_nbytes"]==h["after_nbytes"]
        assert all((a==b)==(s!=".text") for s,(a,b) in h["dso_sections"].items())
    if "rmeta_roots" in h:
        a,b=h["rmeta_roots"]["old"],h["rmeta_roots"]["new"]
        assert a["stable_id"]==b["stable_id"] and a["svh"]!=b["svh"] and a["public_hash"]!=b["public_hash"]
    phases=h["phases"]
    assert len(phases)==(7 if label.startswith(("known-","trained-","typed-")) else 4)
    assert set(phases)==set(comparison[label])
    checked="rmeta" in label or label.startswith("typed-")
    for phase,p in phases.items():
        counts["commands"]+=1
        assert comparison[label][phase]["matches_previous_verdict"]
        assert p["native"]["cargo"]==p["native"]["target_rustc"]==1
        assert p["raw_traces"] and all(re.fullmatch(r"[0-9a-f]{64}",d) for d in [*p["raw_traces"],p["stdout"],p["stderr"],p["original_row"]])
        assert (p["exit"]==101 and p["fresh"] is None) if p["errors"] else (p["exit"]==0 and p["fresh"] is False)
        for e in p["errors"]:
            seen_errors.add(e["structured_sha256"])
            if e["code"]=="E0308":
                counts["type_errors"]+=1
            else:
                assert "colliding StableCrateId values" in e["message"]
                counts["identity_refusals"]+=1
        if "reopened" in p:
            counts["reopened"]+=1
            actual=p["reopened"]
            assert actual["sample"]==p["value"]==29 and actual["exit"]==0
            seen_stdout.add(actual["stdout"])
    for phase in ("repeat","again","clean"):
        p=phases[phase]
        if checked:
            assert p["exit"]==101 and [e["code"] for e in p["errors"]]==["E0308"] and p["errors"]==phases["clean"]["errors"]
        else:
            assert p["exit"]==0 and p["value"]==29
    first=phases["change" if "change" in phases else "initial"]
    if label.startswith("typed-"):
        assert first["exit"]==0
    elif "rmeta" in label or label.startswith("conventional-"):
        assert first["exit"]==101
    else:
        assert first["exit"]==0 and first["value"]==17
    if not checked:
        assert phases["again"]["reopened"]["stdout"]==phases["clean"]["reopened"]["stdout"]
assert counts=={"commands":140,"type_errors":24,"identity_refusals":8,"reopened":36}
assert seen_stdout==set(oracles["terminal_stdout"]) and seen_errors==set(oracles["structured_diagnostics"])
assert all("sample=29" in v.splitlines() for v in oracles["terminal_stdout"].values())
print("Verified 26 independent histories, 140 real Cargo commands, 36 reopened programs at 29, 24 E0308 diagnostics, eight identity refusals and two retained historical-reader stops.")

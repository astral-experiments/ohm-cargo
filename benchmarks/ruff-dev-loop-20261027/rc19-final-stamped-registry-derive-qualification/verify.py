"""Verify the authentic registry inputs, all twelve original commands and four final executions."""
from pathlib import Path
import hashlib,json,re
root=Path(__file__).resolve().parent
read=lambda n: json.loads((root/n).read_bytes())
sha=lambda f:hashlib.sha256((root/f).read_bytes()).hexdigest()
m={n:h for h,n in (s.split("  ",1) for s in (root/"SHA256SUMS").read_text().splitlines())}
assert set(m)=={str(f.relative_to(root)) for f in root.rglob("*") if f.is_file() and f.name!="SHA256SUMS"} and all(sha(f)==h for f,h in m.items())
source=read("source.json")
assert source["cargo"]=="34dad66fd2ac823bfb02c2c4a4bab02fb5ac4d31" and source["cargo"] in source["release_stamp"]["cargo"]
assert source["rust"]=="5e3de497d41f4d4fa98fce3082ea43076779de5d" and source["rust"] in source["release_stamp"]["rustc"]
assert source["fixture_sha256"]=="be93e1e06fb322ad3edad155f75134f9363b2f839cff968fbc3d2b084892ec27"
assert source["fixture_manifest"]=="1b882f2dfcb3eab730e879c26002382ce5fd7a23241f7c0328fc2c1cb4bceb02"
assert source["prior_wrong_release_manifest"]=="fa167fd553956c038b39613c979119148c48ce9a60db67e7b73a01dedd0e56bd"
histories=read("histories.json")
assert set(histories)=={"first-source-use","known-observer"}
for name,h in histories.items():
    assert h["cargo"]=="a9c1b18bbb02f541bcf089db9d4286c215ffc8036fa1ff443e59c9210e77771c" and h["driver"]=="887bf8fc3c90090c1dd5be4af51e8c4a0f319a93db99b454dae35e96c7afde8b"
    assert h["same_output_path"] and h["no_user_binary_writes_or_timestamp_changes"] and h["old_dso"]!=h["new_dso"]
    assert h["source"]==[sha("fixture/original.rs"),sha("fixture/edited.rs")]
    a,b=h["sections"]
    assert a[".rustc"]==b[".rustc"] and a[".dynsym"]==b[".dynsym"] and a[".text"]!=b[".text"]
    assert set(h["packages"])=={"managed-macro","managed-api","managed-tokens"}
    assert h["packages"]["managed-macro"]["files"]["src/lib.rs"]==sha("fixture/macro.rs")
    assert h["packages"]["managed-macro"]["files"]["build.rs"]==sha("fixture/build.rs")
    rows=h["phases"]
    assert set(rows)=={"seed","seed-repeat","first-edit","next","again","empty"}
    for phase,row in rows.items():
        assert row["rc"]==0 and row["native"]["cargo"]==1
        assert set(row["registry_targets"])=={"managed_api","managed_macro","managed_tokens"}
        assert all(v.startswith("registry+https://github.com/rust-lang/crates.io-index#") for v in row["registry_targets"].values())
        assert all(re.fullmatch("[0-9a-f]{64}",v) for v in row["logs"].values())
        if phase in ("seed","seed-repeat"):
            assert row["stdout"]==("17/17" if name=="known-observer" else "17/0")
        else:
            assert row["calls"]==["29"] and row["stdout"]=="29/29" and row["marker"] and not row["fresh"]["cli"]
            assert row["native"]["rustc"]>=1 and row["native"]["Wild"]>=1
    assert rows["seed"]["calls"]==["17"] and rows["seed"]["marker"]==(name=="known-observer")
    assert rows["seed-repeat"]["fresh"]["cli"]==(name=="first-source-use")
    assert rows["again"]["reopened"]["stdout"]==rows["empty"]["reopened"]["stdout"]=="29/29\n"
print("Verified 12 real Cargo commands, two native registry derives and four independently reopened programs.")

"""Validate this exported historical experiment without a toolchain or network access."""
from pathlib import Path
import gzip, hashlib, json, subprocess

base=Path(__file__).resolve().parent
def get(rel):return json.loads((base/rel).read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
manifest={line.split("  ",1)[1]:line.split("  ",1)[0] for line in (base/"SHA256SUMS").read_text().splitlines()}
assert set(manifest)=={f.relative_to(base).as_posix() for f in base.rglob("*") if f.is_file() and f.name!="SHA256SUMS"}
assert all(sha((base/k).read_bytes())==v for k,v in manifest.items())
sha2=get("image/binary.json")["driver_sha256"]
is_v2=sha2=="b0eb717e74b57f5d4529383e21ddaa504b68411c90c202f5527cf2d0b749fe47"
assert is_v2 or sha2=="36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05"
assert (base/"image/verified.sha").read_text().startswith(sha2)
counts={}; good=0; bad=0
for name in ["source-hash","byte-position","hygiene"]:
    title=Path("mini")/name;summary=get(title/"results.json")
    for kind,row in summary.items():
        warm,cold=[row["builds"][s] for s in ("warm","empty")]
        assert warm["proc_macro_sha256"]==cold["proc_macro_sha256"]
        expected_bad=is_v2 and name=="hygiene" and kind in {"call","mixed"}
        assert (warm["rmeta_sha256"]==cold["rmeta_sha256"])== (not expected_bad)
        vals=set()
        for s in ("warm","empty"):
            q=base/title/kind/s
            assert sha((q/"raw.rmeta").read_bytes())==row["builds"][s]["rmeta_sha256"]
            for t in ("warm","empty"):
                k=s+"/from-"+t; r=row["readers"][k];ch=base/title/kind/(s+"-caller-"+t)
                assert get(ch/"status.json")["returncode"]==r["compiler_status"]
                assert (r["compiler_status"]!=0)==(s!=t and expected_bad)
                if "diagnostics_sha256" in r:assert sha((ch/"stderr").read_bytes())==r["diagnostics_sha256"]
                if r["compiler_status"]:assert b"E0460" in (ch/"stderr").read_bytes();bad+=1
                else:
                    native=ch/"execute/stdout"
                    if not native.is_file():native=next(k for k in ch.glob("*/stdout") if r["runtime"] in k.read_text())
                    assert native.read_text().strip()==r["runtime"]
                    good+=1;vals.add(r["runtime"])
        assert len(vals)==(2 if expected_bad else 1)
    counts[name]=len(summary)*4
assert counts=={"source-hash":12,"byte-position":12,"hygiene":16}
assert (good,bad)==((36,4) if is_v2 else (40,0))
rs=get("ruff/results.json")
assert set(rs)=={"train","fresh","warm","empty"}
for key,d in rs.items():
    pre=Path("ruff/records")/key
    stored=get(pre/"result.json");assert d==stored and d["units"]==501
    cargorows=[json.loads(l) for l in gzip.decompress((base/pre/"cargo.stdout.jsonl.gz").read_bytes()).splitlines()]
    items=[r for r in cargorows if r["reason"]=="compiler-artifact"];assert len(items)==501
    assert [(r["package_id"],r["target"]["name"]) for r in items if not r["fresh"]]==[tuple(p) for p in d["dirty_units"]]
    if key=="fresh": assert all(r["fresh"] for r in items) and not d["dirty_rustc_argv"]
    if key in {"warm","empty"}:
        b=gzip.decompress((base/pre/"parser.rmeta.gz").read_bytes());assert sha(b)==d["rmeta_sha256"]
        assert get(pre/"native-ruff/status.json")["rc"]==1 and json.loads((base/pre/"native-ruff/stdout").read_bytes())[0]["message"]=="Bytes literal cannot be mixed with non-bytes literals"
        assert d["get_size_sha256"]==rs["train"]["get_size_sha256"] and len(d["externs"])==16
        assert sha((base/pre/"native-ruff/stdout").read_bytes())==d["native_ruff_diagnostic_sha256"]
        assert d["parser"]==rs["warm"]["parser"] and d["externs"]==rs["warm"]["externs"]
a,b=rs["warm"],rs["empty"]
assert a["header"]==b["header"]
readers=get("ruff/readers/readers.json")
assert len(readers)==6 and all(r["compiler_exit"]==0 and any(v["mmaps"]>0 and Path(k).name.startswith("libruff_python_parser-") for k,v in r["mapped"].items()) for r in readers)
assert all(r["runtime"]=="Bytes literal cannot be mixed with non-bytes literals at byte range 0..18" and any("libordinary_parser_bridge" in k and v["mmaps"]>0 for k,v in r["mapped"].items()) for r in readers if r["kind"]=="caller")
if is_v2:
    assert a["rmeta_sha256"]=="1ba786237818e41731a77831049e21e4d6fe7651afb0c99873002ab432f4ca24" and b["rmeta_sha256"]=="27f42cea5bf80e4653734b7486497cf248f407f6c01367a79f177617db8ad6e4"
    for n in ("warm","empty"):
        reps=get("ruff/same-history-repeats/results.json")[n];assert all(reps["fields_equal"].values()) and reps["original_raw"]==reps["repeat_raw"]==rs[n]["rmeta_sha256"]
        for part,v in reps["sections"].items():
            assert v["raw_sha256"]==v["section_sha256"]==rs[n]["rmeta_sha256"] and v["stored_raw_offset"]==0 and v["section"]==".rmeta"
            packed=base/"ruff/same-history-repeats"/("archived-"+n+"-"+part)/"archived-lib.rmeta.gz"
            assert sha(gzip.decompress(packed.read_bytes()))==v["shell_sha256"]
    w=get("ruff/wire/classification.json");assert w["all_four_raw_exact"] and w["eligible_for_wire_attribution"]
    delta={n:u-t for n,(t,u) in w["observed_stats_deltas"].items()}
    assert delta=={"def-ids":52,"hygiene":12,"interpret-alloc-index":-72,"mir":49} and sum(delta.values())==41
    for root in sorted((base/"run-makes").glob("*/results.json")):
        rr=get(root);assert {n:r["returncode"] for n,r in rr.items() if r["returncode"]}=={"incremental-proc-macro-source-tracked-final":101}
else:
    assert a["rmeta_sha256"]=="d1b4c6fb68748913bdf85f6af1a2f80efbf3a5c186338c971cbfb8fc421433bd" and b["rmeta_sha256"]=="c1781740da42deabf1adf1b9637332ff69363f08c4c227a1b8324e1e922c87df"
    for n in ("warm","empty"):
        r=get("ruff/same-history-repeats/results.json")[n]
        assert r["repeat_raw"]==r["original_raw"]==rs[n]["rmeta_sha256"] and all(r["fields_equal"].values())
        for which,x in r["sections"].items():
            assert x["raw_sha256"]==x["section_sha256"]==rs[n]["rmeta_sha256"] and x["stored_raw_offset"]==0
            pf=base/"ruff/same-history-repeats"/("archived-"+n+"-"+which)/"archived-lib.rmeta.gz"
            assert sha(gzip.decompress(pf.read_bytes()))==x["shell_sha256"]
    wc=get("ruff/wire/classification.json");assert wc["all_four_raw_exact"] and wc["eligible_for_wire_attribution"]
    assert {k:e-w for k,(w,e) in wc["observed_stats_deltas"].items()}=={"mir":-2,"interpret-alloc-index":-72}
    for k,row in get("no-macro-allocation/results.json").items():
        t="no-macro-allocation/"+k.replace("/","-")+"/"
        for hist in ("train","warm","empty","repeat-empty"):
            assert row[hist]["raw"]==sha((base/t/hist/"raw.rmeta").read_bytes())
            assert b"proc_macro" not in (base/t/hist/"plain.rs").read_bytes()
            if hist!="train":assert row[hist]["native"]=="8"
        assert row["warm"]["raw"]!=row["empty"]["raw"]==row["repeat-empty"]["raw"]
        assert {s:row["empty"]["stats"][s]-v for s,v in row["warm"]["stats"].items() if row["empty"]["stats"].get(s)!=v}=={"interpret-alloc-index":-52}
    checks=[v["returncode"] for f in (base/"run-makes").glob("*/results.json") for v in get(f).values()]
    assert checks==[0]*5
for key,row in get("upgrade/results.json").items():
    assert row["header_hex"]=="52534943"+("0200" if key.startswith(("downgrade","old")) else "0300")
print(f"{len(manifest)} checked files, {good}/40 small callers succeeded, {bad} reproduced E0460, 501/501 fresh, 4/4 real parser cross-history native callers; raw warm/empty same: {a['rmeta_sha256']==b['rmeta_sha256']}")

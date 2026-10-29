from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import re
import subprocess
import sys

p=Path(__file__).resolve().parent
groups={"cli-e8249926456311d5":63,"e2e-f978f73ba5a3a2ed":139,"file_watching-948302c9aaff6c9f":98,"self_environment-86a9154a941e135d":31,"ty-28db247cc67222c0":4,"ty-eb87f4f4ad8029dc":14,"ty_server-4973c777e0baa104":107}
SO={"A":("c07e847c4f0093939d5bff0bfe57269a841c58a281fe2a3e36801ce162b3540c","7a87ca416610a37251a1bb3acab7c6c8d5b01182087bf35730683bfbd06799d3"),"B":("1f85b4040f6ced761026938e7808e130382e4e10da54987b9ff87a83c54917a0","38cacdc302138e022b6ef0f99b26793e7618857fc9eba393d3dbf3e2b6ea41a5")}
blobs={"compiler/rustc_interface/src/util.rs":"edfa7a78afa9ca11ced055c7ed7bcced2067ae1e9d09f5e032b5936748eb2d7d","compiler/rustc_session/src/config.rs":"a206d3fe539fc0da60e16f53690fc3f582105fb7abeb1bf857b5cb528031dba7","compiler/rustc_codegen_ssa/src/back/write.rs":"9f22b8925426c1bc531f9ee547537b7a6142a3af34489648b3c930d844569514"}
def code(rust,cargo):
    def show(repo,sha,path):return subprocess.check_output(["git","-C",repo,"show",sha+":"+path])
    rev="a4fa11bcd38280639cb94daacc125472657db6c3"
    files={q:show(rust,rev,q) for q in blobs}
    assert {q:hashlib.sha256(v).hexdigest() for q,v in files.items()}==blobs
    u=files["compiler/rustc_interface/src/util.rs"]
    assert b"rng().next_u32().to_base_fixed_len(CASE_INSENSITIVE)" in u and b"!sess.opts.unstable_opts.emit_rlink" in u
    cfg=files["compiler/rustc_session/src/config.rs"];assert b"fn temp_path_ext_for_cgu" in cfg and b"extension.push_str(rng);" in cfg
    for commit in ["235f9228651b74c591e6f62cae4c9b761448dd2d","4b0751af97bfa22204a013d0d1f0707382b0df52"]:
        f=show(cargo,commit,"src/compiler/mod.rs");assert hashlib.sha256(f).hexdigest()=="415cbc48618bbda34eace953b6efd03bb2a1db26b455b6f2073e992e4ba8ae5d"
        assert b'executable.with_extension("rlink-objects")' in f
def check(d,z):
    assert d["schema"]==1 and d["control_argv_unchanged_outside_listed_positions"] and set(d["source"])==set(SO)
    for a,(trace,res) in SO.items():
        assert d["source"][a]=={"raw_native_trace_sha256":trace,"original_result_sha256":res}
    assert d["frozen_comparator_sha256"]=="8f114ec372cd419e94a5f7e38f40b4667d69d8d04bd826d9b46bdde1c676d9c0"
    assert Counter(x[0] for x in d["compiler_vectors_equal"])=={"rustc-full":1,"rustc-link-only":50}
    rows=d["normalized_native_vectors"];obj=d["objects"];seen=Counter()
    assert len(rows)==150 and len({(r["target"],r["tool"]) for r in rows})==150
    assert len({r["target"] for r in rows})==50 and Counter(r["tool"] for r in rows)=={"gcc":50,"collect2":50,"stock-wild":50}
    assert d["differing_stable_vectors"]==sum(bool(r["differing"]) for r in rows)==21
    assert len(obj)==456 and [v["index"] for v in obj]==list(range(456))
    assert sum(o["A"]["bytes"] for o in obj)==33492416 and Counter(o["target"] for o in obj)==groups
    for o in obj:
        assert o["A"]==o["B"] and o["A"]["bytes"]>0 and re.fullmatch("[0-9a-f]{64}",o["A"]["sha256"]) and o["both_last_changes_preceded_recorded_execs"]
        first,second=[Path(x) for x in o["paths"]]
        base=first.parent;assert not base.is_absolute() and ".." not in base.parts and base.parts[0]=="target"
        assert base==second.parent and base.name==o["target"]+".rlink-objects"
        assert o["suffixes"][0]!=o["suffixes"][1] and all(re.fullmatch("[a-z0-9]{7}",s) for s in o["suffixes"])
        assert [k.name for k in (first,second)]==[o["filename_stem"]+"."+s+".rcgu.o" for s in o["suffixes"]]
    for r in rows:
        diffs=r["differing"];assert len(diffs)==groups.get(r["target"],0)
        assert (r["normalized_sha256"][0]!=r["normalized_sha256"][1])==bool(diffs)
        assert list(sorted({i for i,_ in diffs}))==[i for i,_ in diffs] and all(0<=i<r["argc"] and obj[ind]["target"]==r["target"] for i,ind in diffs)
        seen.update(ind for _,ind in diffs)
    assert seen==Counter({i:3 for i in range(456)}) and set(z)==set(groups)==set(d["target_summary"])
    for target,n in groups.items():
        used=[o for o in obj if o["target"]==target]
        assert len({tuple(o["suffixes"])for o in used})==1
        siblings=[[ind for _,ind in row["differing"]]for row in rows if row["target"]==target]
        assert siblings[0]==siblings[1]==siblings[2]
        s=d["target_summary"][target];assert s["differing_file_pairs"]==s["byte_identical_file_pairs"]==n
        assert (s["linked_outputs"][0]!=s["linked_outputs"][1])==(target=="e2e-f978f73ba5a3a2ed")
        for a in "AB":
            v=z[target][a]
            for k in ("complete_manifest_object_names","changed_fields_present_in_manifest","changed_absolute_paths_present_in_rlink","changed_basenames_present_in_rlink"):assert v[k]==n
            assert all(re.fullmatch(r"[0-9a-f]{64}",v[k]) for k in ("held_rlink_sha256","cargo_manifest_sha256"))
if __name__=="__main__":
    check(json.loads(gzip.decompress((p/"ledger.json.gz").read_bytes())),json.loads((p/"rlink.json").read_bytes()))
    if len(sys.argv)>1:code(*sys.argv[1:])
    print("150 native vectors, 51 rustc vectors, 456 physical object pairs, 1,368 exact slots and all 14 saved link states/manifests verified.")

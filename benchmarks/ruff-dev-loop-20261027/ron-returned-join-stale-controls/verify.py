"""Offline verification of executed observations, controls and native product identity."""
import hashlib, json, re
from pathlib import Path
base=Path(__file__).resolve().parent
load=lambda n:json.loads((base/"data"/(n+".json")).read_bytes())
def valid(h): return isinstance(h,str) and re.fullmatch(r"[0-9a-f]{64}",h)
known={"observer-233":("0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322","dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"),"corrected-17":("0aa04df8023984b83ef676d1494d43e482472e1b2bccdb82a4d0bd390578a322","618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7"),"official-17":("4e4065390403afbf4fb77b2f41fbc21c59afe3dda2337a5bbe29fda29a47dbb3","618ebac16b7d4ec01a2af89661d25b8f26ff347edbb69c6dcaa78f10115914a7")}
out={}
for name,ident in known.items():
    results=load(name); modes=("keep","drop") if name!="official-17" else ("keep",)
    assert set(results)=={f"{k}-{v}-{b}" for k in ("include","dso") for v in modes for b in ("inc","clean")}
    calls=0
    for key,data in results.items():
        kind,v,b=key.split("-");x=data["rows"];s=data["subjects"]
        assert (s["cargo"],s["driver"])==ident and s["symbol"].endswith("span_join") and len(bytes.fromhex(s["instruction"]))==7
        assert s["source"]=="1237676ca4687d8eb8364eb52b23c5f284f73f4d4113ee833fa3470c8b512be9"
        assert s["rustc"]==("4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f" if name=="observer-233" else "7ec5263869aed2fc9272ea7212aabbe7b272a4685f1b79af75c123daff09c02c")
        assert [a["phase"] for a in x]==(["prime"] if b=="clean" else ["prime","trained-1","trained-2","synchronized","repeat-1","repeat-2"])
        for a in x:
            assert a["readback"]==["bitflags/src/public.rs:17:37-17:38","bitflags/src/public.rs:17:90-17:98","bitflags/src/public.rs:17:37-17:98"]
            assert a["marker"]==(v=="keep") and a["fresh"]==a["cargo_artifact_fresh"]["app"]
            assert valid(a["executable"]) and valid(a["external_image"])
            assert all(h is None or valid(h) for h in a["raw_sha256"].values())
            assert (a["raw_sha256"]["rustc_job_argv"] is not None)==bool(a["true_compilers"])
        assert data["actually_loaded_app_diagnostic"]==sum(a["true_compilers"].count("app") for a in x)+(b=="inc")
        calls+=len(x)
        if b=="clean":
            assert x[0]["program"]=="value=29"
            continue
        sync=x[3]; assert x[0]["program"]==sync["program"]=="value=17" and not sync["fresh"] and sync["true_compilers"]==["app"]
        replaced=sync["replacement"]; before,after=replaced["before"],replaced["after"]
        assert replaced["observed"]=="17" and before["sha"]!=after["sha"]
        assert (before["size"],before["ns"],before["dev"])==(after["size"],after["ns"],after["dev"]) and before["inode"]!=after["inode"]
        good=v=="keep" and name!="official-17"
        for item in x[4:]:
            assert item["program"]==("value=29" if good else "value=17")
            assert item["fresh"]==(not good) and item["true_compilers"]==(["app"] if good else [])
        final=data["forced_same_operand"]; assert final["fresh"]==False and final["actual_rustc_crates"]==["app"] and final["runtime"]==["value=29",*sync["readback"]]
        assert valid(final["captured_dso"]) and final["captured_dso"]==x[-1]["external_image"]
        if kind=="dso":
            assert x[0]["external_image"]==before["sha"] and final["captured_dso"]==after["sha"]
            meta=final["source_data_section"]; assert meta["changed_section"]==[".rodata"] and len(meta["byte_offsets"])==2 and valid(meta["metadata"])
        calls+=1
    out[name]=calls
assert sum(out.values())==80
real=load("ron-native-join"); assert real["hit_counts"]=={"join":3} and len(real["span_registers"])==3
for row in real["span_registers"]:
    a,b=row["r15"],row["r14"]
    assert ((b&0xffffffff)-(a&0xffffffff),(a>>32)&65535,(b>>32)&65535,a>>48,b>>48)==(53,1,8,584,584)
assert real["saved_call_stacks_for_join"]==1 and real["register_pairs_for_join"]==3 and real["backtrace_capture"]=="first hit only at each marked operation"
assert real["native_stack"][-3:]==["serde_derive::ser::serialize_newtype_struct","serde_derive::ser::serialize_body","serde_derive::ser::expand_derive_serialize"]
sat=load("relative");v=sat["bitflags"];assert v["base"]==v["restore"]
assert v["base"]["s"]==v["same_byte_coordinates_new_line"]["s"]==549 and v["base"]["e"]==v["same_byte_coordinates_new_line"]["e"]==602
assert v["base"]["lines"][-1]=="bitflags/src/public.rs:17:37-17:98" and v["same_byte_coordinates_new_line"]["lines"][-1]=="bitflags/src/public.rs:18:36-18:97"
a=sat["preceding_local_source"]; assert a["relative"]["before"]==a["relative"]["after"]==a["relative"]["restore"]
assert a["absolute"]["after"]!=a["absolute"]["before"]==a["absolute"]["restore"]
assert all(z[1]=="different-files" for z in sat["fixture"].values())
layout=load("cargo-layout");assert len(layout)==6 and layout[0]["root_header"][1]!=layout[2]["root_header"][1] and layout[0]["root_header"]==layout[-1]["root_header"]
top=load("topology");assert valid(top["dso_sha256"])
assert top["compiled_values"]=={"original":"alias=true;mapped_alias=true;mapped_name=true;nlink=2","shadow_same_spelling":"alias=false;mapped_alias=false;mapped_name=true;nlink=2","both_shadow_aliases":"alias=true;mapped_alias=true;mapped_name=true;nlink=2","restored":"alias=true;mapped_alias=true;mapped_name=true;nlink=2"}
print(json.dumps({"synchronized_cargo_commands":out,"total_synchronized":sum(out.values()),"bitflags_native_and_read_commands":sat["compile_and_reader_commands"],"source_layout_cargo":len(layout),"mapped_aliases":len(top["compiled_values"]),"ron_join_sites":3},sort_keys=True))

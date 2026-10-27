from pathlib import Path
import hashlib,json,os,sys,shutil
E=Path(__file__).resolve().parent;sys.path.insert(0,str(E.parent/"check-after-native"));sys.path.insert(0,str(E))
import mini
from decode import decode
base=E/"fixture";mini.WS=base;(base/"src").mkdir(parents=True,exist_ok=True)
os.environ["MINI_NATIVE_PROMOTION"]="1"
(base/"Cargo.toml").write_text('[package]\nname="geometry_linter"\nversion="0.0.0"\nedition="2024"\n[workspace]\n[profile.dev]\nopt-level=1\ndebug="line-tables-only"\nlto="off"\n')
shell='#![allow(dead_code)]\nmod helpers;\n'
head='pub(super) fn untouched() -> u32 { 1 }\n/// Prefix dataclasses.field().\n'
variants=[
    ("private-fn","pub fn stable()->u32 { 7 }",'pub(super) fn private_fn() -> u32 { 8 }\n'),
    ("helper-call","pub fn stable()->u32 { helpers::private_fn() }",'#[inline(never)] pub(super) fn private_fn() -> u32 { 8 }\n'),
    ("enum-no-derive","pub fn stable()->u32 { 7 }",'pub(super) enum Hidden { Left, Right }\n'),
    ("debug-enum","pub fn stable()->u32 { 7 }",'#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum Hidden { Left, Right }\n'),
    ("used-debug-enum","pub fn stable()->u32 { helpers::private_fn() }",'#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum Hidden { Left, Right }\n#[inline(never)] pub(super) fn private_fn() -> u32 { if Hidden::Left == Hidden::Right { 1 }else{ 8 } }\n'),
    ("empty-macro-call","pub fn stable()->u32 { 7 }",'macro_rules! unused { () => { fn private_fn() {} } } unused!();\n'),
    ("unrelated-exported-macro","#[macro_export] macro_rules! public_constant { () => { 7u32 }; } pub fn stable()->u32 { 7 }",'#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum Hidden { Left, Right }\n'),
    ("unrelated-exported-opaque","pub fn stable()->impl Iterator<Item=u8> { [7].into_iter() }",'#[derive(Debug, Copy, Clone, PartialEq, Eq)] pub(super) enum Hidden { Left, Right }\n'),
    ("exported-macro-no-derive","#[macro_export] macro_rules! public_constant { () => { 7u32 }; } pub fn stable()->u32 { 7 }",'pub(super) enum Hidden { Left, Right }\n'),
    ("exported-macro-debug-only","#[macro_export] macro_rules! public_constant { () => { 7u32 }; } pub fn stable()->u32 { 7 }",'#[derive(Debug)] pub(super) enum Hidden { Left, Right }\n'),
]
known=json.loads((E/"small-results.json").read_bytes())if (E/"small-results.json").exists()else {}
for tag,api,tail in variants:
    if len(sys.argv)>1 and tag not in sys.argv[1:]:continue
    (base/"src/lib.rs").write_text(shell+api+"\n")
    for arm in ("parent","candidate"):
        rows=[]
        for edited,s in enumerate(("dataclasses","dataclass")):
            (base/"src/helpers.rs").write_text(head.replace("dataclasses",s)+tail)
            # A new target per source state avoids stale incremental work masking any difference.
            st=mini.S/("doc-attr-"+tag+"-"+arm+"-"+str(edited));logs=E/(tag+"-"+arm+"-"+str(edited));logs.mkdir(exist_ok=True)
            p=mini.arm_cmd(arm,st,logs,[mini.SHIM/"cargo","+ohm","build","--offline","--message-format=json"])
            assert p.returncode==0,p.stderr[-750:]
            units=[json.loads(l) for l in p.stdout.splitlines() if l]
            art=next(m for m in units if m["reason"]=="compiler-artifact")
            meta,=[st/Path(f).relative_to(mini.S/"active") for f in art['filenames'] if f.endswith(".rmeta")]
            output=logs/"libgeometry_linter.rmeta";shutil.copy2(meta,output)
            rs=decode(output,"helpers.rs")
            public=next(st.rglob("lib-geometry_linter.public-api-hash"));pk=json.loads(public.read_bytes())["value"]
            rows.append({"public":pk,"global":rs["global"],"retained_in_helper":[[x["name"],x["retained_scc"],x["def"]]for x in rs["focus"] if x["retained_scc"]],"defs":rs["defs"]})
        before,after=rows;changes=[v[1] for k,v in before["defs"].items() if v[0]!=after["defs"].get(k,[None])[0]]
        report={"arm":arm,"case":tag,"hashes":[x["public"]for x in rows],"global_equal":before["global"]==after["global"],"changed_defs":changes,"retained":before["retained_in_helper"]}
        known[arm+"-"+tag]=report;print(tag,arm,report["hashes"][0]==report["hashes"][1],changes,[(x[0],x[2][2:4])for x in report["retained"]][:5],flush=True)
        (E/"small-results.json").write_text(json.dumps(known,indent=2)+"\n")

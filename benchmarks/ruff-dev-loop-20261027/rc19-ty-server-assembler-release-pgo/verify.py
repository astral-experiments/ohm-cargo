"""Independently verify the real Ruff source states, unit roster, native processes and clean verdicts."""
from collections import Counter
from functools import cache
import argparse,ast,gzip,hashlib,json,re,struct,tomllib
from pathlib import Path
D=Path(__file__).resolve().parent
cli=argparse.ArgumentParser()
cli.add_argument("--private-root",type=Path,help="Independently reread the retained native ELF bytes, raw Cargo streams and kernel execs.")
args=cli.parse_args()
def digest(b):return hashlib.sha256(b).hexdigest()
@cache
def disksha(p):
    with p.open("rb") as s:return hashlib.file_digest(s,"sha256").hexdigest()
@cache
def elf_text(path):
    with path.open("rb") as f:
        hdr=f.read(64);assert hdr[:6]==b"\x7fELF\x02\x01"
        base=struct.unpack_from("<Q",hdr,40)[0];nbytes,count,table=struct.unpack_from("<HHH",hdr,58)
        assert nbytes==64
        f.seek(base);rows=[struct.unpack("<IIQQQQIIQQ",f.read(nbytes)) for _ in range(count)]
        f.seek(rows[table][4]);names=f.read(rows[table][5])
        text,=[r for r in rows if names[r[0]:].partition(b"\0")[0]==b".text"]
        f.seek(text[4]);return {"bytes":text[5],"hash":digest(f.read(text[5])),"alloc":bool(text[2]&2),"entry_bytes":text[9]}
def read(s):
    data=(D/s).read_bytes()
    return json.loads(gzip.decompress(data) if s.endswith(".gz") else data)
def key(rows):return Counter((x["name"],tuple(x["kind"])) for x in rows)
def checkhex(s):assert re.fullmatch("[0-9a-f]{64}",s)
def same_generation(r):return sorted((x["package"],x["name"],x["kind"],x["test"],x["features"],x["outputs"]) for x in r["units"])
manifest={}
for raw in (D/"SHA256SUMS").read_text().splitlines():
    s,n=raw.split("  ");assert Path(n).name==n and n not in manifest and digest((D/n).read_bytes())==s;manifest[n]=s
assert set(manifest)=={p.name for p in D.iterdir() if p.is_file()}-{"SHA256SUMS"}
sub=read("subjects.json");assert sub["pin"]=="93526150df078af7dd8fc4226cdcc469539d2001" and sub["historical"]=="a50dc58628691ee00a21809e19bdea71958e4f3c"
assert sub["manifest"]=="40c9ac61b804c1d397e269517b7b4871d6bbea49c179b0fac7fcd26bfcc4c083" and sub["independent_private_inode"]
assert sub["sdk"]=="d6c119ae52f3bf712b9ae612e8726d79c6d2afaf905003732f5708607740c6f6"
assert sub["rustc"]=="fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
assert sub["driver"]=="d8adcc610bdae225344ed1310ff9708784634d1fecafa600f7758a5d48d2cc95"
assert sub["wild"]=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
assert len([s for s in (D/"e2e-list.txt").read_bytes().splitlines() if s.endswith(b": test")])==200
assert manifest["e2e-list.txt"]==sub["listing_sha256"]=="76d24b892727ff181fdf019636ef5e928d741eb8df4f58f06dcc626d0bf67c52"
assert manifest["caller.rs"]=="9c7e1b83172431a3a524bdd15b63a07ae2f1ef98e2a5f30a146626de9597dedf"
assert manifest["ruff-Cargo.lock"]==sub["source_lock"]
locked={x["name"]+"-"+x["version"]+".crate":x["checksum"] for x in tomllib.loads((D/"ruff-Cargo.lock").read_text())["package"] if "checksum" in x}
arch=read("registry-archives.json.gz")
assert len(locked)==arch["archive_count"]==arch["lock_registry_count"]==498 and arch["complete_locked_roster"]
assert {name:r["sha256"] for name,r in arch["archives"].items()}==locked
previous=read("prior.json.gz");old=previous["02-unchanged"]
before=Counter((n,tuple(k)) for n,k,f in old["typed"])
assert sum(before.values())==300 and old["e2e"]["sha256"]==sub["previous_elf"] and old["e2e"]["listing"]==sub["listing_sha256"]
core=read("native-and-verdicts.json.gz");ncommands=0
released = "pgo-final-B" in core
if released:
    assert set(core)=={"pgo-final-B"} and sub["cargo_profile"]=="release PGO"
    pgo=read("final-pgo-build.json"); host=read("final-pgo-physical.json"); lanes=read("final-source-and-lanes.json")
    assert manifest["final-pgo-build.json"]==host["h4_receipt"]=="cdd00d02803a9cc427acbdd2be1401c457f1dd87d84e25863939ff20c938bdda"
    assert pgo["complete_sha256"]==host["h4_complete"]=="04d03548052c93ec14b72562ca404763df245834f3cf8ac16d8c7a8e0cab422c"
    assert manifest["final-source-and-lanes.json"]=="7acdc65156957bfa7fdf37a9bc0bb43ad6abb73b07ad106b8ae756ce25f45cdb"
    assert lanes["binary_expected"]==host["cargo"]==pgo["binary_sha256"]=="ad893345f66ade1c886309b0fc2f98ec5b225d206c176e356531f0e3467eff81"
    assert lanes["final"]==host["cargo_source"]==pgo["commit"]=="a8f0c9aa0412aa259c686416a48aa8d2cf92da72"
    assert lanes["tree"]==host["cargo_tree"]==pgo["tree"]=="3d68b73ad08a7eb8a4e285b3e22626f3abb0a527" and lanes["only_final_change"]=="tests/testsuite/cargo/z_help/stdout.term.svg"
    assert host["bytes"]==pgo["size"]==43342128 and [pgo[k] for k in ("ordered_externs","linker_inputs","rlibs")]==[239,335,326]
    assert pgo["profile_sha256"]=="481ada8a40c70dad11b3c7e8871e9a52207d78447ca5e8ace06fc4aec2d2b5a7"
    assert set(lanes["physical_lanes"])=={"warm","empty-good","empty-bad"}
    assert len({r[k] for r in lanes["physical_lanes"].values() for k in ("target_inode","shared_inode")})==6
    assert all(r["independent_copies"]==498 for r in lanes["physical_lanes"].values())
    assert host["rust_source"]=="ca780121cea38bb9b0538d020d4bcce76ca30cbc" and host["std_count"]==53
    lib_prefix="lib/rustlib/x86_64-unknown-linux-gnu/lib/"
    assert len([k for k in host["sdk"] if k.startswith(lib_prefix)])==53
    assert host["sdk"]["bin/rustc"]["sha256"]==sub["rustc"] and host["sdk"]["lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"]["sha256"]==sub["wild"]
    assert [x["sha256"] for k,x in host["sdk"].items() if k.startswith("lib/librustc_driver-")]==[sub["driver"]]
    cap=read("space-final-pgo.json")
    assert not cap["reserve_breached"] and cap["minimum"]>=host["floor_bytes"]==45*2**30
    assert read("final-private-source-restore.json")["source"]==previous["02-unchanged"]["source"]
    if args.private_root:
        for name,item in host["sdk"].items():
            f=args.private_root/"sdk"/name
            assert f.stat().st_size==item["size"] and disksha(f)==item["sha256"]
for role,data in core.items():
    phases=data["phases"];enrolled=data["enrollment"];finished=data["terminal"]
    drv=read(role+"-native-drivers.json")
    routed=read(role+"-rustup-routing.json")
    assert set(phases)==set(finished["records"])=={p for lane,p,mode in enrolled["roster"]}
    assert enrolled["cargo"]==finished["cargo"]
    if released:assert enrolled["cargo"]==pgo["binary_sha256"] and len(phases)==9
    phasewise={}
    for lane,ph,mode in enrolled["roster"]:
        r=phases[ph];ncommands+=1;assert (r["lane"],r["mode"],r["cargo"],r["rustc"],r["wild"])==(lane,mode,enrolled["cargo"],sub["rustc"],sub["wild"])
        if released:
            assert r["cargo_verbose_version_sha256"]==digest(pgo["version"].encode())
            if args.private_root:
                assert disksha(args.private_root/"reports"/role/ph/"cargo.version")==r["cargo_verbose_version_sha256"]
        ch=routed[ph];assert set(ch)=={"rustup-proxy","selected-cargo"}
        assert ch["rustup-proxy"]["pid"]==ch["selected-cargo"]["pid"]
        assert ch["selected-cargo"]["bound_image_sha256"]==r["cargo"]
        assert ch["rustup-proxy"]["argv"]==["+ohm",*ch["selected-cargo"]["argv"]]
        assert ch["selected-cargo"]["argv"]==["test","--locked","--offline","--no-run","-j4","-p","ty_server","--test","e2e","--message-format=json"]
        if args.private_root:
            raw=args.private_root/"reports"/role/ph
            assert disksha(raw/"qualified.json")==r["raw_receipt"]
            assert disksha(raw/"launches.json")==r["raw"]["execs"]
            assert disksha(raw/"cargo.stdout")==r["raw"]["stdout"] and disksha(raw/"cargo.stderr")==r["raw"]["stderr"]
            transcript=[json.loads(line) for line in (raw/"cargo.stdout").read_bytes().splitlines()]
            artifacts=[j for j in transcript if j.get("reason")=="compiler-artifact"]
            assert [(a["target"]["name"],a["target"]["kind"],a["fresh"]) for a in artifacts]==[(u["name"],u["kind"],u["fresh"]) for u in r["units"]]
            for cmd in r["native"]:
                trace=raw/("exec."+str(cmd["pid"]));assert disksha(trace)==cmd["trace_sha256"]
                line,=[l for l in trace.read_text(errors="replace").splitlines() if digest(l.encode())==cmd["line_sha256"]]
                match=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',line)
                assert match and digest(match[2].encode())==cmd["argv_sha256"]
                exe=Path(ast.literal_eval(match[1]));assert exe.name==cmd["image"] and disksha(exe)==cmd["sha256"]
        assert r["raw_receipt"]==finished["records"][ph] and r["source"]==previous[{"original":"02-unchanged","historical":"03-real-edit","invalid":"05-invalid"}[mode]]["source"]
        for value in r["raw"].values():checkhex(value)
        actual=[c for c in r["native"] if c["role"] in {"full","cached"}];wilds=[c for c in r["native"] if c["role"]=="linker" and c["output"].startswith("e2e-")]
        assert all(c["sha256"]==sub["rustc"] for c in actual) and all(c["sha256"]==sub["wild"] for c in wilds)
        e2e=[c for c in actual if c["crate"]=="e2e"]
        assert len(e2e)==len(wilds)
        underlying=drv[ph]
        assert Counter(x["exe"] for x in underlying)==(Counter({"cc":1,"collect2":1,"ld.bfd":1}) if e2e else Counter())
        if wilds:
            w,=wilds;lp,=[x for x in underlying if x["exe"]=="ld.bfd"]
            assert (w["argv_sha256"],w["line_sha256"])==(lp["argv_sha256"],lp["exec_sha256"])
        for c in r["native"]:
            for k in ("sha256","argv_sha256","trace_sha256","line_sha256"):checkhex(c[k])
        if mode=="invalid":
            assert r["status"]==101 and "product" not in r and not e2e
            assert any(c["role"]=="full" and c["crate"]=="ruff_python_parser" for c in actual)
            assert r["diagnostics"] and all(e["code"]=="E0308" and "mismatched types" in e["message"] and any(s[0].endswith("parser/statement.rs") for s in e["spans"]) for e in r["diagnostics"])
            continue
        assert r["status"]==0 and not r["diagnostics"] and key(r["units"])==before
        p=r["product"];assert p["size"]>100_000_000 and p["fields"][".text"]["alloc"] and p["fields"][".text"]["bytes"]>10_000_000
        for k in ("sha256","parser_rlib","caller_elf"):checkhex(p[k])
        if args.private_root:
            native=args.private_root/"native-objects"/p["sha256"]
            assert native.stat().st_size==p["size"] and disksha(native)==p["sha256"] and elf_text(native)==p["fields"][".text"]
            assert disksha(raw/"caller")==p["caller_elf"]
            assert (raw/"caller-run.stdout").read_text()==r["verdict_stdout"]
            assert disksha(raw/"e2e-list.stdout")==p["inventory"]["stdout"]
        emitted,=[x for x in r["units"] if x["name"]=="e2e" and x["kind"]==["test"]]
        assert p["path_name"] in emitted["outputs"] and (not emitted["fresh"])==bool(e2e)
        assert len(wilds)<=1 and all(c["output"]==p["path_name"] for c in wilds)
        assert p["test_names"]==200 and p["inventory"]["stdout"]==manifest["e2e-list.txt"] and p["inventory"]["status"]==0
        assert set(p["tests"])=={"notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell"}
        assert len(r["selected_names"])==2 and {digest(x.encode()) for x in r["selected_names"]}=={v["stdout"] for v in p["tests"].values()}
        assert all(v["status"]==0 for v in p["tests"].values()) and all("1 passed; 0 failed" in x for x in r["selected_names"])
        assert p["caller"]==("accepted" if mode=="historical" else "rejected: Star import cannot be parenthesized")
        assert p["caller_record"]["stdout"]==digest(r["verdict_stdout"].encode()) and p["caller_record"]["status"]==0 and p["caller"]==r["verdict_stdout"].strip()
        if ph.endswith("repeat"):assert all(x["fresh"] for x in r["units"]) and not actual and not [c for c in r["native"] if c["role"]=="linker"]
        if ph=="03-historical":
            assert len(e2e)==1 and e2e[0]["role"]==("cached" if role.endswith("-A") else "full")
            assert [c["role"] for c in actual if c["crate"]=="ruff_python_parser"]==["full"]
        if "empty" in ph or "cold" in ph:
            assert all(not u["fresh"] for u in r["units"]) and len(e2e)==1 and e2e[0]["role"]=="full"
        phasewise[ph]=r
    def product(k):return phases[k]["product"]
    orig,edit,res=map(product,("01-original-cold","03-historical","06-restore"))
    assert orig["fields"][".text"]["hash"]!=edit["fields"][".text"]["hash"]
    cmp={"restored_elf":orig["sha256"]==res["sha256"],"restored_text":orig["fields"][".text"]==res["fields"][".text"],
         "edited_text_changed":orig["fields"][".text"]!=edit["fields"][".text"]}
    assert all(same_generation(x)==same_generation(y) for x,y in ((phasewise["01-original-cold"],phasewise["02-original-repeat"]),(phasewise["03-historical"],phasewise["04-historical-repeat"]),(phasewise["06-restore"],phasewise["07-restored-repeat"])))
    for k,r in ((orig,"02-original-repeat"),(edit,"04-historical-repeat"),(res,"07-restored-repeat")):assert k["sha256"]==product(r)["sha256"]
    if "08-independent-empty-edited" in phases:
        empty=product("08-independent-empty-edited");cmp.update(empty_edited_elf=edit["sha256"]==empty["sha256"],empty_edited_text=edit["fields"][".text"]==empty["fields"][".text"],
            empty_edited_parser_verdict=edit["caller"]==empty["caller"],empty_edited_inventory=edit["inventory"]==empty["inventory"],empty_invalid_diagnostic=phases["05-invalid"]["diagnostics"]==phases["09-independent-empty-invalid"]["diagnostics"])
        assert cmp["empty_edited_parser_verdict"] and cmp["empty_edited_inventory"] and cmp["empty_invalid_diagnostic"]
    assert finished["comparisons"]==cmp
print(f"Verified {len(core)} Cargo image(s), {ncommands} traced commands, the genuine 300-unit graph, both 200-test inventories, notebook and parser verdicts, and raw ELF comparisons.")

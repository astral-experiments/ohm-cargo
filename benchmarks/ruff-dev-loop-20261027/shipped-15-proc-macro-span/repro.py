"""Exercise a derive's discarded TokenStream parse using ordinary Cargo and an independent full caller."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,shutil,subprocess,sys

def digest(p):
    with Path(p).open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def write(p,v): p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def do(dir,argv,cfg,cwd,prefix=()):
    dir.mkdir()
    write(dir/"argv.json",argv)
    p=subprocess.run([*prefix,*argv],env=cfg,cwd=cwd,capture_output=True)
    (dir/"stdout").write_bytes(p.stdout);(dir/"stderr").write_bytes(p.stderr)
    write(dir/"status.json",{"returncode":p.returncode})
    return p
def format_root(result):
    text=result.stdout.decode()
    patterns = {"private":r"^private hash ([0-9a-f]{32})","public":r"^public_hash ([0-9a-f]{32})","stable":r"stable_crate_id StableCrateId\((\d+)\)"}
    return {name:re.search(pattern,text,re.M).group(1) for name,pattern in patterns.items()}
def run(args):
    out=args.out.resolve();out.mkdir(mode=0o700);docs=out/"evidence";docs.mkdir();ws=out/"workspace";ws.mkdir()
    for package in ["macro_maker","unit"]: (ws/package/"src").mkdir(parents=True)
    (ws/"Cargo.toml").write_text('[workspace]\nmembers=["macro_maker","unit"]\nresolver="3"\n')
    (ws/"Cargo.lock").write_text('version = 4\n\n[[package]]\nname = "macro_maker"\nversion = "0.1.0"\n\n[[package]]\nname = "test_unit"\nversion = "0.1.0"\ndependencies = ["macro_maker"]\n')
    (ws/"macro_maker/Cargo.toml").write_text('[package]\nname="macro_maker"\nversion="0.1.0"\nedition="2024"\n[lib]\nproc-macro=true\n')
    (ws/"unit/Cargo.toml").write_text('[package]\nname="test_unit"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nmacro_maker={path="../macro_maker"}\n')
    producer='#[derive(macro_maker::Marker)]\npub struct Marker;\ninclude!("late.rs");\npub fn value() -> u8 { 7 }\n'
    (ws/"unit/src/late.rs").write_text('pub fn late() -> &'+"'static str"+' { macro_maker::report!(late_token) }\n')
    source=ws/"unit/src/lib.rs";source.write_text(producer)
    (ws/"bridge.rs").write_text('pub fn observed() -> String { format!("{}:{}", test_unit::value(), test_unit::late()) }\n')
    (ws/"main.rs").write_text('fn main() { println!("{}", bridge::observed()); }\n')
    active=out/"active";active.mkdir()
    for n in ["target","shared","cargo-home"]: (active/n).mkdir()
    link=out/"libbridge_input.rlib";link.touch()
    cfg=dict(os.environ,RUSTUP_HOME=str(args.rustup),RUSTUP_AUTO_INSTALL="0",CARGO_HOME=str(active/"cargo-home"),CARGO_TARGET_DIR=str(active/"target"),CARGO_BUILD_BUILD_DIR=str(active/"shared"),CARGO_BUILD_JOBS="4",LC_ALL="C.UTF-8",CARGO_TERM_COLOR="never")
    for k in ("RUSTFLAGS","RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST","CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST"): cfg.pop(k,None)
    assert args.cargo.is_file() and args.driver.is_file()
    write(docs/"tools.json",{"rustc":str(args.sysroot/"bin/rustc"),"frontend_sha256":digest(args.sysroot/"bin/rustc"),"cargo_source":str(args.cargo),"driver_source":str(args.driver),"cargo_sha256":digest(args.cargo),"driver_sha256":digest(args.driver),"logical_rustup":str(args.rustup),"sysroot":str(args.sysroot),"cpu_affinity":sorted(os.sched_getaffinity(0))})
    def nspace(st,bridge=None):
        ns=["bwrap","--ro-bind","/","/","--dev-bind","/dev","/dev","--proc","/proc","--bind",str(out),str(out),
            "--ro-bind",str(args.cargo),str(args.sysroot/"bin/cargo"),"--ro-bind",str(args.driver),str(args.sysroot/"lib"/args.driver_soname)]
        for n in ["target","shared","cargo-home"]: ns+=["--bind",str(st/n),str(active/n)]
        if bridge: ns+=["--ro-bind",str(bridge),str(link)]
        return [*ns,"--"]
    def check(z):assert z.returncode==0,(z.args,z.stderr.decode()[-1600:]);return z
    def build(dir,st,mode):
        argv=["cargo","+ohm",*(["-Zohm-defaults=no"] if mode=="legacy" else []),"build","-p","test_unit","--locked","--offline","--message-format=json"]
        z = check(do(dir,argv,cfg,ws,nspace(st)))
        units=[x for l in z.stdout.splitlines() if (x:=json.loads(l))["reason"]=="compiler-artifact"]
        u,=[x for x in units if x["target"]["name"]=="test_unit"]
        m,=[x for x in units if x["target"]["name"]=="macro_maker"]
        assert not u["fresh"]
        rlib,=[Path(p) for p in u["filenames"] if p.endswith(".rlib")]
        mds=[Path(p) for p in u["filenames"] if p.endswith(".rmeta")]
        if mds:md,=mds
        else:
            rpath=st/"target"/rlib.relative_to(active/"target")
            found=[p for n in ["target","shared"] for p in (st/n).rglob("libtest_unit-*.rmeta")]
            assert len(found)==1,found
            md=active/found[0].relative_to(st)
        so,=[Path(p) for p in m["filenames"] if p.endswith(".so")]
        def physical(q):return st/q.relative_to(active)
        header=check(do(dir/"header",["rustc","+ohm","-Zls=root",str(md)],cfg,ws,nspace(st)))
        h=format_root(header)
        row=dict(header=h,rlib=str(rlib),rlib_sha256=digest(physical(rlib)),rmeta=str(md),rmeta_sha256=digest(physical(md)),proc_macro=str(so),proc_macro_sha256=digest(physical(so)),unit_fresh={x["target"]["name"]:x["fresh"] for x in units})
        shutil.copyfile(physical(md),dir/"raw.rmeta")
        write(dir/"result.json",row);return row
    groups={}
    for variant in ["parse","programmatic","legacy"]:
        prefix=docs/variant;prefix.mkdir()
        state_root=out/("states-"+variant);state_root.mkdir()
        proc='extern crate proc_macro;\nuse proc_macro::{TokenStream, Literal};\n#[proc_macro_derive(Marker)]\npub fn marker(_: TokenStream) -> TokenStream {\n'+('    let _: TokenStream = "0".parse().unwrap();\n' if variant!="programmatic" else '    let _ = Literal::u8_unsuffixed(0);\n')+'    TokenStream::new()\n}\n'
        # Keep source warnings out of both arms.
        proc+=r'''#[proc_macro]
pub fn report(t: TokenStream) -> TokenStream {
    let span = t.into_iter().next().unwrap().span();
    let text = format!("{:?}", span);
    TokenStream::from(proc_macro::TokenTree::Literal(Literal::string(&text)))
}
'''
        proc=proc.replace('use proc_macro::{TokenStream, Literal};','use proc_macro::TokenStream;').replace('Literal::','proc_macro::Literal::')
        (ws/"macro_maker/src/lib.rs").write_text(proc);source.write_text(producer)
        (prefix/"maker.rs").write_text(proc);(prefix/"unit-before.rs").write_text(producer)
        states={}
        for state in ["shared-original","warm","empty"]:
            st=state_root/state
            if state=="shared-original":
                st.mkdir();[(st/q).mkdir() for q in ["target","shared","cargo-home"]]
            else:shutil.copytree(states["shared-original"],st,symlinks=True)
            states[state]=st
        base=states["shared-original"];train=build(prefix/"training",base,variant)
        # The warm and empty workdirs above are still unused. Both now receive the
        # identical genuine original Cargo state, without any cross-state hard links.
        for tag in ["warm","empty"]:
            for q in ["target","shared","cargo-home"]:shutil.copytree(base/q,states[tag]/q,symlinks=True,dirs_exist_ok=True)
        dirs=[d for q in ["target","shared"] for d in (states["empty"]/q).rglob("test_unit-*") if d.is_dir() and any(d.glob("s-*-*-*/dep-graph.bin"))]
        assert len(dirs)==1,dirs
        dirs[0].rename(state_root/"disabled-unit-session")
        edited=producer.replace("{ 7 }","{ 8 }");source.write_text(edited);(prefix/"unit-after.rs").write_text(edited)
        data={s:build(prefix/s,states[s],variant) for s in ["warm","empty"]}
        assert data["warm"]["proc_macro_sha256"]==data["empty"]["proc_macro_sha256"]==train["proc_macro_sha256"]
        bridge={}
        for s,row in data.items():
            d=prefix/("bridge-"+s)
            target=d/"libbridge.rlib"
            argv=["rustc","+ohm","--edition=2024","--crate-name","bridge","--crate-type","rlib",str(ws/"bridge.rs"),"--extern","test_unit="+row["rlib"],"-L","dependency="+str(Path(row["rmeta"]).parent),"-L","dependency="+str(Path(row["proc_macro"]).parent),"-o",str(target)]
            check(do(d,argv,cfg,ws,nspace(states[s])));bridge[s]=target
        rr={}
        for s,row in data.items():
            for t in data:
                d=prefix/(s+"-caller-"+t)
                argv=["rustc","+ohm","--edition=2024","--crate-name","app",str(ws/"main.rs"),"--extern","bridge="+str(link),"-L","dependency="+str(Path(row["rmeta"]).parent),"-L","dependency="+str(Path(row["proc_macro"]).parent),"-o",str(d/"app")]
                z=do(d,argv,cfg,ws,nspace(states[s],bridge[t]));value=None
                if not z.returncode:
                    q=check(do(d/"native",[str(d/"app")],cfg,ws,nspace(states[s])))
                    value=q.stdout.decode().strip();assert value.startswith("8:#")
                elif not (z.returncode==1 and b'error[E0460]' in z.stderr and b'crate `test_unit` which `bridge` depends on' in z.stderr):raise ValueError(z.stderr.decode())
                same=data[s]["header"]["private"]==data[t]["header"]["private"]
                assert not args.report_old_semantics or (z.returncode==0 or not same)
                if not args.report_old_semantics: assert (z.returncode==0)==same
                rr[s+"/from-"+t]={"compiler_status":z.returncode,"runtime":value,"bridge_sha256":digest(bridge[t]),"diagnostics_sha256":digest(d/"stderr")}
        groups[variant]={"builds":data,"readers":rr}
        write(docs/"results.json",groups)
        print(variant,[[s,r["header"]["private"],r["header"]["public"]] for s,r in data.items()],rr,flush=True)
    write(docs/"complete.json",{"timings":0,"commands":"nine Cargo builds, six ordinary bridges and twelve ordinary callers","results_sha256":digest(docs/"results.json")})
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--report-old-semantics",action="store_true");p.add_argument("--out",type=Path,required=True);p.add_argument("--rustup",type=Path,required=True);p.add_argument("--sysroot",type=Path,required=True);p.add_argument("--cargo",type=Path,required=True);p.add_argument("--driver",type=Path,required=True);p.add_argument("--driver-soname",default="librustc_driver-774a793a844d5500.so");run(p.parse_args())

"""Native qualification of targeted library tests that can defer a pure Rust dev dependency."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys

q = Path(__file__).resolve().parent
r = q / sys.argv[1]
r.mkdir()
sdk = Path(sys.argv[2]).resolve()
out = r / "project"
proxy = Path.home() / ".cargo/bin/cargo"
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f, "sha256").hexdigest()
def write(name, s):
    p=out/name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s)
def package(name):
    return f'[package]\nname="{name}"\nversion="1.0.0"\nedition="2024"\n'
write("Cargo.toml", '[workspace]\nmembers=["app","retained","unused"]\nresolver="3"\n')
write("retained/Cargo.toml",package("retained"))
write("retained/src/lib.rs","pub fn marker() {}\n")
write("retained/base.c","int choice(void) { return 17; }\n")
write("retained/build.rs",'''use std::{path::PathBuf, process::Command};
fn main() {
    let out = PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
    assert!(Command::new("cc").args(["-c", "base.c", "-o"]).arg(out.join("base.o")).status().unwrap().success());
    assert!(Command::new("ar").arg("crs").arg(out.join("libchoice.a")).arg(out.join("base.o")).status().unwrap().success());
    println!("cargo:rerun-if-changed=base.c");
    println!("cargo:rustc-link-search=native={}", out.display());
}
''')
write("app/Cargo.toml",package("app")+'[dependencies]\nretained={path="../retained"}\n[dev-dependencies]\nunused={path="../unused"}\n')
write("unused/Cargo.toml",package("unused"))
write("unused/src/lib.rs","pub fn unused() {}\n")
(r/"rustup/toolchains").mkdir(parents=True)
(r/"rustup/toolchains/ohm").symlink_to(sdk, target_is_directory=True)
env=dict(HOME=str(r/"home"),CARGO_HOME=str(r/"home/.cargo"),RUSTUP_HOME=str(r/"rustup"),RUSTUP_TOOLCHAIN="ohm",RUSTUP_AUTO_INSTALL="0",CARGO_TARGET_DIR=str(r/"target"),CARGO_BUILD_BUILD_DIR=str(r/"shared"),CARGO_NET_OFFLINE="true",LANG="C.UTF-8",TERM="dumb",PATH=f"{sdk}/bin:{proxy.parent}:/usr/bin:/bin",CARGO_LOG="cargo::compiler::ohm_deferred_dev_deps=info")
def exercise(name, literal):
    write("app/src/lib.rs",f'''
        pub fn selected_body() -> u32 {{ retained::marker(); {literal} }}
        #[link(name="choice", kind="static")]
        unsafe extern "C" {{ fn choice() -> i32; }}
        #[test] fn selected() {{ println!("native-choice={{}}", unsafe {{ choice() }}); }}
    ''')
    d=r/name;d.mkdir()
    cmd=[proxy,"+ohm","test","--offline","-p","app","--lib","--no-run","--message-format=json"]
    with (d/"stdout").open("wb") as stdout,(d/"stderr").open("wb") as stderr:
        c=subprocess.run(["strace","-f","-qq","-s","16000","-e","trace=execve","-o",d/"exec.log",*cmd],cwd=out,env=env,stdout=stdout,stderr=stderr,timeout=75)
    j=[json.loads(line) for line in (d/"stdout").read_bytes().splitlines() if line.startswith(b"{")]
    lines=[s for s in (d/"exec.log").read_text().splitlines() if "execve(" in s and re.search(r'\)\s+= 0$',s)]
    stderr=(d/"stderr").read_text()
    ret=dict(cargo_exit=c.returncode,stage=name,stderr_sha=sha(d/"stderr"),json_sha=sha(d/"stdout"),exec_sha=sha(d/"exec.log"),
             rustcs=[m[1] for s in lines if 'rustc"' in s and (m:=re.search(r'"--crate-name", "([^"]+)"',s))],
             wild=sum("wild-ld/ld.bfd" in re.search(r'execve\("([^"]+)"',s)[1] for s in lines),
             deferred=[s[s.index("ohm_deferred_dev_deps:")+len("ohm_deferred_dev_deps:"):].strip() for s in stderr.splitlines() if "ohm_deferred_dev_deps:" in s])
    if c.returncode==0:
        harness,=[Path(x["executable"]) for x in j if x.get("reason")=="compiler-artifact" and x.get("executable") and x["target"]["name"]=="app"]
        b=subprocess.run([harness,"selected","--exact","--nocapture"],capture_output=True,env=env,timeout=20)
        (d/"native.stdout").write_bytes(b.stdout);(d/"native.stderr").write_bytes(b.stderr)
        val=re.search(rb'native-choice=(\d+)',b.stdout)
        ret.update(native_exit=b.returncode,value=int(val[1]) if val else None,elf=sha(harness))
    else: ret["link_error"]=any("linking with" in x.get("message",{}).get("message","") for x in j if x["reason"]=="compiler-message")
    (d/"result.json").write_text(json.dumps(ret,indent=2)+"\n");print(ret,flush=True)
    return ret,j
rows=[]
row,j=exercise("01-seed",1);rows.append(row)
assert row.get("value")==17,row
dir_,=[Path(x["out_dir"]) for x in j if x.get("reason")=="build-script-executed" and "retained" in x["package_id"]]
proofs=[]
for p in (r/"target").rglob("app-*.rlink-cache.json"):
    doc=json.loads(p.read_bytes());proofs.append(dict(sha=sha(p),names=doc.get("unused_extern_names")))
rows.append(exercise("02-edited-no-shadow",2)[0])
# Replace the valid archive outside Cargo; preserve its name and every emitted directive.
(r/"base.c").write_text("int choice(void) { return 29; }\n")
subprocess.run(["cc","-c","base.c","-o","base.o"],cwd=r,check=True)
subprocess.run(["ar","crs","libchoice.a","base.o"],cwd=r,check=True)
(dir_/"libchoice.a").write_bytes((r/"libchoice.a").read_bytes())
rows.append(exercise("03-supported-archive",3)[0])
# This extra .so is a stock link-name lookup in the actual retained OUT_DIR.
hook=r/"hook.S";hook.write_text('.text\n.type stop_83,@function\nstop_83:\nmov $231,%eax\nmov $83,%edi\nsyscall\nud2\n.section .preinit_array,"aw",@preinit_array\n.quad stop_83\n.section .note.GNU-stack,"",@progbits\n')
subprocess.run(["as","--64",hook,"-o",r/"hook.o"],check=True)
ordinary=Path(subprocess.check_output(["gcc","-print-file-name=libgcc_s.so"],text=True).strip()).resolve(strict=True)
shadow=dir_/"libgcc_s.so";assert not shadow.exists()
shadow.write_text(f'INPUT ( {r/"hook.o"} {ordinary} )\n')
rows.append(exercise("04-valid-shadow",4)[0])
shadow.unlink()
rows.append(exercise("04a-retrain",40)[0])
shadow.write_text("OHM_REJECT_UNRELATED_NATIVE_PROVIDER (\n")
rows.append(exercise("05-malformed-shadow",5)[0])
shadow.unlink()
rows.append(exercise("06-restored",6)[0])
(r/"terminal.json").write_text(json.dumps(dict(cargo=sha(sdk/"bin/cargo"),rustc=sha(sdk/"bin/rustc"),script=sha(Path(__file__)),source=sha(out/"retained/build.rs"),proofs=proofs,rows=rows),indent=2)+"\n")
assert [x["cargo_exit"] for x in rows]==[0,0,0,0,0,101,0]
assert [x.get("native_exit") for x in rows]==[0,0,0,83,0,None,0] and rows[2]["value"]==rows[6]["value"]==29
assert all(x["wild"]>=1 for x in rows) and rows[5]["link_error"]
assert any("accepted current unused-dependency proof" in line for x in rows[1:3] for line in x["deferred"])
assert all(any("retrying complete graph" in line for line in x["deferred"]) for x in [rows[3],rows[5]])

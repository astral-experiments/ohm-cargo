from pathlib import Path
import os, stat, hashlib, json, re, shutil, subprocess, sys

base=Path(__file__).resolve().parent
sdk=base/"sdk"
seed=base/"seed-state"
live=base/"live"
source=live/"src"
rustup=base/"rustup"
stock=Path.home()/".cache/ohm-script-hash-wall-rc19-v1/current/sdk"
cargo_image=Path.home()/".cache/ohm-rlib-origin-product-20261029/cargo-A"
proxy=Path.home()/".cargo/bin/cargo"
digest=lambda b:hashlib.sha256(b).hexdigest()
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def write(p,value):
    p.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def state(p):
    st=p.stat()
    return {"path":str(p),"sha256":sha(p),"mtime_ns":st.st_mtime_ns,"device":st.st_dev,"inode":st.st_ino,"links":st.st_nlink,"bytes":st.st_size}
def fresh():
    assert not live.exists()
    subprocess.run(["cp","-a","--reflink=auto",seed,live],check=True)
def put(name,contents):
    p=source/name
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(contents)
env=dict(PATH=str(proxy.parent)+":/usr/local/bin:/usr/bin:/bin",HOME=str(Path.home()),RUSTUP_HOME=str(rustup),RUSTUP_TOOLCHAIN="ohm",RUSTUP_AUTO_INSTALL="0",CARGO_HOME=str(live/"registry"),CARGO_TARGET_DIR=str(live/"target"),CARGO_BUILD_BUILD_DIR=str(live/"shared"),CARGO_NET_OFFLINE="true",LANG="C",LC_ALL="C",TMPDIR=str(live/"tmp"))
provider="pub fn value() -> u8 { 17 }\n"
reader="pub fn from_index() -> u8 { provider::value() }\n"
args=[str(proxy),"+ohm","check","--workspace","--locked","--offline","-j4","--message-format=json"]
def relevant():
    result={}
    for n in ("provider","reader"):
        p=[p for p in (live/"shared").rglob("lib"+n+"-*.rmeta") if "incremental" not in p.parts]
        if not p:
            p=[p for p in (live/"target").rglob("lib"+n+"-*.rmeta") if "incremental" not in p.parts]
        assert len(p)<=1,(n,p)
        if p:result[n]=state(p[0])
    return result
def run(label,kind="none",trace=False):
    folder=base/"receipts"/label;folder.mkdir()
    e={**env,"CARGO_LOG":"cargo::compiler::fingerprint=debug,cargo_util::paths=debug"}
    if kind!="none":
        e.update(LD_PRELOAD=str(base/"order.so"),WITNESS_EVENTS=str(folder),WITNESS_ORDER=kind,WITNESS_ORIGINAL_CARGO=str(cargo_image))
    before=relevant()
    cmd=args
    if trace:
        cmd=["strace","-qq","-f","-ttt","-s","65535","-e","trace=execve,utimensat,rename,link,linkat,unlink","-o",str(folder/"native.trace"),*args]
    p=subprocess.run(cmd,cwd=source,env=e,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
    (folder/"cargo.stdout").write_bytes(p.stdout);(folder/"cargo.stderr").write_bytes(p.stderr)
    rows=[json.loads(l) for l in p.stdout.splitlines()]
    diagnostics=[[r["target"]["name"],r["message"]["code"],r["message"]["message"]] for r in rows if r["reason"]=="compiler-message"]
    arts=[[r["target"]["name"],r["fresh"]] for r in rows if r["reason"]=="compiler-artifact"]
    obs=relevant()
    actual=[]
    if trace:
        for line in (folder/"native.trace").read_text().splitlines():
            if "execve(" in line and '"--crate-name", ' in line and re.search(r'= 0$',line):
                m=re.search(r'"--crate-name", "([^"]+)"',line)
                if m: actual.append({"crate":m[1],"successful_exec":line.split(" execve(",1)[-1]})
    reasons=[l[l.find("stale:"):][:1400] for l in p.stderr.decode().splitlines() if "stale:" in l]
    order=(folder/"control.tsv").read_text().splitlines() if (folder/"control.tsv").exists() else []
    rec={"argv":args,"status":p.returncode,"compiler_artifacts":arts,"diagnostics":diagnostics,"before":before,"after":obs,"order":order,"actual":actual,"trace":trace,"source_digests":{n:sha(source/n) for n in ["provider/src/lib.rs","reader/src/lib.rs","provider/flag","provider/build.rs"]},"stale":reasons}
    write(folder/"result.json",rec)
    print(label,p.returncode,arts,"ns gap",obs["provider"]["mtime_ns"]-obs["reader"]["mtime_ns"] if len(obs)==2 else None,[(l.split("\t")[0],l.split("\t")[3:5]) for l in order],flush=True)
    return rec
def main():
    assert os.getuid()==1000 and Path("/").stat().st_uid==0 and not live.exists()
    (base/"receipts").mkdir()
    (sdk/"bin").mkdir(parents=True)
    for p in stock.iterdir():
        if p.name!="bin":(sdk/p.name).symlink_to(p)
    for p in (stock/"bin").iterdir():
        (sdk/"bin"/p.name).symlink_to(cargo_image if p.name=="cargo" else p)
    (rustup/"toolchains").mkdir(parents=True);(rustup/"toolchains/ohm").symlink_to(sdk)
    source.mkdir(parents=True);(live/"tmp").mkdir()
    tools={str(p):sha(p) for p in [cargo_image,stock/"bin/rustc",stock/"lib/librustc_driver-b03bf00bec23bb9a.so",proxy.resolve()]}
    assert tools[str(cargo_image)]=="6aaa263e68d2d77aeb8977166f9744f1fa8e0ea4df3216fe516355be68517bac"
    assert tools[str(stock/"bin/rustc")]=="c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
    assert tools[str(stock/"lib/librustc_driver-b03bf00bec23bb9a.so")]=="a7648053cbad025c1bb0bebb7009ce9e1515bdb02e8c30bef29b52a881e5b8de"
    vers={cmd:subprocess.check_output([str(proxy.parent/cmd),"+ohm","-vV"],env=env,text=True) for cmd in ("cargo","rustc")}
    write(base/"identity.json",{"tools":tools,"versions":vers,"source_cargo":"235f9228651b74c591e6f62cae4c9b761448dd2d","source_rust":"a4fa11bcd38280639cb94daacc125472657db6c3","host":"x86_64-unknown-linux-gnu","uid":os.getuid(),"uid_map":Path("/proc/self/uid_map").read_text(),"sdk":str(sdk),"fresh_cargo_home":str(live/"registry")})
    put("Cargo.toml",'[workspace]\nresolver="3"\nmembers=["provider","reader"]\n')
    put("provider/Cargo.toml",'[package]\nname="provider"\nversion="0.1.0"\nedition="2024"\n')
    put("provider/src/lib.rs",provider)
    put("provider/flag","original\n")
    put("provider/build.rs",'fn main() { println!("cargo::rerun-if-changed=flag"); let f = std::fs::read_to_string("flag").unwrap(); println!("cargo::rustc-env=FORCE_PROVIDER={}", f.trim()); }\n')
    put("reader/Cargo.toml",'[package]\nname="reader"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nprovider={path="../provider"}\n')
    put("reader/src/lib.rs",reader)
    subprocess.run([str(proxy),"+ohm","generate-lockfile","--offline"],cwd=source,env=env,check=True,timeout=30)
    assert run("original",trace=True)["status"]==0
    assert run("original-immediate-repeat",trace=True)["status"]==0
    live.rename(seed)
    for label,order,trace in [("normal-untraced","none",False),("normal-traced","none",True),("provider-late","provider-late",True),("provider-first","provider-first",True)]:
        fresh();put("provider/flag","modified\n");put("reader/src/lib.rs",reader+"// independent source edit\n")
        assert run(label,order,trace)["status"]==0
        assert run(label+"-first-repeat",trace=True)["status"]==0
        assert run(label+"-second-repeat",trace=True)["status"]==0
        live.rename(base/("state-"+label))
    fresh();put("provider/src/lib.rs","pub fn value() -> bool { true }\n")
    assert run("api-incompatible-warm",trace=True)["status"]==101
    for n in ["target","shared"]:(live/n).rename(live/(n+"-preserved"))
    assert run("api-incompatible-empty",trace=True)["status"]==101
    live.rename(base/"state-api");fresh()
    r=relevant();Path(r["reader"]["path"]).unlink()
    assert run("missing-existing-output",trace=True)["status"]==0
    live.rename(base/"state-missing")
    print("all commands finished",flush=True)
if __name__=="__main__":main()

"""Compare first-upgrade native jobs with the historical Cargo's actual cached targets."""
from pathlib import Path
import ast, hashlib, json, os, re, shutil, subprocess, sys

phase = sys.argv[1]
assert phase in ("train","upgrade")
root,old,new,donor=map(Path,sys.argv[2:6])
old_sha,new_sha=sys.argv[6:8]
def sha(f):
    with f.open("rb") as inp:return hashlib.file_digest(inp,"sha256").hexdigest()
def put(p,v):
    with p.open("x") as out:json.dump(v,out,indent=2,sort_keys=True);out.write("\n")
assert sha(old)==old_sha and (phase=="train" or (sha(new)==new_sha and old_sha!=new_sha))
assert os.getuid()==1000 and Path("/").stat().st_uid==0 and set(os.sched_getaffinity(0))<={8,9,10,11}
src=root/"work";sdk=root/"sdk";rh=root/"rustup"
if phase=="train":
    root.mkdir(mode=0o700)
    for f in (src,sdk/"bin",rh/"toolchains",root/"home",root/"cargo-home"):f.mkdir(parents=True)
    for f in donor.iterdir():
        if f.name!="bin":(sdk/f.name).symlink_to(f,target_is_directory=f.is_dir())
    for f in (donor/"bin").iterdir():
        if f.name!="cargo":(sdk/"bin"/f.name).symlink_to(f)
    (rh/"toolchains/ohm").symlink_to(sdk,target_is_directory=True)
    def write(p,s):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(s)
    write(src/"Cargo.toml",'[workspace]\nmembers=["with_lib","only_bin"]\nresolver="3"\n')
    for name in ("with_lib","only_bin"):
        p=src/name
        write(p/"Cargo.toml",f'[package]\nname="{name}"\nversion="0.0.0"\nedition="2024"\n')
        write(p/"src/main.rs",'fn main(){println!("42");}\n')
        write(p/f"tests/{name}_it.rs",'#[test] fn ready(){assert_eq!(7*6,42);}\n')
        write(p/f"examples/{name}_ex.rs",'fn main(){println!("42");}\n')
        write(p/f"benches/{name}_bench.rs",'#[test] fn ready(){assert_eq!(7*6,42);}\n')
        if name=="with_lib":write(p/"src/lib.rs",'pub fn answer()->u8{42}\n')
    write(src/"Cargo.lock",'version=4\n\n[[package]]\nname="only_bin"\nversion="0.0.0"\n\n[[package]]\nname="with_lib"\nversion="0.0.0"\n')
env={"PATH":str(Path(shutil.which("rustup")).parent)+":/usr/bin:/bin","HOME":str(root/"home"),
     "CARGO_HOME":str(root/"cargo-home"),"RUSTUP_HOME":str(rh),"RUSTUP_AUTO_INSTALL":"0",
     "CARGO_INCREMENTAL":"0","CARGO_NET_OFFLINE":"true","LC_ALL":"C","LANG":"C"}
live=sdk/"bin/cargo"
def switch(binary,sha256):
    staged=live.with_name("staged");shutil.copyfile(binary,staged);staged.chmod(0o755)
    assert sha(staged)==sha256;os.replace(staged,live)
    return subprocess.check_output(["cargo","+ohm","-Vv"],env=env,cwd=src)
reports={}
def run(arm,mode,number):
    out=root/f"{arm}-{mode}-{number}";out.mkdir()
    lane=root/("state-"+mode)
    args={"check":["check","--all-targets"],"lib":["build","-p","with_lib","--lib"],
          "native":["test","--no-run","--all-targets"]}[mode]
    command=["cargo","+ohm",*args,*(["--workspace"] if mode!="lib" else []),
             "--offline","--locked","-j2","--message-format=json"]
    e=env|{"CARGO_TARGET_DIR":str(lane/"target"),"CARGO_BUILD_BUILD_DIR":str(lane/"shared")}
    with (out/"stdout").open("xb") as so,(out/"stderr").open("xb") as se:
        rc=subprocess.run(["strace","-ff","-qq","-s","131072","-e","trace=execve","-o",out/"exec",*command],
                          cwd=src,env=e,stdout=so,stderr=se,timeout=120).returncode
    units=[]; full=[]; cached=[]; links=[]
    for t in sorted(out.glob("exec.*")):
        for line in t.read_text().splitlines():
            m=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x|NULL|\[).*= 0',line)
            if not m:continue
            f=Path(ast.literal_eval(m[1]));a=ast.literal_eval(m[2])
            if f.name=="rustc" and "--crate-name" in a:
                unit=a[a.index("--crate-name")+1]
                if unit=="___":continue
                assert f.samefile(sdk/"bin/rustc")
                item=[unit,"--test" in a,Path(a[a.index("--out-dir")+1]).name if "--out-dir" in a else None]
                (cached if "link-only" in a or "-Zlink-only" in a else full).append(item)
            if f.name in ("ld","ld.bfd","rust-lld","ld.lld") and "-o" in a:
                assert sha(f)=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
                links.append(Path(a[a.index("-o")+1]).name)
    for ln in (out/"stdout").read_bytes().splitlines():
        v=json.loads(ln)
        assert v["reason"]!="build-script-executed"
        if v["reason"]=="compiler-artifact":
            units.append([v["target"]["name"],v["target"]["kind"],v["profile"]["test"],v["fresh"],
                          sha(Path(v["executable"])) if v.get("executable") else None])
    records={p.name:{"sha":sha(p),"elf":sha(Path(json.loads(p.read_bytes())["executable"]["path"]))}
             for p in lane.rglob("*.rlink-cache.json")}
    j={"rc":rc,"command":command,"units":units,"full":full,"cached":cached,"stock_links":links,
       "old_linkable":records,"raw":{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
    put(out/"result.json",j);reports[out.name]=j
    print(out.name,rc,len(full),len(cached),len(links),len(records),flush=True)
    assert not rc
    if number==2 or arm=="candidate" and mode in ("check","lib"):
        assert not full and not cached and not links and all(z[3] for z in units)
    if arm=="candidate" and mode=="native" and number==1:
        trained=reports["parent-native-2"]
        old_names=sorted(n.removesuffix(".rlink-cache.json") for n in trained["old_linkable"])
        assert sorted(links)==old_names and len(full)==len(old_names) and not cached,(old_names,links,full,cached)
        assert sum(not u[3] for u in units)==len(old_names)
        assert all(u[3] for u in units if u[1]==["lib"] and not u[2])
        assert sorted((u[:3]+u[4:] for u in units),key=str)==sorted((u[:3]+u[4:] for u in trained["units"]),key=str)

if phase=="train":
    old_ver=switch(old,old_sha);(root/"old.version").write_bytes(old_ver)
    for mode in ("check","lib","native"):
        for n in (1,2):run("parent",mode,n)
    put(root/"trained.json",{"old":old_sha,"worker":sha(Path(__file__)),"version":sha(root/"old.version"),"receipt":{k:sha(root/k/"result.json") for k in reports}})
    sys.exit(0)
schema=json.loads((root/"trained.json").read_bytes())
assert schema["old"]==sha(live)==old_sha and schema["worker"]==sha(Path(__file__))
old_ver=(root/"old.version").read_bytes()
for k,h in schema["receipt"].items():
    f=root/k/"result.json";assert sha(f)==h;reports[k]=json.loads(f.read_bytes())
new_ver=switch(new,new_sha);(root/"new.version").write_bytes(new_ver)
assert old_ver==new_ver
for mode in ("check","lib","native"):
    for n in (1,2):run("candidate",mode,n)
put(root/"terminal.json",{"old":old_sha,"new":new_sha,"full_version":sha(root/"old.version"),
                         "receipts":{n:sha(root/n/"result.json") for n in reports}})

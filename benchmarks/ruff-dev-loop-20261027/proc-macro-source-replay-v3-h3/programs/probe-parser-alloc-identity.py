"""Native producer and ordinary consumer with zero macro or registry crates."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys

P=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027");F=P/"frozen-toolchain";X=Path.home()/".cache/ohm-233-position-qualified-20261027"
J=P/"mixed-registry-only-pilot";O=J/"minimal-plain-allocation-identity";O.mkdir(mode=0o700)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
path=O/"source";path.mkdir();results={}
source='''#![crate_type="rlib"]
#[inline] pub fn left() -> (&'static str, u32) { ("a long repeated string from the same module", 1) }
#[inline] pub fn right() -> (&'static str, u32) { ("a long repeated string from the same module", 7) }
pub fn observed() -> bool { left().0 == right().0 && right().1 == 8 }
'''
(path/"app.rs").write_text('fn main() { assert!(plain::observed()); println!("{}", plain::right().1); }\n')
cfg=dict(os.environ,RUSTUP_HOME=str(P/"rustup"),RUSTUP_AUTO_INSTALL="0",RUSTC_BOOTSTRAP="1")
ref=X/"drivers/driver-dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"
for n,image in [("r233",ref),("replay-v3",P/"parse-source-replay-v3/candidate-driver.so")]:
    for policy,opts in [("rdr",["-Zpublic-api-hash","-Zcache-proc-macros"]),("ordinary",[])]:
        d=O/(n+"-"+policy);d.mkdir();rows={}
        ns=["bwrap","--ro-bind","/","/","--dev","/dev","--proc","/proc","--tmpfs","/tmp","--bind",str(O),str(O),"--ro-bind",str(image),str(F/"lib/librustc_driver-774a793a844d5500.so"),"--chdir",str(path),"--"]
        for h,v,ic in [("train",7,"retained"),("warm",8,"retained"),("empty",8,"empty"),("repeat-empty",8,"second-empty")]:
            k=d/h;k.mkdir();(path/"plain.rs").write_text(source.replace(", 7)",f", {v})"));shutil.copyfile(path/"plain.rs",k/"plain.rs")
            args=["rustc","+ohm","--sysroot",str(F),"--edition=2024","--emit=link,metadata","-Copt-level=1","-Cdebuginfo=2","-Ccodegen-units=16","-Cincremental="+str(d/ic),*opts,"-Zmeta-stats","plain.rs"];save(k/"argv.json",args)
            q=subprocess.run([*ns,*args],env=cfg,capture_output=True);(k/"stderr").write_bytes(q.stderr);assert not q.returncode,q.stderr.decode()
            shutil.copyfile(path/"libplain.rmeta",k/"raw.rmeta")
            z=subprocess.run([*ns,"rustc","+ohm","--sysroot",str(F),"-Zls=root","libplain.rmeta"],env=cfg,capture_output=True,check=True);(k/"header").write_bytes(z.stdout)
            xs={}
            for l in q.stderr.decode().splitlines():
                m=re.fullmatch(r"meta-stats\s+(.+?)\s+([0-9,_]+)\s+\(\s*[0-9.]+%\)",l)
                if m:xs[m[1]]=int(m[2].replace(",","").replace("_",""))
            rows[h]=dict(raw=sha(k/"raw.rmeta"),size=(k/"raw.rmeta").stat().st_size,header=z.stdout.decode().splitlines()[2:4],stats=xs)
            if v==8:
                z=subprocess.run([*ns,"rustc","+ohm","--sysroot",str(F),"app.rs","--extern","plain=libplain.rlib","-o","app"],env=cfg,capture_output=True,check=True);(k/"app.stderr").write_bytes(z.stderr)
                z=subprocess.run([*ns,str(path/"app")],env=cfg,capture_output=True,check=True);assert z.stdout.strip()==b'8';rows[h]["native"]=z.stdout.decode().strip()
        results[n+"/"+policy]=rows;save(O/"results.json",results)
        a,b=rows["warm"],rows["empty"];print(n,policy,a["size"],b["size"],{k:[a["stats"].get(k),b["stats"].get(k)] for k in a["stats"].keys()|b["stats"].keys() if a["stats"].get(k)!=b["stats"].get(k)},flush=True)

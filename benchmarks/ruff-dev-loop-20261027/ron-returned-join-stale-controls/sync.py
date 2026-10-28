import argparse, hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAGIC = b"OHMJ_UNIQUE_FIXTURE_17END"
def sha(path):
    with Path(path).open("rb") as f: return hashlib.file_digest(f, "sha256").hexdigest()
def fs(path):
    s = path.stat()
    return dict(sha=sha(path), dev=s.st_dev, inode=s.st_ino, ns=s.st_mtime_ns, size=s.st_size)
def put(path, text):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);return path
def save(path,obj):
    path.write_text(json.dumps(obj,indent=2)+"\n")
def native(work, sdk, rustuphome, cargo, bitflags, variant, kind, value, driver):
    work.mkdir(parents=True,exist_ok=False)
    tc=work/"rustup/toolchains/ohm"
    (tc/"bin").mkdir(parents=True)
    (tc/"lib").mkdir()
    for x in (sdk/"lib").iterdir():
        y=driver if x.name.startswith("librustc_driver-") else x
        (tc/"lib"/x.name).symlink_to(y.resolve())
    for n in ("rustc","rustdoc"):
        (tc/"bin"/n).symlink_to((sdk/"bin"/n).resolve())
    (tc/"bin/cargo").symlink_to(cargo.resolve())
    src=work/"workspace"
    shutil.copytree(bitflags/"src",src/"bitflags/src")
    for name in ("spec.md","CHANGELOG.md","README.md"):
        shutil.copyfile(bitflags/name,src/"bitflags"/name)
    assert sha(src/"bitflags/src/public.rs")=="1237676ca4687d8eb8364eb52b23c5f284f73f4d4113ee833fa3470c8b512be9"
    probe_src=(HERE/"fixtures/probe.rs").read_text().replace("feature(proc_macro_span)","feature(proc_macro_span,proc_macro_expand)")
    probe_src += (HERE/"fixtures/sync-addition.rs").read_text().replace("OHMJ_UNIQUE_FIXTURE_17END","OHMJ_UNIQUE_FIXTURE_"+value+"END")
    put(src/"probe/src/lib.rs",probe_src)
    actual=(HERE/"fixtures/actual.rs").read_text().replace("    println!",'    println!("value={}",probe::hold!('+('include_str!("../input.txt")' if kind=="include" else 'dso')+'));\n    println!')
    app=put(src/"app/src/main.rs",actual)
    put(src/"app/input.txt",value)
    for pkg in ("bitflags","probe","app"):
        manifest=f'[package]\nname="{pkg}"\nversion="0.0.1"\nedition="2021"\n'
        if pkg=="probe":manifest+='[lib]\nproc-macro=true\n'
        if pkg=="app":manifest+='[dependencies]\nbitflags={path="../bitflags"}\nprobe={path="../probe"}\n'
        put(src/pkg/"Cargo.toml",manifest)
    put(src/"Cargo.toml",'[workspace]\nmembers=["app","probe","bitflags"]\nresolver="2"\n[profile.dev]\ndebug="line-tables-only"\nlto="off"\n')
    native_rustc=(sdk/"bin/rustc").resolve()
    wrapper=put(work/"rustc-entry.py","""#!/usr/bin/python3
import json,os,pathlib,sys
args=sys.argv[1:]
if '--crate-name' in args:
    c=args[args.index('--crate-name')+1]
    open(os.environ['OHM_JOB_LOG'],'a').write(json.dumps([c,args])+'\\n')
    if c=='app' and os.environ['OHM_JOIN_OPERATION'] in ('drop','keep'):
        os.environ['LD_PRELOAD']=os.environ['OHM_PRELOAD_PATH']
os.execv(os.environ['OHM_FRONTEND'],[os.environ['OHM_FRONTEND'],'--sysroot',os.environ['OHM_HOLDOUT_SYSROOT'],*args])
""")
    wrapper.chmod(0o755)
    coord=work/"coord";coord.mkdir()
    env={"PATH":rustuphome+os.pathsep+"/usr/bin:/bin","HOME":str(work/"home"),"RUSTUP_HOME":str(work/"rustup"),"CARGO_HOME":str(work/"cargo-home"),"CARGO_TARGET_DIR":str(work/"target"),"CARGO_BUILD_BUILD_DIR":str(work/"shared"),"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","CARGO_NET_OFFLINE":"true","CARGO_BUILD_JOBS":"2","CARGO_TERM_COLOR":"never","RUSTUP_AUTO_INSTALL":"0","RUSTC":str(wrapper),"RUSTC_BOOTSTRAP":"probe","LD_LIBRARY_PATH":str(tc/"lib"),"OHM_JOIN_COORD":str(coord),"OHM_JOIN_OPERATION":variant,"OHM_FRONTEND":str(native_rustc),"OHM_HOLDOUT_SYSROOT":str(sdk),"OHM_PRELOAD_PATH":str(HERE/"runtime/libjoin-diagnostic.so"),"OHM_JOIN_RECEIPT":str(work/"native.log")}
    # rustc uses its own RPATH, including separately selected library dirs. The CLI is verified by its actual marker in each output.
    syms=subprocess.check_output(["nm","-D","--defined-only",driver],text=True).splitlines()
    _,sym,addr=next((a,b,int(a,16)) for l in syms if (ls:=l.split()) and len(ls)==3 and (a:=ls[0]) and (b:=ls[-1]).endswith("span_join") and "proc_macro_server" in b)
    cmd=["objdump","-d","--start-address="+hex(addr),"--stop-address="+hex(addr+850),driver]
    asm=subprocess.check_output(cmd,text=True)
    hits=re.findall(r'^\s*([0-9a-f]+):\s+(c6 [0-9a-f ]+01)\s+movb\s+\$0x1,0x[0-9a-f]+\(%[a-z]+\)',asm,re.M)
    assert hits,(sym,asm)
    # This is the sole immediate store in the active join symbol, following expansion-cache invalidation.
    hit,raw=hits[0];delta=int(hit,16)-addr
    assert delta<600 and len(bytes.fromhex(raw))==7 and 'invalidate_cached_expansion' in asm[:asm.index(hit+':')]
    env.update(OHM_JOIN_SYMBOL=sym,OHM_JOIN_DELTA=hex(delta),OHM_JOIN_BYTES=bytes.fromhex(raw).hex())
    proof={"symbol":sym,"delta":hex(delta),"instruction":bytes.fromhex(raw).hex(),"driver":sha(driver),"cargo":sha(cargo),"rustc":sha(native_rustc),"source":sha(src/"bitflags/src/public.rs")}
    save(work/"subjects.json",proof)
    outcomes=[]
    def invoke(name, replace=False, data=None):
        rec=work/name;rec.mkdir()
        jobs=rec/"jobs.jsonl"
        env["OHM_JOB_LOG"]=str(jobs)
        if replace: (coord/"armed").touch()
        with (rec/"stdout").open("w") as out, (rec/"stderr").open("w") as err:
            proc=subprocess.Popen(["cargo","+ohm","build","--offline","-p","app","--message-format=json"],cwd=src,env=env,stdout=out,stderr=err)
            if replace:
                limit=time.monotonic()+40
                while not (coord/"observed").exists() and proc.poll() is None and time.monotonic()<limit: time.sleep(.01)
                assert (coord/"observed").exists(),(name,proc.poll(),(rec/"stderr").read_text())
                assert (coord/"observed").read_text()=="17"
                live=(src/"app/input.txt") if kind=="include" else data
                before=fs(live); b=live.read_bytes()
                if kind=="dso":
                    assert b.count(MAGIC)==1,(live,b.count(MAGIC))
                    b=b.replace(MAGIC,MAGIC.replace(b"17",b"29"))
                else: assert b==b"17"; b=b"29"
                new=live.with_name(live.name+".replacement")
                new.write_bytes(b);new.chmod(live.stat().st_mode&0o777);os.utime(new,ns=(before["ns"],before["ns"]));os.replace(new,live)
                after=fs(live)
                assert before["ns"]==after["ns"] and before["size"]==after["size"] and before["inode"]!=after["inode"] and before["sha"]!=after["sha"]
                save(rec/"replacement.json",dict(before=before,after=after,observed="17"))
                (coord/"release").touch()
            code=proc.wait(timeout=80)
            if replace:(coord/"armed").unlink()
        if code: raise RuntimeError((name,code,(rec/"stderr").read_text(),(rec/"stdout").read_text()[-4500:]))
        rows=[j for l in (rec/"stdout").read_text().splitlines() if (j:=json.loads(l)).get("reason")=="compiler-artifact"]
        a=next(x for x in rows if x["target"]["name"]=="app")
        dso=next(Path(n) for x in rows if x["target"]["name"]=="probe" for n in x["filenames"] if n.endswith(".so"))
        text=subprocess.check_output([a["executable"]],text=True).strip().splitlines()
        assert len(text)==4 and text[1:]==["bitflags/src/public.rs:17:37-17:38","bitflags/src/public.rs:17:90-17:98","bitflags/src/public.rs:17:37-17:98"]
        deps=[x for x in (work/"target").rglob("app.d") if x.parent.name=="out"]
        assert len(deps)==1
        dep=deps[0].read_bytes();(rec/"rustc.d").write_bytes(dep)
        m=b"ohm-foreign-span-bytes" in dep
        assert m==(variant!="drop"),(name,variant,m)
        js=[json.loads(z)[0] for z in jobs.read_text().splitlines()] if jobs.exists() else []
        runtime=text[0].strip()
        outcomes.append(dict(phase=name,program=runtime,true_compilers=js,fresh=a["fresh"],marker=m,external_image=sha(dso),executable=sha(a["executable"]),readback=text[1:]))
        save(work/"results.json",outcomes)
        return dso
    dso=invoke("prime")
    if value=="29": return outcomes
    invoke("trained-1");invoke("trained-2")
    app.write_text(actual+"\nconst _: u8 = 1;\n")
    invoke("synchronized",True,dso)
    invoke("repeat-1");invoke("repeat-2")
    return outcomes
def main():
    ap=argparse.ArgumentParser()
    for k in ("sdk","cargo","driver","bitflags","work"):ap.add_argument("--"+k,required=True,type=Path)
    ap.add_argument("--rustup-bin",required=True)
    ap.add_argument("--only",choices=["dso","include"])
    ap.add_argument("--variants",nargs="+",default=["keep","drop"])
    a=ap.parse_args();out={}
    a.work.mkdir(parents=True,exist_ok=False)
    for k in ([a.only] if a.only else ["include","dso"]):
        for v in a.variants:
            for label,val in (("inc","17"),("clean","29")):
                key=f"{k}-{v}-{label}"; print("start",key,flush=True)
                out[key]=native(a.work/key,a.sdk,a.rustup_bin,a.cargo,a.bitflags,v,k,val,a.driver)
                print(key,[i["program"] for i in out[key]],flush=True)
                save(a.work/"summary.json",out)
if __name__=="__main__":main()

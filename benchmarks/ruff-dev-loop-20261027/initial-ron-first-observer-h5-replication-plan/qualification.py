"""Trace genuine empty, first-unchanged, and settled release Ruff builds in three independent arms."""
from pathlib import Path
import fcntl,hashlib,json,os,shutil,struct,subprocess,sys,time
p=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027");sys.path.insert(0,str(Path(__file__).resolve().parent/"support"))
from shared import BUILD,CH,FROZEN,SONAME,TARGET,TRANSFER,WT,env,floors,git,load,need,sha,skeleton,trusted
from roster import audit_json
from replay_processes import parsed,records
import replay_processes
r=p/"ron-first-replication-release-v1";q=r/"inputs";run=Path(__file__).resolve()
epoch="93526150df078af7dd8fc4226cdcc469539d2001"
basec="dd5cab154b8dcd09ccc2753160d314cade80979b2d055ee66aa9e2217e05e7e1"; newc="51e2e21a219004007a2d51e19e5a8edc57b47c7eb290383f4bbc13428e0f7d9c"
baser="dec72d1e68fdb0f8ff91fc98e8a826bf837878eca30b1ec5ea2f3258b6b2f99f"; newr="185629fabec9baacfd8fd7e61d6d84e79f69aa9abf4a4a9bb431c24f0a89d040"
def write(path,v):path.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def default_output(directory):
    for pid,exe,a in records(directory):
        if exe=="/usr/bin/ld" and "-o" not in a and "--help" not in a and "--version" not in a:
            need(any(s.endswith("/crti.o") for s in a) and any(s.endswith("/crtn.o") for s in a) and any(s.startswith("/tmp/") and s.endswith(".o") for s in a),("unknown link",pid))
            yield pid,exe,[*a,"-o","a.out"]
        else:yield pid,exe,a
replay_processes.records=default_output
def relocate(path):return str(path).replace(str(p)+"/","$RUN/")
def elf(path):
    data=bytearray(path.read_bytes());assert data[:6]==b"\x7fELF\x02\x01"
    raw=hashlib.sha256(data).hexdigest()
    off=struct.unpack_from("<Q",data,40)[0];width,num,idx=struct.unpack_from("<HHH",data,58)
    def section(i):return struct.unpack_from("<IIQQQQIIQQ",data,off+i*width)
    tab=section(idx);names=data[tab[4]:tab[4]+tab[5]];entry=None;build_id=None
    for i in range(num):
        s=section(i);name=names[s[0]:names.index(0,s[0])]
        if name==b".rodata":
            entry=s[9];data[off+i*width+56:off+i*width+64]=bytes(8)
        if name==b".note.gnu.build-id":
            n,d,t=struct.unpack_from("<III",data,s[4]);lo=s[4]+12+((n+3)//4)*4
            assert t==3 and data[s[4]+12:s[4]+12+n]==b"GNU\0" and lo+d<=s[4]+s[5]
            build_id=bytes(data[lo:lo+d]).hex();data[lo:lo+d]=bytes(d)
    return {"bytes":len(data),"raw":raw,"except_registered_wild_fields":hashlib.sha256(data).hexdigest(),"build_id":build_id,"rodata_entsize":entry}
def probes_native(j,e):
    root=TARGET/"debug";tests=[Path(x) for x in j["executables"]];stdlib,=[f for f in tests if f.name.startswith("ruff_python_stdlib-")]
    def runa(argv,expected=0,stdin=None):
        a=subprocess.run(argv,cwd=WT,env=e,input=stdin,capture_output=True);need(a.returncode==expected,(argv,a.returncode,a.stderr[-400:]));return a.stdout
    ls=runa([stdlib,"--list"]);names=[s.removesuffix(": test") for s in ls.decode().splitlines() if s.endswith(": test")];need(bool(names),"empty genuine stdlib test listing")
    unit=runa([stdlib,"--exact",names[0]]);need(b"1 passed" in unit and names[0].encode() in unit,"test caller")
    lint=runa([root/"ruff","check","--isolated","--no-cache","--select","E712","--output-format","concise","-"],expected=1,stdin=b"if a == True:\n    pass\n");need(b"E712" in lint,lint)
    return {"ruff":runa([root/"ruff","--version"]).decode().strip(),"ty":runa([root/"ty","--version"]).decode().strip(),"lint":lint.decode(),"stdlib_test_list_sha256":hashlib.sha256(ls).hexdigest(),"stdlib_test_count":len(names),"executed":names[0],"passed":True}
def dirs(key):return r/"states"/key,r/"results"/key
def setup(key,arm,mode):
    st,dest=dirs(key);need(not st.exists() and not dest.exists(),("existing private state",key));floors(16<<30);st.mkdir(parents=True,mode=0o700);dest.mkdir(parents=True,mode=0o700)
    for n in ("target","build","home"):(st/n).mkdir(mode=0o700)
    shutil.copytree(p/"rustup",st/"rustup",symlinks=True)
    subprocess.run(["cp","-a","--reflink=auto","--",str(CH/"registry"),str(st/"home/registry")],check=True)
    for n in ("config","config.toml"):
        if (CH/n).is_file():shutil.copy2(CH/n,st/"home"/n)
    op=skeleton(st)
    for a,b in ((dest,dest),(st/"target",TARGET),(st/"build",BUILD),(st/"home",CH),(st/"rustup",p/"rustup")):op+=["--bind",str(a),str(b)]
    for a,b in ((q/"candidate-cargo-v3" if arm in "AC" else TRANSFER/"A",FROZEN/"bin/cargo"),(q/"controls-v2/release/candidate-driver.so" if arm in "BC" else TRANSFER/"rustc-driver",FROZEN/"lib"/SONAME)):op+=["--ro-bind",str(a),str(b)]
    e=env();e.pop("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST");e.pop("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST");e["CARGO_BUILD_JOBS"]="8"
    if mode=="qualify":e["CARGO_LOG"]="cargo::compiler::fingerprint=info"
    subprocess.run([*op,"--","taskset","-c","0-23",sys.executable,"-Bu",str(run),"inside",key,arm,mode],cwd=WT,env=e,check=True)
def inside(key,arm,mode):
    st,dest=dirs(key);trusted();need(not any(TARGET.iterdir()) and not any(BUILD.iterdir()) and not git("status","--porcelain") and git("rev-parse","HEAD").decode()==epoch,"unmodified source or empty stores")
    cargo_hash=sha(FROZEN/"bin/cargo");drv=sha(FROZEN/"lib"/SONAME);need(cargo_hash==(newc if arm in "AC" else basec) and drv==(newr if arm in "BC" else baser),"wrong product")
    wild=sha(p/load(TRANSFER/"installation.json")["bundled_wild"]);need(wild=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5" and sha(FROZEN/"bin/rustc")=="4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f" and len(os.sched_getaffinity(0))==24 and os.environ["CARGO_BUILD_JOBS"]=="8","binding")
    e=dict(os.environ);results={};cmd=["cargo","+ohm","test","--no-run","--locked","--offline","--message-format=json"]
    for phase in ("cold","first","settled"):
        d=dest/phase;d.mkdir();floors()
        trace=["strace","-ff","-qq","-s","262144","-e","trace=execve,execveat","-o",str(d/"exec")] if mode=="qualify" else []
        start=time.monotonic_ns()
        with (d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:x=subprocess.run(trace+cmd,cwd=WT,env=e,stdout=so,stderr=se,stdin=subprocess.DEVNULL)
        ns=time.monotonic_ns()-start;write(d/"status.json",{"rc":x.returncode,"elapsed_ns":ns});need(x.returncode==0,("Cargo failed",d))
        j=audit_json(d/"stdout","test");arts=[row for l in (d/"stdout").read_bytes().splitlines() if (row:=json.loads(l)).get("reason")=="compiler-artifact"]
        need(len(arts)==619 and len(j["executables"])==102 and len(j["elf"])==110,(key,phase,"complete Ruff roster"));fr=sum(a["fresh"] for a in arts)
        roster=sorted((a["package_id"],a["target"]["name"],a["target"]["kind"],a["profile"]["test"]) for a in arts)
        procs=None
        if trace:
            real=parsed(d,j);write(d/"processes.json",real);procs={"full":[a[1] for a in real["rustc"] if a[2]=="full"],"relink":[a[1] for a in real["rustc"] if a[2]=="link-only"],"wild":sum(a[2] for a in real["native_links"]),"system":sum(not a[2] for a in real["native_links"]),"probe":[[pid,Path(x).name] for pid,x,a in records(d) if Path(x).name=="rustc" and "-Zohm-observer-dep-info" in a and "--print=sysroot" in a]}
        native={relocate(f):elf(Path(f)) for f in j["elf"]};write(d/"native.json",native)
        a,=[a for a in arts if a["target"]["name"]=="ron"];rl,=[Path(x) for x in a["filenames"] if x.endswith(".rlib")];rm=rl.with_suffix(".rmeta");di,=rl.parent.glob("ron-*.d");fp=rl.parent.parent/"fingerprint"/"dep-lib-ron"
        raw=fp.read_bytes();idx=raw.rfind(b"OBS1");need(idx>=0 and len(raw)-idx==41,("missing actor receipt",idx));seal=raw[idx+8]==1
        checkdir=d/"ron";checkdir.mkdir()
        for inp in ([di,fp,rm,rl] if mode=="qualify" else [di,fp]):shutil.copy2(inp,checkdir/inp.name)
        selected={"elapsed_ns":ns,"fresh":fr,"ron_complete":seal,"ron_depinfo":sha(di),"ron_fingerprint":sha(fp),"ron_rmeta":sha(rm),"ron_rlib":sha(rl),"checksums":sum(l.startswith("# checksum:") for l in di.read_text().splitlines()),"cargo_stdout":sha(d/"stdout"),"cargo_stderr":sha(d/"stderr"),"messages":json.dumps(j["messages"],sort_keys=True),"roster":hashlib.sha256(json.dumps(roster,sort_keys=True).encode()).hexdigest(),"processes":procs,"native":sha(d/"native.json")}
        results[phase]=selected;write(d/"summary.json",selected);print(key,phase,fr,seal,selected["checksums"],[(k,len(v) if isinstance(v,list) else v) for k,v in (procs or {}).items()],flush=True)
    c,f,s=[results[t] for t in ("cold","first","settled")];need(c["fresh"]==0 and f["fresh"]==(619 if arm=="C" else 563) and s["fresh"]==619,(key,"per-phase fresh roster",[(z["fresh"],z["ron_complete"]) for z in (c,f,s)]))
    need(c["ron_complete"]==(arm=="C") and f["ron_complete"] and s["ron_complete"] and c["checksums"]==(45 if arm=="C" else 0) and f["checksums"]==s["checksums"]==45,("auth",key))
    need(c["roster"]==f["roster"]==s["roster"] and c["messages"]==f["messages"]==s["messages"],("roster or diagnostics changed",key))
    cold,first,settled=[load(dest/t/"native.json") for t in ("cold","first","settled")];need(first==settled and cold.keys()==first.keys(),("unstable settlement",key))
    differences={}
    for n,(a,b) in ((n,(v,first[n])) for n,v in cold.items() if v!=first[n]):
        need(arm!="C" and a["except_registered_wild_fields"]==b["except_registered_wild_fields"] and a["bytes"]==b["bytes"] and {a["rodata_entsize"],b["rodata_entsize"]}<={0,8},("new native difference",key,n,a,b));differences[n]=[a,b]
    if mode=="qualify":
        for index,phase in enumerate(("cold","first","settled")):
            v=results[phase]["processes"]
            if index==0:need(len(v["full"])==636 and not v["relink"] and v["wild"] in (200,201) and v["system"]==62,("unexplained cold jobs",key,v["wild"]))
            elif index==1 and arm!="C":need(v["full"]==["ron"] and len(v["relink"])==v["wild"]==50 and v["system"]==0,("wrong baseline acquisition",key,v))
            else:need(not v["full"] and not v["relink"] and v["wild"]==v["system"]==0,("extra native jobs",key,phase,v))
    identity=probes_native(j,e);need(not git("status","--porcelain"),"Ruff tree modified")
    write(dest/"complete.json",{"arm":arm,"cargo":cargo_hash,"rust":drv,"wild":wild,"mode":mode,"case":key,"phases":results,"cold_to_first_native_differences":differences,"ordinary_native_oracles":identity,"free_bytes":shutil.disk_usage(p).free})
if __name__=="__main__":
    if sys.argv[1]=="inside":inside(*sys.argv[2:]);sys.exit(0)
    if sys.argv[1]!="qualification":raise SystemExit("Native timed commands need the separate prebound schedule and launch grant")
    need(r.is_dir() and (r/"inputs/installation.json").is_file() and not (r/"results").exists(),"new independent workspace oracle root")
    with (p/"native-measure.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for arm in ("D","C"):setup("qualify-"+arm,arm,"qualify")

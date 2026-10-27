"""Exercise a real first-observer Rust upgrade and downgrade in the same target and rustup path."""
from pathlib import Path
import json,os,re,shutil,subprocess,sys
p=Path("/mnt/devbox-scratch/dev-user/ohm-empty-test-h4-20261027");sys.path.insert(0,str(p/"runner"))
from shared import BUILD,CH,FROZEN,TARGET,TRANSFER,env,floors,need,sha,skeleton,trusted
from replay_processes import records
q=p/"first-proof-stage1";s1="librustc_driver-15d35e5526bb94f8.so";src=q/"fixture-root";tag=sys.argv[1]
root=Path(__file__).resolve().parent/("hot-swap-"+tag);st=root/"state"
cargo=(q/"candidate-cargo") if len(sys.argv)<3 else Path(sys.argv[2]); cs=sha(cargo)
e=env();e.pop("CARGO_UNSTABLE_OHM_PROC_MACRO_TRUST");e.pop("CARGO_UNSTABLE_OHM_NATIVE_TOOL_TRUST")
e.update(CARGO_BUILD_JOBS="4",CARGO_LOG="cargo::compiler::fingerprint=info")
if sys.argv[-1]=="inside":
    label=sys.argv[3];pair=sys.argv[4];trusted()
    d=root/label;d.mkdir()
    if label=="prime":subprocess.run(["cargo","+ohm","generate-lockfile","--offline"],cwd=src,env=e,check=True,capture_output=True)
    argv=["strace","-ff","-qq","-s","65536","-e","trace=execve,execveat","-o",str(d/"exec"),"cargo","+ohm","build","-p","hold_direct","--offline","--locked","--message-format=json"]
    res=subprocess.run(argv,env=e,cwd=src,capture_output=True);(d/"stdout").write_bytes(res.stdout);(d/"stderr").write_bytes(res.stderr)
    arts=[v for l in res.stdout.splitlines() if (v:=json.loads(l)).get("reason")=="compiler-artifact"]
    exe=[v for v in arts if v["target"]["name"]=="hold_direct" and v.get("executable")]
    data={"cargo":sha(FROZEN/"bin/cargo"),"driver":sha(FROZEN/"lib"/s1),"frontend":sha(FROZEN/"bin/rustc"),"returncode":res.returncode,"unknown_observer_option":"unknown unstable option" in res.stderr.decode(errors="replace") and "ohm-observer-dep-info" in res.stderr.decode(errors="replace"),"rustc":[]}
    for pid,x,a in records(d):
        if Path(x).name=="rustc":data["rustc"].append({"crate":a[a.index("--crate-name")+1] if "--crate-name" in a else None,"capability":"--print=sysroot" in a and "-Zohm-observer-dep-info" in a,"new_flag":"-Zohm-observer-dep-info" in a,"known":"-Zbinary-dep-depinfo" in a})
    if res.returncode==0:
        need(len(exe)==1,exe)
        program=Path(exe[0]["executable"])
        run=subprocess.run([program],capture_output=True,check=True);data["native"]=run.stdout.decode();data["fresh"]=exe[0]["fresh"];data["elf"]=sha(program)
    (d/"receipt.json").write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print(label,pair,data["returncode"],data.get("native","").splitlines()[:1],data["unknown_observer_option"],flush=True);sys.exit(0)
need(not root.exists(),root);root.mkdir(mode=0o700);st.mkdir();shutil.copytree(q/"heldout-fixture",st/"src")
for n in ("target","build","home"):(st/n).mkdir(mode=0o700)
shutil.copytree(p/"rustup",st/"rustup",symlinks=True)
for name in ("config.toml","config"):
    if (CH/name).is_file():shutil.copy2(CH/name,st/"home"/name)
physical=st/"src/hold_direct/src/main.rs";text=physical.read_text()
need(len(re.findall(r"fn main\(\)\s*\{",text))==1,text)
new_front=st/"front-reinstalled";shutil.copy2(q/"sysroot/bin/rustc",new_front);os.utime(new_front,None)
for label,pair,needle,replace_front in [
    ("prime","PP","initial",False),("fresh","PP",None,False),
    ("driver-only-downgrade","PA","old compiler",False),("driver-only-return","PP","new compiler",False),
    ("normal-reinstall-downgrade","PA","old reinstalled",True),("normal-reinstall-unchanged","PA",None,True),
    ("old-cargo-new-rust","AP","old Cargo",False),("both-restored","PP","both restored",False),("fresh-restored","PP",None,False)]:
    if needle:physical.write_text(re.sub(r"fn main\(\)\s*\{",f'fn main() {{println!("verified {needle}");',text,count=1))
    op=skeleton(st)
    for a,b in [(root,root),(st/"src",src),(st/"target",TARGET),(st/"build",BUILD),(st/"home",CH),(st/"rustup",p/"rustup")]:op+=["--bind",str(a),str(b)]
    for a,b in [(CH/"registry",CH/"registry"),(q/"sysroot",FROZEN),((cargo if pair[0]=="P" else TRANSFER/"A"),FROZEN/"bin/cargo"),((q/"candidate-driver-v2" if pair[1]=="P" else q/"old-driver"),FROZEN/"lib"/s1)]:op+=["--ro-bind",str(a),str(b)]
    if replace_front:op+=["--ro-bind",str(new_front),str(FROZEN/"bin/rustc")]
    subprocess.run([*op,"--","taskset","-c","24-27",sys.executable,"-B",str(Path(__file__)),tag,str(cargo),label,pair,"inside"],env=e,check=True)
receipts={r.parent.name:json.loads(r.read_bytes()) for r in root.glob("*/receipt.json")}
(root/"summary.json").write_text(json.dumps(receipts,indent=2,sort_keys=True)+"\n")

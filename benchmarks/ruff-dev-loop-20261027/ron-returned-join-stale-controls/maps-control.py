import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
src=Path(__file__).resolve().parent
r=Path(sys.argv[1]).resolve();r.mkdir(exist_ok=False);(r/"original").mkdir();(r/"shadow").mkdir()
driver=Path(os.environ["OHM_HOLDOUT_SYSROOT"])
rc=["rustc","+ohm","--sysroot",str(driver),"--edition=2021"]
so=r/"original/libmaps_probe.so"; alias=r/"original/alias.so";copy=r/"shadow/libmaps_probe.so"
shutil.copyfile(src/"fixtures/maps.rs",r/"maps.rs");(r/"main.rs").write_text('fn main(){println!("{}",maps_probe::image_topology!());}\n')
env=dict(os.environ,RUSTC_BOOTSTRAP="maps_probe",OHM_JOIN_ORIGINAL=str(so),OHM_JOIN_ALIAS=str(alias))
def run(a,**kwargs):return subprocess.run(a,cwd=r,text=True,env=env,capture_output=True,check=True,**kwargs).stdout.strip()
run([*rc,"--crate-type=proc-macro","--crate-name","maps_probe","maps.rs","-o",so])
os.link(so,alias);shutil.copyfile(so,copy);copy.chmod(0o755);os.link(copy,r/"shadow/other-name.so")
assert so.read_bytes()==copy.read_bytes() and so.stat().st_nlink==copy.stat().st_nlink==2
proof={}
for label,bind in (("original",[]),("shadow_same_spelling",["--ro-bind",str(copy),str(so)]),("both_shadow_aliases",["--ro-bind",str(copy),str(so),"--ro-bind",str(copy),str(alias)]),("restored",[])):
    ns=["bwrap","--die-with-parent","--ro-bind","/","/","--proc","/proc","--dev","/dev","--bind",str(r),str(r),*bind,"--chdir",str(r),"--"]
    run([*ns,*rc,"main.rs","--extern","maps_probe="+str(so),"-o",r/"app"])
    proof[label]=run([r/"app"])
    print(label,proof[label],flush=True)
assert proof["original"]==proof["restored"] and "alias=true;mapped_alias=true;" in proof["original"]
assert "alias=false;mapped_alias=false;" in proof["shadow_same_spelling"] and "nlink=2" in proof["shadow_same_spelling"]
assert "alias=true;mapped_alias=true;" in proof["both_shadow_aliases"]
(r/"summary.json").write_text(json.dumps({"dso_sha256":hashlib.sha256(so.read_bytes()).hexdigest(),"compiled_values":proof},indent=2)+"\n")

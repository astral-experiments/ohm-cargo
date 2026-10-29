"""Run real Rust code generation failure and recovery without compiler wrappers or injected flags."""
from pathlib import Path
import errno,hashlib,json,os,re,signal,subprocess,sys,time
import shutil
sdk=Path(sys.argv[1]).resolve(strict=True)
root=Path(sys.argv[2]).resolve();root.mkdir(mode=0o700)
arm="local"
proxy=shutil.which("cargo");assert proxy and (sdk/"bin/cargo").is_file() and (sdk/"bin/rustc").is_file()
def sha(f):
 with f.open("rb") as fd:return hashlib.file_digest(fd,"sha256").hexdigest()
def save(p,value):
 with p.open("x") as out:json.dump(value,out,sort_keys=True,indent=2);out.write("\n")
base=root/arm;base.mkdir(mode=0o700);r=base/"rustup";(r/"toolchains").mkdir(parents=True);(r/"toolchains/ohm").symlink_to(sdk)
src=base/"src";src.mkdir();provider=src/"dep/src/lib.rs";target=base/"target";shared=base/"shared";rec=base/"records";rec.mkdir()
def create(name,b):
 f=src/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(b)
create("Cargo.toml",'[package]\nname = "app"\nversion = "0.1.0"\nedition = "2024"\n[dependencies]\ndep = { path = "dep" }\n')
create("dep/Cargo.toml",'[package]\nname = "dep"\nversion = "0.1.0"\nedition = "2024"\n')
create("src/lib.rs",'pub fn value() -> u32 { dep::VALUE }\n')
create("src/main.rs",'fn main() { println!("{}", app::value()); }\n')
fifo=base/"codegen-input.s";fifo.write_text(".pushsection .text\n.byte 0x90\n.popsection\n")
asm=f'core::arch::global_asm!(r#".pushsection .rodata\n.byte {{v}}\n.popsection\n.include "{fifo}""#, v=const VALUE);\n'
base_source='pub const VALUE: u32 = 17;\n'+asm;changed=base_source.replace("= 17;","= 29;");failure=changed
create("dep/src/lib.rs",base_source)
env={"HOME":str(Path.home()),"PATH":str(Path(proxy).parent)+":/usr/bin:/bin","CARGO_HOME":str(base/"cargo-home"),"CARGO_TARGET_DIR":str(target),"CARGO_BUILD_BUILD_DIR":str(shared),"RUSTUP_HOME":str(r),"CARGO_TERM_COLOR":"never","CARGO_NET_OFFLINE":"true","RUSTUP_AUTO_INSTALL":"0","LANG":"C.UTF-8"}
cmd=[proxy,"+ohm","build","--offline","-j3","--message-format=json"]
results={}
def check(name,expected=None,capture=None):
 folder=rec/name;folder.mkdir()
 with (folder/"cargo.jsonl").open("xb") as out,(folder/"stderr").open("xb") as err:
  if capture!="deliberate":
   rc=subprocess.run(cmd,cwd=src,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=120).returncode
  else:
   marks=list(target.rglob("lib-app"));assert len(marks)==1;mark=marks[0]
   oldtime=mark.stat().st_mtime_ns;oldvalue=mark.read_bytes();assert re.fullmatch(b"[0-9a-f]{16}",oldvalue)
   proc=subprocess.Popen(cmd,cwd=src,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
   fd=None;deadline=time.monotonic()+20;seen=[]
   while proc.poll() is None and time.monotonic()<deadline:
    try:fd=os.open(fifo,os.O_WRONLY|os.O_NONBLOCK);break
    except OSError as e:
     if e.errno!=errno.ENXIO:raise
    time.sleep(.001)
   if fd is None:
    if proc.poll() is None:proc.kill();proc.wait()
    raise RuntimeError("real assembler did not open its input: "+(folder/"stderr").read_text())
   try:
    deadline=time.monotonic()+5
    while proc.poll() is None and time.monotonic()<deadline:
     try:stat=mark.stat();value=mark.read_bytes()
     except FileNotFoundError:continue
     item=[stat.st_mtime_ns,value.decode()]
     if not seen or seen[-1]!=item:seen.append(item)
     if stat.st_mtime_ns!=oldtime and re.fullmatch(b"[0-9a-f]{16}",value):break
     time.sleep(.001)
    actual=bool(seen and seen[-1][0]!=oldtime and re.fullmatch(r"[0-9a-f]{16}",seen[-1][1]))
    save(folder/"commit-observation.json",{"before":[oldtime,oldvalue.decode()],"states":seen,"committed_before_assembler_error":actual})
    assert actual,"consumer did not commit before interruption"
    candidates=[]
    for child in Path("/proc").iterdir():
     if not child.name.isdecimal():continue
     try:
      nums=(child/"status").read_text().split("PPid:")[1].split()[0]
      args=(child/"cmdline").read_bytes().split(b"\x00")
      if int(nums)==proc.pid and (child/"exe").samefile(sdk/"bin/rustc") and b"--crate-name" in args and args[args.index(b"--crate-name")+1]==b"dep":candidates.append(int(child.name))
     except (OSError,IndexError):continue
    assert len(candidates)==1,candidates
    pid=candidates[0];ref=os.pidfd_open(pid);signal.pidfd_send_signal(ref,signal.SIGKILL);os.close(ref)
    save(folder/"interrupt.json",{"pid":pid,"signal":"SIGKILL","actual_rustc":sha(sdk/"bin/rustc"),"cargo_pid":proc.pid,"committed_before_signal":actual})
   finally:os.close(fd)
   try:rc=proc.wait(timeout=30)
   except subprocess.TimeoutExpired:proc.kill();proc.wait();raise
 rows=[json.loads(line) for line in (folder/"cargo.jsonl").read_bytes().splitlines()];assert rows[-1]=={"reason":"build-finished","success":rc==0}
 arts=[[x["target"]["name"],x["target"]["kind"],x["fresh"]] for x in rows if x["reason"]=="compiler-artifact"]
 errors=[[x["target"]["name"],(x["message"].get("code") or {}).get("code"),x["message"]["message"]] for x in rows if x["reason"]=="compiler-message" and x["message"]["level"]=="error"]
 val={"rc":rc,"artifacts":arts,"errors":errors,"source":sha(provider),"stdout":sha(folder/"cargo.jsonl"),"stderr":sha(folder/"stderr")}
 if rc==0:
  elfs=[Path(x["executable"]) for x in rows if x.get("executable")];assert len(elfs)==1 and elfs[0].is_file()
  output=subprocess.check_output([elfs[0]],cwd=src,env=env);val.update(program_stdout=output.decode(),elf=sha(elfs[0]))
  assert expected==output.decode().strip(),(name,expected,val)
 elif capture=="deliberate":assert rc==101 and (folder/"interrupt.json").is_file() and ("SIGKILL" in (folder/"stderr").read_text() or "signal 9" in (folder/"stderr").read_text()),(name,val,(folder/"stderr").read_text())
 save(folder/"result.json",val);results[name]=val;print(arm,name,rc,arts,errors,val.get("program_stdout","").strip(),flush=True)
check("seed","17");check("unchanged","17")
saved=fifo.with_name("original-codegen-input.s");fifo.rename(saved);os.mkfifo(fifo,0o600)
provider.write_text(failure)
try:check("interrupted-provider",capture="deliberate")
finally:
 assert fifo.is_fifo() and saved.is_file();fifo.unlink();saved.rename(fifo)
provider.write_text(base_source);check("revert","17");check("revert-again","17")
for n in (target,shared):n.rename(n.with_name("held-warm-"+n.name))
check("clean-revert","17");provider.write_text(changed);check("independent-valid-change","29")
save(base/"complete.json",results)

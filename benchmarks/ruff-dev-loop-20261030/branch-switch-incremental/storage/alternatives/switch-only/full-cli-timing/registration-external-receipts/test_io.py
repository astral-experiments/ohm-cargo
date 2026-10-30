#!/usr/bin/env python3
"""Verify the escrow boundary inside a real, unprivileged measurement namespace."""
import argparse
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from receiver import canonical,check,digest,identity

def forbidden(path):
    check(os.statvfs(path.parent).f_flag&os.ST_RDONLY and not path.exists(), "write test must be a new name on a protected mount")
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_CLOEXEC,0o600)
    except OSError as e:
        check(e.errno==errno.EROFS,"mounted device did not enforce EROFS")
        return e.errno
    else:
        os.close(fd)
        raise AssertionError("protected device unexpectedly writable")

def run(p):
    full=Path(p.original).resolve()
    spec=importlib.util.spec_from_file_location("actual_measure",full/"measure.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    s=p.work/"io-fixture";s.mkdir();(s/"src").mkdir();temp=s/"tmp";temp.mkdir()
    q=p.spool/"io";q.mkdir()
    status=Path("/proc/self/status").read_text().splitlines()
    check(os.geteuid()==1000 and next(x.split()[1] for x in status if x.startswith("CapEff:"))=="0000000000000000" and
          next(x.split()[1] for x in status if x.startswith("NoNewPrivs:"))=="1","ordinary measurement permissions")
    absent=p.receiver_device
    check(not any(line.split()[2]==absent for line in Path("/proc/self/mountinfo").read_text().splitlines()),
          "external receiving ext4 filesystem remained visible")
    rejected=[forbidden(x/("qa-must-return-erofs-"+str(os.getpid()))) for x in
              (p.backing,p.actual_home_testdir,p.scratch)]
    denied_devices={x.stat().st_dev for x in (p.backing,p.actual_home_testdir,p.scratch)}
    outer=[]
    for path in Path("/proc/self/fd").iterdir():
        try:
            st=path.stat();info=Path("/proc/self/fdinfo",path.name).read_text()
        except FileNotFoundError:
            continue
        flags=int(next(x.split()[1] for x in info.splitlines() if x.startswith("flags:")),8)
        if flags&os.O_ACCMODE!=os.O_RDONLY:
            check(st.st_dev not in denied_devices and stat.S_ISREG(st.st_mode), "writable durable fd inherited")
            outer.append(int(path.name))
    # Use the same Rustup command, ordinary Cargo entry and actual mounted SDK.
    cargo_home=s/"cargo-home";cargo_home.mkdir()
    rustup=s/"rustup";(rustup/"toolchains").mkdir(parents=True);(rustup/"toolchains/ohm").symlink_to(p.sdk)
    env={"PATH":str(p.proxies)+":/usr/bin:/bin","HOME":str(s),"RUSTUP_HOME":str(rustup),"CARGO_HOME":str(cargo_home),
         "CARGO_TARGET_DIR":str(p.target/"cargo-target"),"CARGO_BUILD_BUILD_DIR":str(p.target/"cargo-shared"),
         "CARGO_NET_OFFLINE":"true","RUSTUP_AUTO_INSTALL":"0","CARGO_CACHE_AUTO_CLEAN_FREQUENCY":"never",
         "TMPDIR":str(temp),"LC_ALL":"C","LANG":"C"}
    (s/"Cargo.toml").write_text('[package]\nname="receipt_probe"\nversion="0.1.0"\nedition="2024"\n')
    (s/"Cargo.lock").write_text('version = 4\n\n[[package]]\nname = "receipt_probe"\nversion = "0.1.0"\n')
    check(Path(subprocess.check_output(["rustup","which","--toolchain","ohm","cargo"],env=env,text=True).strip()).samefile(p.sdk/"bin/cargo"),
          "wrong Cargo selected")
    rust=str(subprocess.check_output(["rustc","+ohm","-vV"],env=env,text=True))
    cargo=str(subprocess.check_output(["cargo","+ohm","-Vv"],env=env,text=True))
    m.CARGO=["cargo","+ohm","build","--locked","--offline","-j1","--message-format=json","-p","receipt_probe"]
    subject=s/"src/main.rs";body=lambda n:f'fn main() {{ println!("{n}"); }}\n'
    true_target=p.target/"cargo-target/debug/receipt_probe";rows=[]
    for phase,n,expected in [("cold",17,0),("edit",29,0),("fresh",29,0),("invalid",None,101),("repair",29,0)]:
        if phase!="fresh":subject.write_text(body(n) if n is not None else 'fn main() { let _:u8="invalid"; }\n')
        out=q/phase;out.mkdir()
        try:
            actual=m.ordinary_cargo(s,env,temp,out)
        except subprocess.CalledProcessError:
            actual=json.loads((out/"cargo.process.json").read_bytes())
        check(actual["exit"]==expected and actual["blocking_wait"]=="wait4" and actual["wall_ns"]>0,
              "real ordinary Cargo terminal missing")
        messages=[json.loads(y) for y in (out/"cargo.stdout").read_bytes().splitlines()]
        if n is not None:
            obj,=[j for j in messages if j.get("reason")=="compiler-artifact" and j["target"]["name"]=="receipt_probe"]
            check(Path(obj["executable"]).samefile(true_target) and
                  subprocess.check_output([true_target],text=True).strip()==str(n), "native executable value")
            if phase=="fresh":check(obj["fresh"] and digest(true_target)==rows[-1]["elf"],"genuine unchanged repeat")
            if phase=="repair":check(digest(true_target)==rows[1]["elf"],"repaired whole native output")
            exe=digest(true_target)
            bodies=q/"bodies";bodies.mkdir(exist_ok=True)
            archive=bodies/(exe+".zst")
            if not archive.exists():
                with archive.open("xb") as raw:
                    subprocess.run(["zstd","-q","-T1","-3","-c",true_target],stdout=raw,check=True)
                    raw.flush();os.fsync(raw.fileno())
                child=subprocess.Popen(["zstd","-qdc",archive],stdout=subprocess.PIPE)
                import hashlib
                with child.stdout as plain:check(hashlib.file_digest(plain,"sha256").hexdigest()==exe,"escrowed native test body")
                check(child.wait()==0,"compressed native readback")
        else:
            check(any(j.get("reason")=="compiler-message" and (j["message"].get("code") or {}).get("code")=="E0308"
                      for j in messages),"missing observed invalid source")
            exe=None
        rows.append(dict(phase=phase,exit=actual["exit"],elf=exe,expected_native=n,streams=actual["stdout_and_stderr"]))
    timer=subprocess.run([os.sys.executable,"-IB",str(full/"test_timer.py"),str(s),str(q)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    calibration=json.loads(timer.stdout);check(len(calibration["six_independent_timer_probes"])==6 and calibration["contributes_scored_samples"]==0,"timing FD controls")
    data=dict(measured_samples=0,wrong_durable_writes_three_errno=rejected,unprivileged=True,receiver_absent=True,
              inherited_writable_non_durable_fds=outer,source_spool_target_devices=[s.stat().st_dev,q.stat().st_dev,p.target.stat().st_dev],
              blocking_timer=digest(full/"measure.py"),compiler=rust.strip(),cargo=cargo.strip(),actual=rows,timer_probes=calibration)
    driver,=list((p.sdk/"lib").glob("librustc_driver-*.so"))
    wild=p.sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    data["local_sdk_files"]={k:[v.stat().st_size,digest(v)] for k,v in
        {"rustc":p.sdk/"bin/rustc","driver":driver,"cargo":p.sdk/"bin/cargo","wild":wild}.items()}
    check(len(set(data["source_spool_target_devices"]))==3,"receipt/work/measurement devices collapsed")
    (q/"io-result.json").write_bytes(canonical(data))

if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    for n in ("original","work","spool","target","backing","actual_home_testdir","scratch","sdk","proxies"):
        a.add_argument(n,type=Path)
    a.add_argument("receiver_device")
    run(a.parse_args())

"""Count the compilers and linkers executed by real, unwrapped Ohm Cargo on Ruff."""
import ast
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback

D = Path(os.environ["OHM_REPLAY_VIEW"])
M = D / "mount"
label, arm, mode, cargo_sha = sys.argv[1:]
O = D / "runs" / label
source = M / "source"
sdk = Path(os.environ["OHM_STUDY_SDK"])
donor = D / "donor"
ruff = "93526150df078af7dd8fc4226cdcc469539d2001"
version_rel = "crates/ruff_python_ast/src/python_version.rs"
edit = "ef23c9c39eb3029bab0139c3ea7ae6d95c4131e0"
rel = version_rel
root = "ruff_python_ast"
stock = sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "RUSTUP_HOME", "PATH")}
env.update(CARGO_HOME=str(M/"cargo-home"), CARGO_TARGET_DIR=str(M/"products"),
           CARGO_NET_OFFLINE="true", CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never", CARGO_TERM_COLOR="never",
           TMPDIR=str(M/"tmp"), RUSTUP_AUTO_INSTALL="0", TZ="UTC", LC_ALL="C.UTF-8")
assert "CARGO_BUILD_BUILD_DIR" not in env
config = M/"cargo-home"/"config.toml"
assert not config.exists() and not (config.parent/"config").exists()
config.write_text('[build]\nbuild-dir = ' + json.dumps(str(M/"shared")) + '\n')


def sha(bytestr):
    return hashlib.sha256(bytestr).hexdigest()
def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
def save(name, value):
    with (O/name).open("x") as out:
        json.dump(value, out, indent=2, sort_keys=True); out.write("\n")
def zipfile(name, data):
    (O/name).write_bytes(gzip.compress(data, compresslevel=3, mtime=0))
def git(*args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", donor, *args])
def mount_for(path):
    fd = os.open(path,os.O_PATH|os.O_DIRECTORY)
    try:
        ident=next(row.split()[1] for row in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines() if row.startswith("mnt_id:"))
    finally:
        os.close(fd)
    raw=next(row for row in Path("/proc/self/mountinfo").read_text().splitlines() if row.split()[0]==ident)
    left,right=raw.split(" - ",1)
    return [ident, left.split()[2], left.split()[4], left.split()[5].split(","), right.split()[0]]
relay = D / "runs"
def storage():
    protected=(donor,sdk)
    rows={str(x):mount_for(x) for x in (*protected,M,O,relay)}
    for loc in protected:
        assert os.statvfs(loc).f_flag & os.ST_RDONLY and "ro" in rows[str(loc)][3]
    assert not (os.statvfs(M).f_flag & os.ST_RDONLY)
    assert not (os.statvfs(O).f_flag & os.ST_RDONLY)
    return rows
def available():
    storage()
    return [int(next(l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemAvailable:")))*1024,
            shutil.disk_usage(relay).free,shutil.disk_usage(M).free]
floors = [16*2**30, 2*2**30, 128*2**20]
def checked(cmd, name, cwd=source, rc=0):
    # Duration here is a watchdog only. Probes and tests are distinct from cargo records.
    log, err = M/(name+".out"), M/(name+".err")
    before = available()
    assert all(v>n for v,n in zip(before, floors)), before
    with log.open("xb") as sout, err.open("xb") as serr:
        p=subprocess.Popen(cmd, cwd=cwd, env=env, stdout=sout, stderr=serr, start_new_session=True)
        start=time.monotonic(); mins=before
        try:
            while p.poll() is None:
                vals=available(); mins=list(map(min,mins,vals))
                if not all(v>n for v,n in zip(vals,floors)) or time.monotonic()-start>420:
                    raise RuntimeError((name,"reserve or timeout",vals))
                time.sleep(0.4)
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGKILL);p.wait()
    data=log.read_bytes(); errors=err.read_bytes()
    zipfile(name+".stdout.gz",data);zipfile(name+".stderr.gz",errors)
    assert p.returncode==rc,(name,p.returncode,errors[-1800:])
    return data

def native(trace, name):
    # strace follows every fork/exec, and only successful physical compiler/linker entries count.
    compiles=[]; links=[]; streams={}
    for f in sorted(trace.glob("exec.*")):
        data=f.read_bytes()
        streams[f.name]=data.decode()
        for line in data.decode().splitlines():
            if not line.startswith("execve(") or not line.endswith(" = 0"):continue
            item=re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-f]+ /\* [^*]* \*/|NULL)\)\s+= 0',line)
            assert item,line[:250]
            exe=Path(ast.literal_eval(item[1])); argv=ast.literal_eval(item[2])
            if not exe.exists(): continue
            if exe.samefile(sdk/"bin/rustc") and "--crate-name" in argv and "--out-dir" in argv:
                compiles.append(dict(crate=argv[argv.index("--crate-name")+1],argv=argv,exe=str(exe)))
            if exe.samefile(stock): links.append(dict(exe=str(exe),argv=argv))
    zipfile(name+".exec.json.gz",json.dumps(streams).encode())
    return compiles,links

def cargo(name, kind, state):
    args=["test","--lib","--no-run"] if kind=="test" else [kind]
    tr=M/(name+".trace");tr.mkdir()
    raw=checked(["strace","-ff","-qq","-s","131072","-e","trace=execve","-o",str(tr/"exec"),"cargo","+ohm",*args,"--locked","--offline","-p",root,"-j","4","--message-format=json"],name)
    rows=[json.loads(line) for line in raw.splitlines()]
    assert rows[-1]=={"reason":"build-finished","success":True}
    arts=[row for row in rows if row["reason"]=="compiler-artifact"]; assert sum(row["target"]["name"]==root for row in arts)==1
    pkg=next(row for row in arts if row["target"]["name"]==root)
    compiles, links=native(tr,name)
    all_files=[Path(path) for row in arts for path in row["filenames"]]
    for f in all_files: assert f.is_file(),f
    marker_names=set()
    for base in (M/"shared", M/"products"):
        for f in base.rglob("*.d"):
            if f.is_file() and b"ohm-untracked-relink-inputs" in f.read_bytes():
                marker_names.add(f.name)
    report=dict(state=state,mode=kind,typed=sorted((row["target"]["name"],row["target"]["kind"],row["target"]["crate_types"],row["features"],row["fresh"]) for row in arts),
                rustc=[x["crate"] for x in compiles],wild=len(links), checked=[x["crate"] for x in compiles if "-Zohm-check-relink-inputs" in x["argv"]],
                dirty=sorted(row["target"]["name"] for row in arts if not row["fresh"]), depinfo_marked=sorted(marker_names),
                root={x:digest(x) for x in pkg["filenames"]},compact=[{"file":x,"sha256":digest(x)} for row in arts if row["target"]["name"]=="compact_str" for x in row["filenames"]])
    save(name+".json",report)
    return dict(pkg=pkg,all=all_files,commands=compiles,record=report)

def verdict(tag,phase,state):
    p=phase["pkg"]
    assert mode == "build"
    rlib,=[Path(x) for x in p["filenames"] if x.endswith(".rlib")]
    libs={str(f.parent) for f in phase["all"]}
    for c in phase["commands"]:
        for i,arg in enumerate(c["argv"][:-1]):
            if arg=="-L" and c["argv"][i+1].startswith("dependency="): libs.add(c["argv"][i+1][11:])
            if arg=="--extern" and "=" in c["argv"][i+1]:libs.add(str(Path(c["argv"][i+1].split("=",1)[1]).parent))
    # The external reader consumes the actual root .rlib emitted by Cargo.
    for dirs in (M/"shared", M/"products"):
        libs.update(str(f.parent) for pat in ("*.rlib","*.so") for f in dirs.rglob(pat))
    reader=M/"reader.rs"
    reader.write_text("use ruff_python_ast::PythonVersion as V; fn main(){ println!(\"{} {} {}\", V::latest(), V::latest_ty(), V::default()); }\n")
    exe=M/"reader"
    checked(["rustc","+ohm","--edition=2024",reader,"--extern",f"ruff_python_ast={rlib}",*sum((["-L","dependency="+s] for s in sorted(libs)),[]),"-o",exe],tag+"-reader-compile")
    out=checked([exe],tag+"-reader-run").decode().strip()
    want={"new":"3.15 3.15 3.11","old":"3.14 3.14 3.10"}[state]
    assert out==want,(tag,out,want)
    elf_hash = digest(exe)
    bodies = O.parent/"consumer-elves"
    bodies.mkdir(exist_ok=True)
    retained = bodies/elf_hash
    if not retained.exists():
        with exe.open("rb") as src, retained.open("xb") as dst:
            shutil.copyfileobj(src,dst)
        retained.chmod(0o400)
    assert digest(retained) == elf_hash and retained.read_bytes() == exe.read_bytes()
    record=dict(elf=elf_hash,bytes=retained.stat().st_size,verdict=out)
    save(tag+"-verdict.json",record)
    return record

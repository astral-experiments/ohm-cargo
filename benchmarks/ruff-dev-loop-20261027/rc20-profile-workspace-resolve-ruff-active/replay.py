"""Replay the registered active Ruff profile edit using two isolated Linux mount namespaces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import runpy
import shutil
import subprocess as sp
import sys

HERE = Path(__file__).resolve().parent
native = type("Native", (), runpy.run_path(str(HERE/"native_execs.py")))
PIN = "93526150df078af7dd8fc4226cdcc469539d2001"
HIST = "36cc91ffb72adde11f0c4dfb76330a07481f6153"
RUST = "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
ORIG = "893b5ff55f23fde170f5079766ebbe20937419a24296394a6dd0f326b8ccba88"
EDIT = "db64b4749750f397144a063138740d50c96a110ec0d2491c3cdd0ea14f518321"
LOCK = "c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
IMAGES = {
    "A": ("2fe90823d","967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9"),
    "B": ("97e5acfb7","80356b8237d3089d3360b6de5abfc64a17e4b8d3f0ec1fb64e09254418b5c5e5")
}


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(p, data):
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run_arm(arm, out):
    assert os.geteuid() == CONFIG["uid"] and "CapEff:\t0000000000000000" in Path("/proc/self/status").read_text()
    work = VIEW / "ws"
    mf = work / "Cargo.toml"
    src = work / "crates/ruff_text_size/src/lib.rs"
    lib = src.read_bytes()
    lock = work / "Cargo.lock"
    assert sha(mf) == ORIG and sha(lock) == LOCK
    assert sha(work / "crates/ruff_text_size/tests/serde.rs") == "46cd1f5bfd2f40374e3d5312f9d151b2cf7470ec866a3a309adb1999b7231d46"
    assert sp.check_output(["git","rev-parse","HEAD"],cwd=work).strip() == b"93526150df078af7dd8fc4226cdcc469539d2001"
    assert sha(SDK / "bin/rustc") == RUST and sha(SDK / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd") == WILD
    ref, cargo = IMAGES[arm]
    image = Path(CONFIG["control" if arm == "A" else "candidate"])
    assert sha(image) == cargo
    ru = VIEW / "ru/toolchains/ohm"
    (ru / "bin").mkdir(parents=True)
    (ru / "bin/cargo").symlink_to(image)
    for name in ("rustc","rustdoc"):
        (ru / "bin" / name).symlink_to(SDK / "bin" / name)
    (ru / "lib").symlink_to(SDK / "lib",target_is_directory=True)
    args = {"check":["check","-p","ruff_text_size"], "test":["test","-p","ruff_text_size","--features","serde","--test","serde","--no-run"]}
    env = dict(HOME=CONFIG["home"],USER=CONFIG["user"],PATH=CONFIG["proxies"] + ":/usr/bin:/bin",
               RUSTUP_HOME=str(VIEW/"ru"),RUSTUP_AUTO_INSTALL="0",CARGO_HOME=str(VIEW/"cargo-home"),
               LC_ALL="C.UTF-8",CARGO_NET_OFFLINE="true",CARGO_TERM_COLOR="never",CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",
               CARGO_LOG="cargo::ops::resolve=debug",GIT_OPTIONAL_LOCKS="0",TMPDIR=str(VIEW/"tmp"))
    (VIEW / "tmp").mkdir()
    cli = [str(Path(CONFIG["proxies"])/"cargo"),"+ohm"]
    assert b"2fe90823d8eadc95de56c2cde8d41e0082aac0eb" in sp.check_output(cli+["-Vv"],cwd=work,env=env)
    original = mf.read_bytes()
    hunk = (HERE/"active-dev.hunk").read_bytes()
    edited = original.replace(hunk,b"")
    assert original.count(hunk) == 1 and hashlib.sha256(edited).hexdigest() == EDIT
    results = {}

    def call(mode, label, *, hit=None, dirty=None, invalid=False):
        target = VIEW / (mode + "-target")
        build = VIEW / (mode + "-shared")
        curenv = dict(env,CARGO_TARGET_DIR=str(target),CARGO_BUILD_BUILD_DIR=str(build))
        assert shutil.disk_usage(VIEW).free > 350*2**20 and shutil.disk_usage(out).free > CONFIG["reserve_bytes"]
        d = out / (mode + "-" + label)
        d.mkdir()
        cmd = ["strace","-f","-qq","-s","131072","-e","trace=execve,execveat","-o",str(d/"exec"),*cli,*args[mode],"--locked","--offline","--message-format=json"]
        x = sp.run(cmd,cwd=work,env=curenv,capture_output=True,timeout=220)
        (d/"stdout").write_bytes(x.stdout)
        (d/"stderr").write_bytes(x.stderr)
        ev = native.native_execs((d/"exec").read_bytes())
        comps = sorted(e["crate"] for e in ev if native.is_compile(e))
        links = sorted(e["program"] for e in ev if native.is_link(e))
        assert all(v == "ld.bfd" for v in links)
        # A single cargo check can resolve more than once. A later hit must not hide an earlier full resolution.
        hits = x.stderr.count(b"reusing the cached workspace resolution")
        full = x.stderr.count(b"resolve_with_registry:resolve_with_previous:register_patch_entries:")
        cached = hits > 0 and full == 0
        assert full > 0 or hits > 0, (mode, label, x.stderr[-1500:])
        arts = [json.loads(line) for line in x.stdout.splitlines()]
        emitted = [a for a in arts if a["reason"] == "compiler-artifact"]
        errors = [a["message"] for a in arts if a["reason"] == "compiler-message" and a["message"]["level"] == "error"]
        row = dict(exit=x.returncode,manifest=sha(mf),lib=sha(src),lock=sha(lock),hit=cached,full_workspace_resolutions=full,cache_hits=hits,compiles=comps,
                   links=links,events=ev,artifacts=sorted([a["target"]["name"],a["fresh"]] for a in emitted),
                   products={str(Path(f).relative_to(VIEW)):sha(Path(f)) for a in emitted for f in a["filenames"]},
                   errors=[(d["code"]["code"],d["message"],d["spans"][0]["file_name"],d["spans"][0]["line_start"]) for d in errors if d.get("code")],
                   stdout=sha(d/"stdout"),stderr=sha(d/"stderr"),trace=sha(d/"exec"))
        save(d/"row.json",row)
        print(arm,mode,label,x.returncode,cached,len(comps),len(links),row["errors"],flush=True)
        assert sha(lock) == LOCK and x.returncode == (101 if invalid else 0), (mode,label,x.stderr[-2000:])
        assert (hit is None or hit == cached) and (dirty is None or bool(comps) == dirty), (mode,label,row)
        if invalid:
            assert [e[0] for e in row["errors"]] == ["E0308"] and comps == ["ruff_text_size"] and not links
        else:
            assert not errors and arts[-1] == {"reason":"build-finished","success":True}
            if dirty is False:
                assert all(a["fresh"] for a in emitted) and not links
            if mode == "test":
                a, = [a for a in emitted if a["target"]["name"]=="serde" and a.get("executable")]
                exe = Path(a["executable"])
                listing = sp.check_output([exe,"--list"],cwd=work,env=curenv).decode()
                test = sp.check_output([exe,"--test-threads=1"],cwd=work,env=curenv).decode()
                names = sorted(line[:-6] for line in listing.splitlines() if line.endswith(": test"))
                assert len(names) == 3 and all("test " + n + " ... ok" in test for n in names)
                row.update(exe=sha(exe),names=names,verdict="passed")
                (d/"test-list").write_text(listing)
                (d/"test-verdict").write_text(test)
                if dirty:
                    assert "serde" in comps and links
        save(d/"row.json",row)
        results[mode+"-"+label] = row
        return row

    for mode in args:
        call(mode,"01-original",hit=False,dirty=True)
        call(mode,"02-repeat",hit=True,dirty=False)
    mf.write_bytes(edited)
    for mode in args:
        call(mode,"03-reverse",hit=arm=="B",dirty=True)
        call(mode,"04-repeat",hit=True,dirty=False)
    assert results["test-03-reverse"]["exe"] != results["test-01-original"]["exe"]
    for mode in args:
        for key in ["-target","-shared"]:
            p=VIEW / (mode + key)
            assert p.is_dir() and not p.is_symlink()
            p.rename(VIEW / (mode+key+"-prior"))
        call(mode,"05-clean-edited",hit=False,dirty=True)
    assert results["test-03-reverse"]["exe"] == results["test-05-clean-edited"]["exe"]
    src.write_bytes(lib + b"\nconst OHM_PROFILE_ERROR_CONTROL: () = 17;\n")
    bad=call("check","06-invalid",hit=True,invalid=True)
    for role in ("check-target","check-shared"):
        (VIEW/role).rename(VIEW/(role+"-before-invalid-clean"))
    clean_bad=call("check","07-clean-invalid",hit=False,invalid=True)
    assert bad["errors"] == clean_bad["errors"]
    src.write_bytes(lib)
    mf.write_bytes(original)
    for mode in args:
        call(mode,"08-restored",hit=arm=="B",dirty=True)
        call(mode,"09-final",hit=True,dirty=False)
    assert results["test-08-restored"]["exe"] == results["test-01-original"]["exe"]
    assert sha(mf)==ORIG and sha(lock)==LOCK and src.read_bytes()==lib
    save(out/"terminal.json",{"arm":arm,"cargo":cargo,"rows":{k:sha(out/k/"row.json") for k in results}})

MOUNT = """set -euo pipefail
mount -t tmpfs -o "size=3G,mode=0700,uid=$6,gid=$7,exec,nosuid,nodev" tmpfs "$1"
for name in ws cargo-home; do
    install -d -m0700 -o"$6" -g"$7" "$1/$name" "$1/$name-upper" "$1/$name-work"
    if [ "$name" = ws ]; then lower="$2"; else lower="$3"; fi
    mount --bind "$lower" "$lower"
    mount -o remount,bind,ro "$lower"
    mount -t overlay overlay -o "lowerdir=$lower,upperdir=$1/$name-upper,workdir=$1/$name-work" "$1/$name"
    mount -o remount,rw,exec,nosuid,nodev "$1/$name"
done
exec setpriv --reuid="$6" --regid="$7" --init-groups --no-new-privs --inh-caps=-all \
  --ambient-caps=-all --bounding-set=-all -- env "HOME=$8" "USER=$9" "LOGNAME=$9" \
  python3 -IB "$4" guest "$5" "${10}" "${11}"
"""


def verified_source(checkout):
    def git(*args):
        return sp.check_output(["git","--no-optional-locks","-C",str(checkout),*args])
    assert git("rev-parse","HEAD").decode().strip()==PIN
    assert git("status","--porcelain","--untracked-files=no")==b""
    assert git("show","--format=","--unified=0",HIST,"--","Cargo.toml")==(HERE/"active-dev.patch").read_bytes()
    subject=json.loads((HERE/"subjects.json").read_text())
    for rel,entry in subject["ruff"]["files"].items():
        assert sha(checkout/rel)==entry["sha256"]
        assert git("rev-parse",PIN+":"+rel).decode().strip()==entry["git_blob"]
    print("authenticated Ruff source, lock, test and whole historical manifest patch",flush=True)


def run(args):
    paths={name:str(getattr(args,name).expanduser().resolve(strict=True)) for name in ("checkout","cargo_home","sdk","control","candidate","proxies")}
    uid=os.getuid()
    assert uid!=0 and os.getgid()!=0 and os.geteuid()==uid
    work=args.work.absolute()
    out=args.out.absolute()
    assert not work.exists() and not out.exists() and work.parent.exists() and out.parent.exists()
    assert not work.is_relative_to(out) and not out.is_relative_to(work)
    for candidate in (work,out):
        assert candidate==candidate.resolve() and all(not candidate.is_relative_to(x) for x in paths.values())
        assert shutil.disk_usage(candidate.parent).free>args.reserve_gib*(2**30)+16_000_000
    assert args.reserve_gib>=0 and not any(ch in str(work) for ch in ",:\\")
    assert not any(ch in x for x in (paths["checkout"],paths["cargo_home"]) for ch in ",:\\")
    verified_source(Path(paths["checkout"]))
    subjects=json.loads((HERE/"subjects.json").read_text())
    for name,values in subjects["released_18_runtime"].items():
        assert sha(Path(paths["sdk"])/name)==values["sha256"]
    for arm,k in (("A","control"),("B","candidate")):
        assert sha(Path(paths[k]))==IMAGES[arm][1]
    for binary in ("sudo","setpriv","unshare","strace","git","bash","mount"):
        assert shutil.which(binary),binary
    assert (Path(paths["proxies"])/"cargo").exists()
    uid_entry=pwd.getpwuid(uid)
    work.mkdir(mode=0o700)
    out.mkdir(mode=0o700)
    conf=dict(paths,uid=uid,gid=os.getgid(),user=uid_entry.pw_name,home=uid_entry.pw_dir,work=str(work),
              reserve_bytes=int(args.reserve_gib*2**30))
    cfg=out/"replay-inputs.json"
    save(cfg,conf)
    for arm in "AB":
        arm_out=out/arm
        arm_out.mkdir()
        cmd=["sudo","-n","unshare","--mount","--propagation","private","--","bash","-c",MOUNT,"replay",
             str(work),paths["checkout"],paths["cargo_home"],str(Path(__file__).resolve()),str(cfg),
             str(uid),str(os.getgid()),uid_entry.pw_dir,uid_entry.pw_name,arm,str(arm_out)]
        with (arm_out/"worker.stderr").open("xb") as error:
            sp.run(cmd,stderr=error,check=True)
        assert not list(work.iterdir())
        verified_source(Path(paths["checkout"]))
    terminals=[json.loads((out/arm/"terminal.json").read_text()) for arm in "AB"]
    assert list(terminals[0]["rows"])==list(terminals[1]["rows"])
    for name in terminals[0]["rows"]:
        a,b=[json.loads((out/arm/name/"row.json").read_text()) for arm in "AB"]
        for field in ("exit","lib","manifest","lock","compiles","links","errors","artifacts","exe","names","verdict"):
            assert a.get(field)==b.get(field),(name,field)
    save(out/"complete.json",dict(source=PIN,profile_edit=HIST,rustc=RUST,wild=WILD,arms=terminals,scope="native correctness"))
    print("32 Cargo checks/test builds, 14 harness runs, recovery and both edited clean binaries verified")


if __name__=="__main__":
    if sys.argv[1:2]==["guest"]:
        CONFIG=json.loads(Path(sys.argv[2]).read_text())
        SDK=Path(CONFIG["sdk"])
        VIEW=Path(CONFIG["work"])
        run_arm(sys.argv[3],Path(sys.argv[4]))
    elif sys.argv[1:2]==["--check-source"] and len(sys.argv)==3:
        verified_source(Path(sys.argv[2]).resolve(strict=True))
    else:
        parser=argparse.ArgumentParser(description=__doc__)
        for field in ("checkout","sdk","control","candidate","cargo-home","work","out"):
            parser.add_argument("--"+field,type=Path,required=True)
        parser.add_argument("--proxies",type=Path,default=Path.home()/".cargo/bin")
        parser.add_argument("--reserve-gib",type=float,default=0,help="minimum free GiB to retain on the report filesystem")
        run(parser.parse_args())

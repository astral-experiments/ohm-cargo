#!/usr/bin/env python3
"""Collect genuine Cargo-issued Rust processes on an independent x86-64 Linux host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
sys.path.insert(0, str(HERE))
from counts import actual_ir
ROOT = "ruff_python_ast"
WILD = Path("lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")
S = json.loads((DATA / "sources.json").read_bytes())

def require(ok, detail):
    if not ok:
        raise RuntimeError(detail)

def digest(p):
    with Path(p).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def read(f):
    return json.loads(Path(f).read_bytes())

def save(f, data):
    with Path(f).open("x") as out:
        json.dump(data, out, indent=2, sort_keys=True)
        out.write("\n")

def free_memory():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable unavailable")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("work",type=Path,help="a new private directory, with at least 6 GiB free")
    p.add_argument("--checkout",type=Path,required=True,help="clean Ruff git checkout at the recorded snapshot and with the edit commit")
    p.add_argument("--registry",type=Path,required=True,help="authenticated CARGO_HOME/registry with the locked cache and index")
    p.add_argument("--parent-sdk",type=Path,required=True)
    p.add_argument("--candidate-sdk",type=Path,required=True)
    p.add_argument("--parent-product",type=Path,help="compiler build receipt for an independent rebuild")
    p.add_argument("--candidate-product",type=Path,help="compiler build receipt for an independent rebuild")
    p.add_argument("--cargo",type=Path,required=True,help="Ohm Cargo with its defaults compiled in")
    p.add_argument("--rustup",type=Path,required=True,help="the rustup executable used to provide private +ohm proxies")
    p.add_argument("--cpus",type=str,required=True,help="four available CPU numbers separated by commas")
    p.add_argument("--allow-rebuilt",action="store_true",help="require source and SDK product manifests, and verify a new source-stamped Cargo")
    p.add_argument("--limit",choices=("admission","pair","full"),default="pair",
                   help="four ordinary gates, gates plus the first chronological pair, or all 48")
    opt=p.parse_args()
    require(sys.platform.startswith("linux") and os.uname().machine=="x86_64","requires Linux x86-64")
    require(not sys.flags.optimize,"run without -O")
    for program in ("bwrap","cc","strace","git"):
        require(shutil.which(program),f"missing {program}")
    require(Path("/usr/bin/valgrind.bin").is_file(),"install native Valgrind and Callgrind at /usr/bin/valgrind.bin")
    cpus=sorted(set(int(n) for n in opt.cpus.split(",")))
    require(len(cpus)==4 and set(cpus)<=os.sched_getaffinity(0),"four allowed physical CPUs")
    os.sched_setaffinity(0,cpus)
    work=opt.work.absolute()
    require(not work.exists(),"work directory must be new")
    require(shutil.disk_usage(work.parent).free>6*2**30 and free_memory()>18*2**30,"initial disk/RAM reserve")
    work.mkdir(mode=0o700)
    for d in ("view","runs","failed"): (work/d).mkdir(mode=0o700)
    view=work/"view"
    src=opt.checkout.resolve(strict=True); reg=opt.registry.resolve(strict=True)
    kit={"P":opt.parent_sdk.resolve(strict=True),"Q":opt.candidate_sdk.resolve(strict=True)}
    proxy=opt.rustup.resolve(strict=True); cargo=opt.cargo.resolve(strict=True)
    require(all((reg/n).is_dir() for n in ("index","cache")),"offline registry")
    def git(*args):
        return subprocess.check_output(["git","--no-optional-locks","-C",src,*args])
    require(git("rev-parse","HEAD").decode().strip()==S["ruff"] and digest(src/"Cargo.lock")==S["lockfile"],"Ruff or lockfile")
    require(not git("status","--porcelain","--untracked-files=no"),"dirty Ruff checkout")
    path="crates/ruff_python_ast/src/python_version.rs"
    require(git("show",S["edit"]+":"+path)==(src/path).read_bytes() and git("show",S["edit"]+"^:"+path)!=(src/path).read_bytes(),"historical hunk")
    role_drivers={}; tools={}
    for arm in "PQ":
        driver,=kit[arm].glob("lib/librustc_driver*.so")
        role_drivers[arm]=digest(driver)
        tools[arm]={"driver":role_drivers[arm],"rustc":digest(kit[arm]/"bin/rustc"),"wild":digest(kit[arm]/WILD)}
        require(tools[arm]["wild"]==S["wild_sha256"],"stock Wild")
    require(tools["P"]["rustc"]==tools["Q"]["rustc"] and role_drivers["P"]!=role_drivers["Q"],"matched frontends and distinct drivers")
    cargo_sha=digest(cargo)
    if opt.allow_rebuilt:
        manifests={"P":opt.parent_product,"Q":opt.candidate_product}
        entries={}
        for a,fn in manifests.items():
            require(fn is not None,"--allow-rebuilt needs both physical SDK build receipts")
            man=read(fn)
            require(man["commit"]==S["roles"][a] and not man["pgo"] and not man["bolt"] and not man["wild_built"],"source-attested optimized stage1")
            entries[a]=man["files"]
            require(len(entries[a])==55,"55 compiler/stdlib files")
            for name,f in entries[a].items():
                require(not Path(name).is_absolute() and ".." not in Path(name).parts,"relative SDK member")
                actual=kit[a]/name
                require(digest(actual)==f["sha256"] and actual.stat().st_size==f["bytes"],name)
        require({n:v for n,v in entries["P"].items() if not n.startswith("lib/librustc_driver")}
                =={n:v for n,v in entries["Q"].items() if not n.startswith("lib/librustc_driver")},"matched physical runtime")
        if cargo_sha!=S["cargo_sha256"]:
            require(S["cargo_source"] in subprocess.check_output([cargo,"-Vv"]).decode(),"source-stamped rebuilt Cargo")
    else:
        require(cargo_sha==S["cargo_sha256"] and role_drivers==S["driver_sha256"],"recorded physical compilers/Cargo; use --allow-rebuilt for new source attestations")
    save(work/"tools.json",{"roles":S["roles"],"physical":tools,"cargo":cargo_sha,"cpus":cpus,"source":S["ruff"]})
    tracer=work/"trace"
    subprocess.run(["cc","-O2","-o",tracer,HERE/"trace.c"],check=True)
    common=[("RUSTUP_HOME",str(view/"rustup")),("HOME",str(view/"home")),("USER","replay"),("LOGNAME","replay"),
            ("PATH",str(view/"bin")+":/usr/local/bin:/usr/bin:/bin"),("OHM_REPLAY_VIEW",str(view)),
            ("OHM_STUDY_SDK",str(view/"rustup/toolchains/ohm")),("OHM_REPLAY_CPUSET",",".join(map(str,cpus))),
            ("OHM_REPLAY_TRACE_SHA",digest(tracer))]
    def slot(label,arm):
        require(free_memory()>18*2**30 and shutil.disk_usage(work).free>6*2**30,"pre-slot RAM/disk reserve")
        result=work/"runs"/label; result.mkdir(mode=0o700)
        state=Path(tempfile.mkdtemp(prefix="replay-",dir=work))
        try:
            for name in ("mount/products","mount/shared","mount/tmp","mount/cargo-home/registry/cache",
                         "mount/cargo-home/registry/index","bin","home","rustup/toolchains/ohm","donor","runs"):
                (state/name).mkdir(parents=True,exist_ok=True)
            for n in ("cargo","rustc"):
                (state/"bin"/n).symlink_to(proxy)
            (state/"trace").touch()
            subprocess.run(["git","clone","--quiet","--shared","--no-checkout",src,state/"mount/source"],check=True)
            subprocess.run(["git","-C",state/"mount/source","checkout","--quiet","--detach",S["ruff"]],check=True)
            observed=state/"source-product.json"
            save(observed,{"commit":S["roles"][arm],"driver":role_drivers[arm]})
            b=["bwrap","--die-with-parent","--ro-bind","/","/","--dev-bind","/dev","/dev","--proc","/proc",
               "--bind",state,view,"--bind",work/"runs",view/"runs","--ro-bind",src,view/"donor",
               "--ro-bind",kit[arm],view/"rustup/toolchains/ohm","--ro-bind",cargo,view/"rustup/toolchains/ohm/bin/cargo",
               "--ro-bind",tracer,view/"trace"]
            for n in ("cache","index"):
                b.extend(["--ro-bind",reg/n,view/"mount/cargo-home/registry"/n])
            b.append("--clearenv")
            for k,v in common: b.extend(["--setenv",k,v])
            b.extend(["--","/usr/bin/python3","-IB",HERE/"collect.py",label,arm,"build",cargo_sha])
            with (result/"launcher.stdout").open("xb") as out,(result/"launcher.stderr").open("xb") as err:
                run=subprocess.run(b,stdout=out,stderr=err)
            (result/"launcher.exit").write_text(str(run.returncode)+"\n")
            require(run.returncode==0,(label,(result/"launcher.stderr").read_text()[-1800:]))
            terminal=read(result/"terminal.json")
            require(terminal["matched"] and terminal["consumer"]["native"][1]==terminal["clean"],"clean reader")
        except BaseException:
            state.rename(work/"failed"/label); raise
        shutil.rmtree(state)
        return result
    admissions={}
    for direction in ("forward","reverse"):
        agreed=None
        for a in "PQ":
            f=slot("admission-"+direction+"-"+a.lower(),a)
            t=read(f/"terminal.json"); before,after=t["consumer"]["native"]
            row={"argv":read(f/"actual-dirty-argv.json"),"old":before,"changed":after}
            require(agreed is None or row==agreed,"literal native cross-arm enrollment")
            agreed=row
            for tag,counts in (("native-initial",(39,39,8)),("native-edit",(39,1,0)),("native-warm",(39,0,0)),
                               ("native-edited-unchanged",(39,0,0)),("independent-changed",(39,39,8))):
                physical=read(f/(tag+".json"))
                require((len(physical["typed"]),len(physical["rustc"]),physical["wild"])==counts,tag)
        admissions[direction]=agreed
    save(work/"runs/native-admission.json",{"directions":admissions})
    schedule=read(DATA/"schedule.json")
    limit={"admission":0,"pair":2,"full":48}[opt.limit]
    replay_rows=[]
    for name,direction,a,number in schedule[:limit]:
        f=slot(name,a); gold=admissions[direction]
        terminal=read(f/"terminal.json")
        require(terminal["consumer"]["native"]==terminal["consumer"]["profile"]==[gold["old"],gold["changed"]]
                and read(f/"actual-dirty-argv.json")==gold["argv"],"independent native/profile/clean")
        ir=actual_ir(f)
        replay_rows.append([name,direction,a,number,ir])
        print(name,ir,flush=True)
    save(work/"new-observations.json",replay_rows)
    if limit==48:
        import importlib.util
        module=importlib.util.spec_from_file_location("endpoint",DATA/"verify.py")
        verify=importlib.util.module_from_spec(module); module.loader.exec_module(verify)
        estimates={}
        for direction in ("forward","reverse"):
            pairs=[]
            for i in range(1,13):
                block=[row for row in replay_rows if row[1]==direction and row[3]==i]
                counts={row[2]:row[4] for row in block}
                pairs.append((block[0][2],counts["P"],counts["Q"]))
            estimates[direction]=verify.endpoint(pairs)
        save(work/"new-endpoints.json",estimates)
    print("qualified native admissions",len(admissions)*2,"new full compiler profiles",len(replay_rows))

if __name__=="__main__":
    main()

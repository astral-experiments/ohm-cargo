"""Build two authenticated Ohm Cargo source trees with the same normal Ohm SDK and display stamp."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess as sp

PARENT="2fe90823d8eadc95de56c2cde8d41e0082aac0eb"
DIRECT_PARENT="9d675d9393b5ff1ecebe764d1a554f8fd64175ef"
CANDIDATE="97e5acfb7b8eefde1ce07d703fc4849d6d36e37c"
WILD="lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"


def check(value,message):
    if not value: raise RuntimeError(str(message))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")


def git(checkout,*argv):
    return sp.check_output(["git","--no-optional-locks","-C",str(checkout),*argv])


def sources(checkout):
    check(git(checkout,"rev-parse",CANDIDATE+"^").decode().strip()==DIRECT_PARENT,"unexpected candidate parent")
    check(git(checkout,"diff","--name-only",PARENT,DIRECT_PARENT).splitlines()==[b"tests/testsuite/freshness.rs"],"production base disagreement")
    check(git(checkout,"diff","--name-only",DIRECT_PARENT,CANDIDATE).splitlines()==[b"src/ops/resolve_cache.rs",b"tests/testsuite/workspaces.rs"],"unexpected candidate delta")
    return git(checkout,"show","-s","--format=%H%n%h%n%cs","--abbrev=9",PARENT)


def extract(checkout,rev,dest,stamp):
    dest.mkdir()
    listing=git(checkout,"ls-tree","-rz",rev)
    records={}
    for entry in listing.rstrip(b"\0").split(b"\0"):
        meta,name=entry.split(b"\t",1)
        mode,kind,blob=meta.decode().split()
        check(kind=="blob" and mode in ("100644","100755","120000"),"unsupported Git entry")
        records[os.fsdecode(name)]=(mode,blob)
    # tar extractors can normalize the literal spelling of symlink targets.
    # Read the exact blob for each Git-stored path and verify the written bytes.
    with sp.Popen(["git","-C",str(checkout),"cat-file","--batch"],stdin=sp.PIPE,stdout=sp.PIPE) as child:
        for name,(mode,blob) in records.items():
            rel = Path(name)
            check(not rel.is_absolute() and ".." not in rel.parts, "invalid Git path")
            child.stdin.write(blob.encode()+b"\n")
            child.stdin.flush()
            key,kind,length = child.stdout.readline().split()
            check((key.decode(),kind)==(blob,b"blob"), "wrong Git object")
            data=child.stdout.read(int(length))
            check(len(data)==int(length) and child.stdout.read(1)==b"\n", "truncated Git object")
            p = dest/rel
            p.parent.mkdir(parents=True,exist_ok=True)
            if mode=="120000":
                target = os.fsdecode(data)
                check(not os.path.isabs(target) and (p.parent/target).resolve().is_relative_to(dest.resolve()), "external source link")
                p.symlink_to(target)
                actual = os.fsencode(os.readlink(p))
            else:
                p.write_bytes(data)
                p.chmod(0o755 if mode=="100755" else 0o644)
                actual = p.read_bytes()
            git_id=hashlib.sha1(b"blob "+str(len(actual)).encode()+b"\0"+actual).hexdigest()
            check(git_id==blob and p.is_symlink()==(mode=="120000"), name)
            if not p.is_symlink():
                check(bool(p.stat().st_mode & 0o111)==(mode=="100755"),name)
        child.stdin.close()
        check(child.wait()==0,"Git object reader failed")
    actual_paths={f.relative_to(dest).as_posix() for f in dest.rglob("*") if f.is_symlink() or not f.is_dir()}
    check(actual_paths==records.keys(),"incomplete source export")
    check(not (dest/".git").exists() and "git-commit-info" not in records,"unexpected Git metadata")
    (dest/"git-commit-info").write_bytes(stamp)
    return {"commit":rev,"tree":git(checkout,"rev-parse",rev+"^{tree}").decode().strip(),"files":len(records),
            "git_tree_listing_sha256":hashlib.sha256(listing).hexdigest(),"cargo_lock":digest(dest/"Cargo.lock"),
            "stamp":stamp.decode().splitlines()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cargo-checkout",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path,help="new build directory, independent of the source clone")
    p.add_argument("--prepare-only",action="store_true",help="verify both exact source exports without invoking Cargo")
    p.add_argument("--reserve-gib",type=int,default=8)
    p.add_argument("--jobs",type=int,default=4)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--proxies",type=Path,default=Path.home()/".cargo/bin")
    args=p.parse_args()
    out=args.out.absolute(); checkout=args.cargo_checkout.resolve(strict=True)
    check(not out.exists() and out.parent.resolve()==out.parent and not out.is_relative_to(checkout),"new build directory outside the clone required")
    check(args.reserve_gib>=0 and args.jobs>=1,"invalid resource limits")
    budget=args.reserve_gib*2**30
    check(shutil.disk_usage(out.parent).free>budget+(128*2**20 if args.prepare_only else 8*2**30),"insufficient initial disk reserve")
    stamp=sources(checkout)
    out.mkdir(mode=0o700)
    env={k:os.environ[k] for k in ("HOME","USER","LOGNAME","RUSTUP_HOME","CARGO_HOME","SSL_CERT_FILE","SSL_CERT_DIR") if k in os.environ}
    env.update(PATH=str(args.proxies.resolve())+":"+os.defpath,LC_ALL="C.UTF-8",RUSTUP_AUTO_INSTALL="0",CFG_RELEASE_CHANNEL="dev",
               CARGO_INCREMENTAL="0",CARGO_PROFILE_RELEASE_INCREMENTAL="false",CARGO_TERM_COLOR="never",
               CARGO_TARGET_DIR=str(out/"current/target"),CARGO_BUILD_BUILD_DIR=str(out/"current/shared"))
    cargo=str(args.proxies.resolve()/"cargo")
    compiler=[str(args.proxies.resolve()/"rustc"),"+ohm"]
    cmd=[cargo,"+ohm","-Zohm-defaults=no","build","--locked","--release","-p","cargo","--bin","cargo","--features","ohm-defaults","--jobs",str(args.jobs),"--message-format=json"]
    if args.offline:cmd.append("--offline")
    sdk=Path(sp.check_output(compiler+["--print","sysroot"],env=env,text=True).strip()).resolve(strict=True)
    enrolled={"kind":"public Git source build, standard release profile","qualified_pgo_reconstruction":False,"arms":{},
              "common_build_args":cmd[1:],"compiler_version":sp.check_output(compiler+["-Vv"],env=env,text=True),
              "sdk_rustc_sha256":digest(sdk/"bin/rustc"),"sdk_wild_sha256":digest(sdk/WILD)}
    for arm,rev in (("A",PARENT),("B",CANDIDATE)):
        current=out/"current";current.mkdir()
        src=current/"source"
        desc=extract(checkout,rev,src,stamp)
        enrolled["arms"][arm]=desc
        save(current/"source.json",desc)
        if not args.prepare_only:
            check(shutil.disk_usage(out).free>budget+4*2**30,"reserve before native build")
            with (current/"stdout.jsonl").open("xb") as stdout,(current/"stderr").open("xb") as stderr:
                result=sp.run(cmd,cwd=src,env=env,stdout=stdout,stderr=stderr)
            check(result.returncode==0,"Cargo build failed; see retained current/stderr")
            records=[json.loads(line) for line in (current/"stdout.jsonl").read_bytes().splitlines()]
            files=[Path(e["executable"]) for e in records if e.get("reason")=="compiler-artifact" and e["target"]["name"]=="cargo" and e.get("executable") and e["target"]["kind"]==["bin"]]
            check(len(files)==1 and files[0].resolve().is_relative_to(current.resolve()),"unexpected Cargo product")
            shutil.copy2(files[0],current/"cargo")
            desc.update(binary_sha256=digest(current/"cargo"),version=sp.check_output([str(current/"cargo"),"-Vv"],text=True))
            check("commit-hash: "+PARENT+"\n" in desc["version"],"source tarball stamp was not used")
        current.rename(out/arm)
    a,b=enrolled["arms"].values()
    check(a["cargo_lock"]==b["cargo_lock"],"different dependency locks")
    if not args.prepare_only:
        check(a["version"]==b["version"] and a["binary_sha256"]!=b["binary_sha256"],"unmatched or identical Cargo images")
        enrolled.update(baseline=PARENT,source=CANDIDATE,baseline_binary=a["binary_sha256"],cargo_sha256=b["binary_sha256"])
    save(out/("sources.json" if args.prepare_only else "build-receipt.json"),enrolled)
    print(out)


if __name__=="__main__": main()

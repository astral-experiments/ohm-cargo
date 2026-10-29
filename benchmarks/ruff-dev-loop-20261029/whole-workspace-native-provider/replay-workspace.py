#!/usr/bin/env python3
"""Replay the fifty real native providers in a fresh Cargo store using a local Ohm SDK."""
import argparse
import ast
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

BASE="93526150df078af7dd8fc4226cdcc469539d2001"
CASES=("inlay_hints::default_inlay_hints","notebook::hover_past_end_of_cell","notebook::inlay_hints_range_past_end_of_cell")
FORCED=("ty_server/test/e2e","ruff_python_parser/test/generate_inline_tests","ty_python_semantic/lib/ty_python_semantic")

def h(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ruff",type=Path,required=True);ap.add_argument("--registry",type=Path,required=True,help="Cargo registry/ with offline index and cache")
    ap.add_argument("--work",type=Path,required=True,help="new directory on one private filesystem, preferably 48 GiB available")
    ap.add_argument("--min-free-gib",type=int,default=8,help="reserve beneath which a new Cargo call is refused");args=ap.parse_args()
    root=Path(__file__).resolve().parent;dst=args.work.absolute();registry=args.registry.resolve(strict=True);src=args.ruff.resolve(strict=True)
    if dst.exists() or os.uname().machine!="x86_64":raise SystemExit("requires x86_64 Linux and a new work directory")
    assert subprocess.check_output(["git","--no-optional-locks","-C",src,"rev-parse","HEAD"],text=True).strip()==BASE
    assert not subprocess.check_output(["git","--no-optional-locks","-C",src,"status","--porcelain","--untracked-files=no"])
    assert h(src/"Cargo.lock")=="c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
    if args.min_free_gib<=0 or shutil.disk_usage(dst.parent).free < (14+args.min_free_gib)*2**30:
        raise SystemExit("allow at least 14 GiB for new working data in addition to the reserve")
    dst.mkdir(mode=0o700);tar=dst/"target";shr=dst/"shared";ch=dst/"cargo-home";(ch/"registry").mkdir(parents=True)
    shutil.copytree(registry/"index",ch/"registry/index",symlinks=True);(ch/"registry/cache").symlink_to(registry/"cache",target_is_directory=True);tar.mkdir();shr.mkdir()
    tmp=dst/"tmp";tmp.mkdir()
    env={k:os.environ[k] for k in ("PATH","HOME","RUSTUP_HOME") if k in os.environ}
    env.update(CARGO_TARGET_DIR=str(tar),CARGO_BUILD_BUILD_DIR=str(shr),CARGO_HOME=str(ch),CARGO_NET_OFFLINE="true",TMPDIR=str(tmp),LC_ALL="C",INSTA_UPDATE="no")
    rustc=Path(subprocess.check_output(["rustup","which","--toolchain","ohm","rustc"],env=env,text=True).strip());cargo=Path(subprocess.check_output(["rustup","which","--toolchain","ohm","cargo"],env=env,text=True).strip())
    wild=rustc.parent.parent/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd";assert wild.is_file()
    gccscript=Path(subprocess.check_output(["cc","-print-file-name=libgcc_s.so"],env=env,text=True).strip()).resolve(strict=True);sys_before=h(gccscript)
    obj=dst/"provider.o";subprocess.run(["cc","-c",root/"provider.s","-o",obj],env=env,check=True)
    if any(c in str(p) for c in ' \n\t()"' for p in (obj,gccscript)):raise SystemExit("choose simple private filenames for GNU INPUT")
    good=("INPUT ( "+str(obj)+" "+str(gccscript)+" )\n").encode();bad=b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT (\n"
    fixed=set(json.loads(gzip.decompress((root/"observations.json.gz").read_bytes()))["baseline"]);assert len(fixed)==50
    program={};manifest={};baseline={};inventory={};seen={};pkgcache={};slot=None
    ordinary=["cargo","+ohm","test","--workspace","--no-run","--locked","--offline","-j4","--message-format=json"]
    def visit(label,mode,forced=False):
        nonlocal slot
        if shutil.disk_usage(dst).free <= args.min_free_gib*2**30:raise SystemExit("private reserve reached")
        stage=dst/label;stage.mkdir()
        if slot is not None:
            assert slot.parent.is_dir() and (slot.is_relative_to(tar) or slot.is_relative_to(shr))
            if os.path.lexists(slot):
                assert slot.is_file() and not slot.is_symlink() and slot.read_bytes() in (good,bad);slot.unlink()
            if mode!="absent":
                with slot.open("xb") as f:f.write(good if mode=="valid" else bad);f.flush();os.fsync(f.fileno())
        if forced:
            for i,name in enumerate(FORCED):
                p=program[name];assert p.is_file() and not p.is_symlink() and (p.is_relative_to(tar) or p.is_relative_to(shr))
                prior=h(p);save=stage/("preserved-"+str(i));p.rename(save);assert not p.exists() and h(save)==prior
        with (stage/"stdout").open("xb") as out,(stage/"stderr").open("xb") as err:
            code=subprocess.run(["strace","-ff","-qq","-s","524288","-e","trace=execve,execveat","-o",stage/"exec",*ordinary],cwd=src,env=env,stdout=out,stderr=err).returncode
        rows=[json.loads(l) for l in (stage/"stdout").read_bytes().splitlines()]
        assert rows[-1]=={"reason":"build-finished","success":code==0}
        links={};real=0
        for f in stage.glob("exec.*"):
            pending=None
            for line in f.read_text().splitlines():
                if line.endswith("<unfinished ...>"):assert pending is None;pending=line[:line.rfind("<unfinished ...>")];continue
                if line.startswith("<... "):assert pending is not None;line=pending+line.partition(" resumed>")[2];pending=None
                if not line.startswith("execve(") or not re.search(r"=\s*0$",line):continue
                m=re.match(r'execve\(("(?:\\.|[^"\\])*"), (\[.*\]), (?:0x[0-9A-Fa-f]+|NULL|\[.*\])',line);assert m
                p=Path(ast.literal_eval(m[1]));p=p if p.is_absolute() else src/p
                if p.is_file() and p.samefile(wild):
                    av=ast.literal_eval(m[2]);real+=1;assert "-o" in av;links[Path(av[av.index("-o")+1])]=av
            assert pending is None
        if mode=="bad":
            assert code==101 and real and b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in (stage/"stdout").read_bytes()+(stage/"stderr").read_bytes()
            result={"cargo":code,"real_wild":real,"selected_launched":sorted(k for k,p in program.items() if p in links)}
        else:
            assert code==0
            for a in rows:
                if a["reason"]!="compiler-artifact" or not a["executable"] or not a["profile"]["test"]:continue
                m=Path(a["manifest_path"]);pkg=pkgcache.get(m)
                if pkg is None:pkg=pkgcache[m]=tomllib.loads(m.read_text())["package"]["name"]
                k="/".join([pkg,a["target"]["kind"][0],a["target"]["name"]])
                if k in fixed:
                    exe=Path(a["executable"]);assert k not in program or program[k]==exe;program[k]=exe;manifest[k]=m
            assert set(program)==fixed
            cand=set()
            for k,p in program.items():
                assert p in links,(label,k)
                av=links[p];ix,=[i for i,v in enumerate(av) if v.startswith("-L") and "psm" in Path(v[2:]).parts and Path(v[2:]).name=="out"];assert ix<av.index("-lgcc_s");cand.add(Path(av[ix][2:]))
            assert len(cand)==1;search,=cand;assert search.is_relative_to(tar) or search.is_relative_to(shr)
            if slot is None:slot=search/"libgcc_s.so";assert not os.path.lexists(slot)
            else:assert slot.parent==search
            result={"cargo":code,"real_wild":real,"selected":{}}
            for k,p in sorted(program.items()):
                e={**env,"CARGO_MANIFEST_DIR":str(manifest[k].parent),"CARGO_MANIFEST_PATH":str(manifest[k])}
                q=subprocess.run([p,"--list"],cwd=manifest[k].parent,env=e,capture_output=True);bs=h(p);ls=hashlib.sha256(q.stdout).hexdigest()
                if mode=="valid":
                    assert q.returncode==83 and not q.stdout and not q.stderr and bs!=baseline[k]
                else:
                    assert q.returncode==0
                    if label=="00-empty":baseline[k]=bs;inventory[k]=ls
                    assert ls==inventory[k]
                    if k=="ty_server/test/e2e":
                        assert bs==baseline[k] and sum(v.endswith(b": test") for v in q.stdout.splitlines())==200
                        for case in CASES:
                            rr=subprocess.run([p,"--exact",case],cwd=manifest[k].parent,env=e,capture_output=True);assert rr.returncode==0 and ("test "+case+" ... ok").encode() in rr.stdout.splitlines()
                result["selected"][k]=[q.returncode,bs,ls]
        (stage/"result.json").write_text(json.dumps(result,sort_keys=True)+"\n");seen[label]=result;print(label,code,real,flush=True)
    for label,m,force in (("00-empty","absent",False),("01-unchanged","absent",False),("02-unchanged","absent",False),("10-valid","valid",False),("11-valid-repeat","valid",False),("12-forced-valid","valid",True),("13-malformed","bad",False),("14-remove","absent",False),("15-forced-malformed","bad",True),("16-final-remove","absent",False)):visit(label,m,force)
    assert not os.path.lexists(slot) and sys_before==h(gccscript)
    (dst/"terminal.json").write_text(json.dumps({"cargo":h(cargo),"rustc":h(rustc),"wild":h(wild),"source":BASE,"observations":seen},sort_keys=True)+"\n")
if __name__=="__main__":main()

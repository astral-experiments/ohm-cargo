"""Project actual Cargo streams and kernel launches, preserving the raw checksums."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy

HERE = Path(__file__).resolve().parent
NATIVE = runpy.run_path(str(HERE / "native_execs.py"))
CANONICAL = re.compile(r"(/target/debug/build/workspaces/)([a-f0-9]{16}/v2-[a-f0-9]{16})(/profile_probe/)")
DEBUG = re.compile(r"^\s*\d+\.\d+s DEBUG (?:[a-z_]+:)* ?cargo::ops::resolve: .*\n$")
CLOCK = re.compile(r"^(    Finished `dev` profile \[unoptimized\] target\(s\) in )\d+(?:\.\d+)?s\n$")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def raw_index(root):
    result={}
    for f in sorted(root.rglob("*")):
        if f.is_dir():
            continue
        check(f.is_file() and not f.is_symlink(),f.name)
        b=f.read_bytes()
        result[f.relative_to(root).as_posix()]={"bytes":len(b),"sha256":sha(b)}
    return result


def check(condition, message):
    if not condition:
        raise ValueError(str(message))


def emit(path, val):
    b = (json.dumps(val,indent=2,sort_keys=True)+"\n").encode()
    path.write_bytes(gzip.compress(b,mtime=0) if path.suffix==".gz" else b)


def user_diagnostics(stderr):
    """Keep complete user-facing bytes including line endings. Isolate only registered debug and clock text."""
    lines=stderr.splitlines(keepends=True)
    return "".join(CLOCK.sub(r"\1<elapsed>\n", line) for line in lines if not DEBUG.fullmatch(line))


def capture(root, sdk, full):
    terminal=json.loads((root/"complete.json").read_bytes())
    target=[r["manifest_path"] for r in map(json.loads,(root/"A/01-seed/stdout").read_bytes().splitlines())
            if r.get("reason")=="compiler-artifact"][0]
    arena=str(Path(target).parents[1])
    stock=(sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd").resolve(strict=True)
    expected_wild="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    check(sha(stock.read_bytes())==expected_wild,"stock linker")
    sample={"terminal":terminal,"terminal_sha256":sha((root/"complete.json").read_bytes()),"arms":{}, "snapshots":full}
    if full:
        objects={}
        for obj in (root/"elf").iterdir():
            b=obj.read_bytes()
            check(sha(b)==obj.name and b[:4]==b"\x7fELF" and int.from_bytes(b[18:20],"little")==62,"native ELF")
            objects[obj.name]=len(b)
        sample["physically_rehashed_elf_bytes"]=objects
    for arm in "AB":
        visits={}
        for folder in sorted((root/arm).iterdir()):
            tag=folder.name
            raw={n:(folder/n).read_bytes() for n in ("row.json","exec","stdout","stderr")}
            row=json.loads(raw["row.json"])
            for key,n in (("stdout","stdout"),("stderr","stderr"),("trace","exec")):
                check(row[key]==sha(raw[n]),(tag,key))
            stdout=raw["stdout"].decode().replace(arena,"<arena>")
            stderr=raw["stderr"].decode().replace(arena,"<arena>")
            check(user_diagnostics(stderr)==user_diagnostics(row["diagnostic"].replace(arena,"<arena>")+"\n"),
                  (tag,"original unlogged diagnostic"))
            native=NATIVE["native_execs"](raw["exec"])
            trace=raw["exec"].decode().splitlines()
            for idx,e in enumerate(native):
                start=e["lines"][0]-1
                matched=re.search(r'execve(?:at)?\((?:[^,]+, )?("(?:[^"\\]|\\.)*"),',trace[start])
                check(matched is not None,(tag,"kernel program path",start))
                program=Path(ast.literal_eval(matched[1]))
                e["raw_program_path_sha256"]=sha(str(program).encode())
                if e["program"]=="cargo":
                    check((idx==0 and e["cargo_args"][:1]==["+ohm"]) or
                          (idx==1 and program==Path(arena)/"ru/toolchains/ohm/bin/cargo"),"ordinary Cargo route")
                elif e["program"]=="rustc":
                    check(program==Path(arena)/"ru/toolchains/ohm/bin/rustc","compiler route")
                elif NATIVE["is_link"](e):
                    check(program.resolve(strict=True)==stock,"physical stock Wild route")
                    e["linker_sha256"]=expected_wild
            public={k:v for k,v in row.items() if k!="diagnostic"}
            public.update(raw_row_sha256=sha(raw["row.json"]),stdout_text=stdout,stderr_text=stderr,
                          public_stdout_sha256=sha(stdout.encode()),public_stderr_sha256=sha(stderr.encode()),
                          user_diagnostic=user_diagnostics(stderr),native=native)
            if full:
                for field,file in (("manifest","Cargo.toml"),("lock","Cargo.lock"),("marker","marker")):
                    b=(folder/file).read_bytes()
                    if field=="marker":check(b.decode()==row[field],(tag,field))
                    else: check(sha(b)==row[field],(tag,field))
                    public[field+"_bytes"]=b.decode()
                if row["exit"]==0:
                    b=(folder/"runtime.stdout").read_bytes()
                    check(b.decode()==row["output"]+"\n" and row["elf"] in objects,(tag,"native caller"))
                    public["runtime_stdout_sha256"]=sha(b)
                else:check(not (folder/"runtime.stdout").exists(),(tag,"runtime on failed Cargo"))
            visits[tag]=public
        sample["arms"][arm]=visits
    return sample


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ("original","replay","sdk","out"):
        parser.add_argument("--"+n,required=True,type=Path)
    a=parser.parse_args()
    emit(a.out,{"original":capture(a.original,a.sdk,False),"replay":capture(a.replay,a.sdk,True)})
    emit(a.out.with_name("raw-file-index.json.gz"),{"original":raw_index(a.original),"replay":raw_index(a.replay)})

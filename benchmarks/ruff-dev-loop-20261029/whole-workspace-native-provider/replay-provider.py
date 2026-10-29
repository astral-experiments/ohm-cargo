#!/usr/bin/env python3
"""Build and run the exact x86_64 constructor, both as an executable input and through dlopen."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

def h(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--wild",type=Path,required=True);p.add_argument("--work",type=Path,required=True)
    args=p.parse_args();w=args.work.absolute();wild=args.wild.resolve(strict=True)
    if w.exists() or os.uname().machine!="x86_64":raise SystemExit("requires x86_64 Linux and a new work directory")
    w.mkdir(mode=0o700);lddir=w/"bin";lddir.mkdir();(lddir/"ld.bfd").symlink_to(wild);search=w/"private-search";search.mkdir()
    sysgcc=Path(os.fsdecode(subprocess.check_output(["cc","-print-file-name=libgcc_s.so"])).strip()).resolve(strict=True)
    if any(ch in str(p) for ch in '\n\t ()"' for p in (w,sysgcc)):raise SystemExit("please choose plain directory names for GNU INPUT syntax")
    system_hash=h(sysgcc);src=Path(__file__).resolve().with_name("provider.s");obj=w/"provider.o";subprocess.run(["cc","-c",src,"-o",obj],check=True)
    (w/"main.c").write_text("int main(void){return 0;}\n")
    (w/"library.c").write_text("int ohm_answer(void){return 17;}\n")
    (w/"loader.c").write_text('#include <dlfcn.h>\nint main(int n,char **v){if(n!=2)return 31;void *p=dlopen(v[1],RTLD_NOW|RTLD_LOCAL);if(!p)return 32;int (*f)(void)=dlsym(p,"ohm_answer");if(!f||f()!=17)return 33;return dlclose(p)!=0;}\n')
    scope=["cc","-B"+str(lddir),"-fuse-ld=bfd","-Wl,--build-id=sha1"]
    def native(label,rest):
        q=w/label;q.mkdir();log=q/"exec"
        child=subprocess.run(["strace","-ff","-qq","-s","65536","-e","trace=execve,exit_group","-o",log,*scope,*rest],cwd=w,capture_output=True)
        (q/"stdout").write_bytes(child.stdout);(q/"stderr").write_bytes(child.stderr);real=0
        for f in q.glob("exec.*"):
            for line in f.read_text().splitlines():
                if line.startswith("execve(") and re.search(r"=\s*0$",line):
                    m=re.match(r'execve\(("(?:\\.|[^"\\])*")',line);assert m
                    n=Path(ast.literal_eval(m[1]));n=n if n.is_absolute() else w/n
                    if n.is_file() and n.samefile(wild):real+=1
        assert real==1,(label,real)
        return child
    loader=w/"loader";assert native("loader-link",[w/"loader.c","-ldl","-o",loader]).returncode==0
    result={};slot=search/"libgcc_s.so";original={};valid=("INPUT ( "+str(obj)+" "+str(sysgcc)+" )\n").encode();bad=b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT (\n"
    for mode,contents in (("baseline",None),("higher",valid),("malformed",bad),("restored",None)):
        if slot.exists():
            assert not slot.is_symlink() and slot.read_bytes() in (valid,bad);slot.unlink()
        if contents is not None:
            with slot.open("xb") as f:f.write(contents)
        result[mode]={}
        for kind in ("exe","shared"):
            dst=w/("subject" if kind=="exe" else "subject.so")
            argv=([w/"main.c"] if kind=="exe" else ["-shared","-fPIC",w/"library.c"])+["-L"+str(search),"-Wl,--no-as-needed","-lgcc_s","-o",dst]
            r=native(mode+"-"+kind,argv)
            if mode=="malformed":
                assert r.returncode!=0 and b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in r.stderr
                result[mode][kind]={"link":r.returncode,"runtime":None}
            else:
                assert r.returncode==0;call=subprocess.run([dst] if kind=="exe" else [loader,dst],cwd=w,capture_output=True)
                assert call.returncode==(83 if mode=="higher" else 0)
                result[mode][kind]={"link":0,"runtime":call.returncode,"elf":h(dst)}
                if mode=="baseline":original[kind]=h(dst)
                if mode=="restored":assert original[kind]==h(dst)
    assert not slot.exists() and h(sysgcc)==system_hash
    report={"source":h(src),"wild":h(wild),"gcc_script":system_hash,"operations":result}
    (w/"result.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n");print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

SOURCE = Path(__file__).resolve().parent
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bitflags", type=Path, required=True, help="unmodified bitflags 2.13.2 source directory")
    ap.add_argument("--work", type=Path, required=True)
    args = ap.parse_args()
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SOURCE / "fixtures", root / "fixtures")
    shutil.copytree(args.bitflags / "src", root / "bitflags/src")
    for name in ("spec.md", "README.md", "CHANGELOG.md"):
        shutil.copyfile(args.bitflags / name, root / "bitflags" / name)
    raw = root / "bitflags/src/public.rs"
    assert digest(raw) == "1237676ca4687d8eb8364eb52b23c5f284f73f4d4113ee833fa3470c8b512be9"
    orig = raw.read_bytes()
    proc = root / "fixtures/producer.rs"
    proc_bytes = proc.read_bytes()
    events = []
    def call(argv):
        p = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        events.append(dict(argv=argv, stdout=p.stdout, stderr=p.stderr, status=p.returncode))
        (root/"commands.json").write_text(json.dumps(events, indent=2)+"\n")
        if p.returncode:
            raise RuntimeError(f"{argv}: {p.stderr}")
        return p.stdout.strip()
    def rust(*argv):
        args = ["rustc", "+ohm", "--edition=2021", "-Cdebuginfo=0"]
        if os.environ.get("OHM_HOLDOUT_SYSROOT"):
            args.extend(["--sysroot",os.environ["OHM_HOLDOUT_SYSROOT"]])
        return call([*args,*argv])
    call(["rustc","+ohm","-vV"])
    rust("--crate-type=proc-macro","--crate-name","probe","fixtures/probe.rs","-o","libprobe.so")
    def library(lib, src):
        rust("--crate-type=rlib","--crate-name",lib,src,"-o",f"lib{lib}.rlib")
    def program(crate, lib, filename):
        rust("--crate-name",crate,f"fixtures/{filename}.rs","--extern","probe=libprobe.so","--extern",f"{lib}=lib{lib}.rlib","-o",crate)
        return call(["./"+crate]).splitlines()
    bitflags = {}
    literal=b"$vis struct $PublicBitFlags(<$PublicBitFlags as $crate::__private::PublicFlags>::Internal);"
    assert orig.count(literal) == 1
    phases = {"base": orig, "prefix_line": b"// source line inserted\n"+orig, "interior_space": orig.replace(literal,literal.replace(b"::Internal",b"::   Internal")), "same_byte_coordinates_new_line":orig.replace(b"        "+literal,b"\n       "+literal), "restore":orig}
    for name, source in phases.items():
        raw.write_bytes(source)
        library("bitflags","bitflags/src/lib.rs")
        lines = program("actual","bitflags","actual")
        assert len(lines) == 3
        s = source.index(literal.split(b"(<")[0])+len(literal.split(b"(<")[0])+1
        e = source.index(b"Internal);",s)
        def pos(idx):
            return f"{source[:idx].count(bytes([10]))+1}:{idx-source.rfind(bytes([10]),0,idx)}"
        def show(start,end):
            return f"bitflags/src/public.rs:{pos(start)}-{pos(end)}"
        expected=[show(s,s+1),show(e,e+8),show(s,e+8)]
        assert lines == expected, (lines,expected)
        bitflags[name] = {"lines":lines, "file_sha256":digest(raw), "s":s, "e":e}
    a, b = bitflags["base"], bitflags["same_byte_coordinates_new_line"]
    assert (a["s"], a["e"]) == (b["s"], b["e"]) and a["lines"] != b["lines"]
    toy = {}
    for name, source in {"base":proc_bytes,"prefix_line":b"// prepended\n"+proc_bytes,"interior_space":proc_bytes.replace(b"first last",b"first    last"),"restore":proc_bytes}.items():
        proc.write_bytes(source)
        library("origin","fixtures/producer.rs")
        lines = program("consumer","origin","consumer")
        assert len(lines)==2 and lines[1]=="different-files"
        assert "fixtures/producer.rs:" in lines[0]
        toy[name] = lines
    assert toy["restore"]==toy["base"] and len({tuple(v) for k,v in toy.items() if k!="restore"})==3
    assert raw.read_bytes() == orig
    actual_source = root / "fixtures/actual.rs"
    saved = actual_source.read_bytes()
    altered = saved + b"// change the preceding local source allocation\n"
    abs_table = {}
    for mode in ("relative", "absolute"):
        if mode == "absolute":
            rust("--cfg","measure_absolute","--crate-type=proc-macro","--crate-name","probe","fixtures/probe.rs","-o","libprobe.so")
        rows = {}
        for name, text in (("before", saved), ("after", altered), ("restore", saved)):
            actual_source.write_bytes(text)
            rows[name] = program("actual","bitflags","actual")
        assert rows["restore"] == rows["before"]
        if mode == "relative":
            assert rows["before"] == rows["after"] == bitflags["base"]["lines"]
        else:
            assert rows["after"] != rows["before"]
            for a,b in zip(rows["before"],rows["after"]):
                assert a.split(" ",1)[0] == b.split(" ",1)[0]
                lo, hi = map(int,re.search(r"bytes\((\d+)\.\.(\d+)\)", a).groups())
                newlo, newhi = map(int,re.search(r"bytes\((\d+)\.\.(\d+)\)", b).groups())
                assert (newlo-lo, newhi-hi) == (len(altered)-len(saved),)*2
        abs_table[mode] = rows
    out = {"bitflags":bitflags,"fixture":toy,"preceding_local_source":abs_table,"compile_and_reader_commands":len(events)}
    (root/"summary.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__ == "__main__":
    main()

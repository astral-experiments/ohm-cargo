#!/usr/bin/env python3
"""Replay the Linux x86_64 source and native-provider controls in a new local directory."""
import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BASE = "93526150df078af7dd8fc4226cdcc469539d2001"
HIST = "1b9310471b7d1178633e58ee63808522609db887"
SOURCE = "crates/ty_server/tests/e2e/inlay_hints.rs"
INPUTS = {"original": "a025b90170c496d6336023fa8857c4d2cb2ef77c2e601bf119e9feb3c1a71624", "edited": "24d443ea2c65e5879884b32e761fea2d5e0f3cd198fd0ea9a44bd27e52078fad", "invalid": "b0c839216b204903f687d177f8669b6e3601683217cfd460c4ff112916296d57"}
CASES = ["inlay_hints::default_inlay_hints", "notebook::hover_past_end_of_cell", "notebook::inlay_hints_range_past_end_of_cell"]
ASM = """.text
.type ohm_native_provider_exit_83,@function
ohm_native_provider_exit_83:
 mov $231,%eax
 mov $83,%edi
 syscall
 ud2
.size ohm_native_provider_exit_83,.-ohm_native_provider_exit_83
.section .preinit_array,"aw",@preinit_array
 .quad ohm_native_provider_exit_83
.section .note.GNU-stack,"",@progbits
"""
def digest(p):
    h = sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)
def tools_for(w):
    driver = os.fsdecode(subprocess.check_output(["rustup", "which", "--toolchain", "ohm", "rustc"])).strip()
    cargo = os.fsdecode(subprocess.check_output(["rustup", "which", "--toolchain", "ohm", "cargo"])).strip()
    sdk = Path(driver).parent.parent
    wild = sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    for name, tool in [("cargo", cargo), ("rustc", driver), ("wild", wild)]:
        assert Path(tool).is_file()
        (w / (name + ".sha256")).write_text(digest(tool) + "\n")
    for name in ("cargo", "rustc"):
        (w / (name + ".version")).write_bytes(subprocess.check_output([name, "+ohm", "-Vv"]))
    return wild
def true_execs(d):
    for f in sorted((d / "trace").glob("exec.*")):
        pending = {}
        for line in f.read_text().splitlines():
            if line.endswith("<unfinished ...>"):
                op = line.split("(", 1)[0]
                assert op not in pending
                pending[op] = line.removesuffix("<unfinished ...>")
                continue
            m = re.match(r"^<\.\.\. (\w+) resumed>", line)
            if m:
                line = pending.pop(m[1]) + line[m.end():]
            if line.startswith(("execve(", "execveat(")) and line.endswith("= 0"):
                m = re.fullmatch(r'execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x\w+|NULL|\[.*\])(?: /\*.*?\*/)?\)\s*= 0', line)
                if not m:
                    raise ValueError("Unrecognized successful exec: " + line[:120])
                yield Path(ast.literal_eval(m[1])), ast.literal_eval(m[2])
        assert not pending
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ruff", type=Path, required=True, help="Existing Git clone containing both Ruff revisions")
    ap.add_argument("--registry", type=Path, required=True, help="Cargo registry directory containing offline index and cache")
    ap.add_argument("--work", type=Path, required=True, help="New, absent, private directory on a filesystem with at least 9 GiB available")
    args = ap.parse_args()
    w = args.work.resolve()
    assert os.uname().machine == "x86_64" and os.uname().sysname == "Linux"
    assert not w.exists() and w.parent.is_dir() and shutil.disk_usage(w.parent).free >= 9*2**30
    assert not any(c.isspace() for c in str(w)), "Use a path without spaces for the GNU INPUT script"
    w.mkdir(mode=0o700)
    wild = tools_for(w)
    src = w/"ruff"
    run(["git","clone","--shared","--no-checkout",args.ruff.resolve(),src])
    run(["git","-C",src,"checkout","--detach",BASE])
    assert digest(src/"Cargo.lock")=="c9e345325bec5ff08dbbe3916edd39ad0c3d1c7797a8c241ae32f62754e764bf"
    target, shared, ch = (w/n for n in ("target","shared","cargo-home"))
    rustup = Path(os.environ.get("RUSTUP_HOME",Path.home()/".rustup")).resolve()
    proxy = Path(shutil.which("rustup")).absolute().parent
    tmp = w/"tmp";tmp.mkdir()
    home = w/"home";home.mkdir()
    env = {"PATH":str(proxy)+":/usr/local/bin:/usr/bin:/bin","HOME":str(home),"CARGO_HOME":str(ch),"RUSTUP_HOME":str(rustup),"CARGO_TARGET_DIR":str(target),"CARGO_BUILD_BUILD_DIR":str(shared),"CARGO_NET_OFFLINE":"true","RUSTUP_AUTO_INSTALL":"0","TMPDIR":str(tmp),"INSTA_UPDATE":"no","LC_ALL":"C","LANG":"C"}
    reg=args.registry.resolve()
    def empty():
        target.mkdir();shared.mkdir();(ch/"registry").mkdir(parents=True)
        shutil.copytree(reg/"index",ch/"registry/index",symlinks=True)
        (ch/"registry/cache").symlink_to(reg/"cache",target_is_directory=True)
        assert not list(target.iterdir()) and not list(shared.iterdir()) and not (ch/"registry/src").exists()
    empty()
    source=src/SOURCE
    data={"original":source.read_bytes()}
    patch=subprocess.check_output(["git","-C",src,"diff",HIST+"^",HIST,"--",SOURCE])
    run(["git","-C",src,"apply","--reverse","--", "-"],input=patch)
    data["edited"]=source.read_bytes()
    lines=data["edited"].splitlines(keepends=True);lines.insert(21,b"    let _ohm_invalid: &str = 0usize;\n")
    data["invalid"]=b"".join(lines)
    assert {k:sha256(v).hexdigest() for k,v in data.items()}==INPUTS
    state={};slot=None;selected=None
    def visit(label,mode,native="absent",force=False,cold=False):
        nonlocal slot,selected
        if source.read_bytes()!=data[mode]:source.write_bytes(data[mode])
        if force:
            assert selected.is_file() and not selected.is_symlink() and selected.is_relative_to(target)
            shutil.copyfile(selected,w/(label+".incumbent"))
            selected.unlink()
        d=w/label;d.mkdir();(d/"trace").mkdir()
        ordinary=["cargo","+ohm","test","--locked","--offline","--no-run","-j4","-p","ty_server","--test","e2e","--message-format=json"]
        with (d/"stdout").open("xb") as so,(d/"stderr").open("xb") as se:
            p=subprocess.run(["strace","-ff","-qq","-s","524288","-e","trace=execve,execveat,exit_group","-o",d/"trace/exec",*ordinary],cwd=src,env=env,stdout=so,stderr=se)
        rows=[json.loads(l) for l in (d/"stdout").read_bytes().splitlines()]
        ok=mode!="invalid" and native!="malformed"
        assert p.returncode==(0 if ok else 101) and rows[-1]=={"reason":"build-finished","success":ok}
        arts=[x for x in rows if x["reason"]=="compiler-artifact"]
        exe=None
        if ok:
            r,=[r for r in arts if r["target"]["kind"]==["test"] and r["target"]["name"]=="e2e" and r["manifest_path"]==str(src/"crates/ty_server/Cargo.toml")]
            exe=Path(r["executable"]);assert len(arts)==300 and exe.is_file() and exe.is_relative_to(target)
            selected=exe
        jobs=[a for p,a in true_execs(d) if p.is_file() and p.samefile(wild)]
        relevant=[a for a in jobs if "-o" in a and selected is not None and Path(a[a.index("-o")+1])==selected]
        if cold:
            assert not any(r["fresh"] for r in arts) and len(relevant)==1
        if ok and native=="absent":
            result=run([exe,"--list"],env=env,cwd=src/"crates/ty_server",stdout=subprocess.PIPE).stdout
            (d/"listing").write_bytes(result);assert sum(x.endswith(b": test") for x in result.splitlines())==200
            supplied={**env,"CARGO_MANIFEST_DIR":str(src/"crates/ty_server"),"CARGO_MANIFEST_PATH":str(src/"crates/ty_server/Cargo.toml")}
            for ix,case in enumerate(CASES):
                raw=run([exe,"--exact",case],env=supplied,cwd=src/"crates/ty_server",stdout=subprocess.PIPE).stdout
                (d/("case-"+str(ix))).write_bytes(raw)
                assert ("test "+case+" ... ok").encode() in raw.splitlines()
            if slot is None:
                a,=relevant
                positions=[(i,Path(v[2:])) for i,v in enumerate(a) if v.startswith("-L") and "psm" in Path(v[2:]).parts]
                (pos,psm),=positions
                assert pos<a.index("-lgcc_s") and psm.is_relative_to(target) and (psm/"libpsm_s.a").is_file()
                slot=psm/"libgcc_s.so";assert not os.path.lexists(slot)
        if native=="valid":
            r=subprocess.run([exe,"--list"],env=env,cwd=src/"crates/ty_server",capture_output=True)
            assert r.returncode==83 and not r.stdout and not r.stderr and len(relevant)==1
        if native=="malformed":
            assert b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT" in (d/"stdout").read_bytes()+(d/"stderr").read_bytes()
        if mode=="invalid":
            assert any((x.get("message",{}).get("code") or {}).get("code")=="E0308" and any(s["is_primary"] and s["line_start"]==22 for s in x["message"]["spans"]) for x in rows)
            assert not relevant
        state[label]={"cargo":p.returncode,"fresh":sum(x["fresh"] for x in arts),"typed":len(arts),"wild":len(jobs),"e2e_wild":len(relevant),"elf":digest(exe) if exe else None,"list":digest(d/"listing") if (d/"listing").is_file() else None}
        (d/"result.json").write_text(json.dumps(state[label],sort_keys=True)+"\n")
        print(label,state[label],flush=True)
    for label,mode in [("01-empty-original","original"),("02-unchanged","original"),("03-unchanged","original"),("04-edited","edited"),("05-edited-repeat","edited"),("06-invalid","invalid"),("07-recovery","edited"),("08-restored","original")]:
        visit(label,mode,cold=label.startswith("01"))
        if label=="04-edited":shutil.copyfile(selected,w/"warm-edited-elf")
    hook=w/"provider.o"
    run(["cc","-c","-x","assembler","-o",hook,"-"],input=ASM.encode())
    stock=Path(os.fsdecode(subprocess.check_output(["cc","-print-file-name=libgcc_s.so"])).strip()).absolute();assert stock.is_file()
    assert slot.is_relative_to(target) and not slot.exists() and not any(c.isspace() for c in str(stock))
    good=f"INPUT ( {hook} {stock} )\n".encode();bad=b"OHM_REJECT_BAD_WORKSPACE_TEST_LINK_SCRIPT (\n"
    for label,form,forced in [("09-higher","valid",False),("10-forced-higher","valid",True),("11-malformed","malformed",False),("12-remove","absent",False),("13-forced-malformed","malformed",True),("14-repair","absent",False)]:
        if os.path.lexists(slot):
            assert not slot.is_symlink() and slot.read_bytes() in (good,bad)
            slot.unlink()
        if form!="absent":
            with slot.open("xb") as f:f.write(good if form=="valid" else bad)
        visit(label,"original",form,forced)
    assert state["01-empty-original"]["elf"]==state["14-repair"]["elf"]
    assert state["09-higher"]["elf"]==state["10-forced-higher"]["elf"]
    for f in (target,shared,ch):f.rename(w/("preserved-warm-"+f.name))
    empty()
    visit("15-empty-edited","edited",cold=True)
    assert state["15-empty-edited"]["elf"]==state["04-edited"]["elf"]
    run(["cmp","--",selected,w/"warm-edited-elf"])
    assert (w/"15-empty-edited/listing").read_bytes()==(w/"04-edited/listing").read_bytes()
    (w/"terminal.json").write_text(json.dumps(state,indent=2,sort_keys=True)+"\n")
if __name__=="__main__": main()

"""Independently check the programs, linker operands, compiler modes and verdicts."""
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile

root = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
records = json.loads(gzip.decompress((root/"records.json.gz").read_bytes()))
with tarfile.open(root/"streams.tar.gz", "r:gz") as archive:
    assert all(m.isfile() and m.size < 4 * 1024**2 for m in archive)
    assert len(archive.getnames()) == len(set(archive.getnames()))
    streams = {n:archive.extractfile(n).read() for n in archive.getnames()}
seen = set()
totals = Counter()

def commands(trace):
    for line in trace.decode().splitlines():
        if "execve(" not in line or not re.search(r"\)\s+= 0$", line):
            continue
        m = re.search(r'execve\(("(?:[^"\\]|\\.)*"), \[', line)
        assert m, line
        image = ast.literal_eval(m[1])
        argv = ast.literal_eval("[" + line.split(", [", 1)[1].split("], ", 1)[0] + "]")
        yield image, argv

for series, group in records.items():
    implicit, fixed = series.startswith("implicit"), series.endswith("-fixed")
    source = group["source"]
    assert len(source)==4 and set(source)=={"Cargo.toml","app/Cargo.toml","app/src/lib.rs","app/tests/probe.rs"}
    assert "build" not in source["app/Cargo.toml"] and "[dependencies]" not in source["app/Cargo.toml"]
    if implicit:
        assert source["app/tests/probe.rs"]=='#[test]\nfn prints_choice() { println!("native-choice=17"); }\n'
        assert group["intact_host"]["sha256"]==sha((root/"system-linker-script.txt").read_bytes())
        assert group["archived_inputs"]["absent"]==group["intact_host"]["sha256"]
    else:
        assert '#[link(name = "ohm_rc20_native_choice_20261029"' in source["app/tests/probe.rs"]
        assert group["intact_host"]["sha256"] is None and group["private_mount"]["unique_name_absent"]
    assert len(set(group["archived_inputs"].values()))==3
    assert set(group["histories"])==({"on","off","empty29","empty-invalid","no-rust-edit"} |
                                      ({"emptyoff29","emptyoffbad"} if implicit else set()))
    for arm, history in group["histories"].items():
        off = arm in ("off","emptyoff29","emptyoffbad")
        assert history["defaults_off"] == off
        assert history["rustc"]=="fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
        want_image = ("99383612a7a0a2b58c60f8d94711e88e3f73f4fd584ff43ef8a6b04caa1fa8aa" if fixed else
                      "fcb1960fa700069b2cf9634526e2cc1a7d7aa0e68d00fc358075e6b7a8fd87d0" if implicit else
                      "00d75d89b28ac122fa18d41fbfd054e50fbef0e2a64ccb4786ea146cccc29b20")
        assert history["cargo"] == want_image
        phases=[r["phase"] for r in history["rows"]]
        assert phases == (["empty"] if arm.startswith("empty") else [
            "initial","settled","declared-valid","repeat-valid","declared-malformed","repeat-malformed","restored"])
        initial_hash = history["rows"][0].get("hash")
        for row in history["rows"]:
            phase,state=row["phase"],row["state"]
            values = {}
            for name,digest in row["normalized"].items():
                key=f"{series}/{arm}/{phase}/{name}"
                values[name]=streams[key]
                seen.add(key)
                assert sha(values[name])==digest and re.fullmatch("[0-9a-f]{64}",row["outputs"][name])
            code=1 if arm=="no-rust-edit" else row["lib"]
            for name,contents in source.items():
                data=contents.replace("1 + 1","1 + "+str(code)) if name=="app/src/lib.rs" else contents
                assert sha(data.encode())==row["sources"][name]
            cargo=[json.loads(line) for line in values["stdout"].splitlines() if line.startswith(b"{")]
            assert not any(j["reason"]=="build-script-executed" for j in cargo)
            assert {j["target"]["name"] for j in cargo if j["reason"]=="compiler-artifact"}<={"app","probe"}
            no_change = arm=="no-rust-edit" or (arm=="on" and not fixed)
            active_state = "absent" if no_change and phase!="empty" else state
            status = 101 if active_state=="malformed" else 0
            assert row["cargo"]==status
            finish=[j["success"] for j in cargo if j["reason"]=="build-finished"]
            assert finish == [status==0]
            if status:
                assert any(j["reason"]=="compiler-message" and "linking with" in j["message"]["message"] for j in cargo)
                totals["real link errors"]+=1
            else:
                text=values["native.stdout"]
                expected_native=83 if implicit and active_state=="valid" else 0
                expected_value=None if expected_native==83 else 29 if active_state=="valid" else 17
                assert (row["native_exit"],row["value"])==(expected_native,expected_value)
                assert ([int(x) for x in re.findall(rb"native-choice=(\d+)",text)]==
                        ([] if expected_value is None else [expected_value]))
                if no_change and phase!="empty":
                    assert row["hash"]==initial_hash
                totals["executed tests"]+=1
            jobs=list(commands(values["exec.log"]))
            probe=[argv for exe,argv in jobs if exe.endswith("/rustc") and "--crate-name" in argv and
                   argv[argv.index("--crate-name")+1]=="probe"]
            links=[(exe,argv) for exe,argv in jobs if Path(exe).name in ("ld.bfd","ld","rust-lld") and "-o" in argv and
                   Path(argv[argv.index("-o")+1]).name.startswith("probe-")]
            for exe,argv in links:
                assert ("wild-ld/ld.bfd" in exe)==(not off)
                assert "-lgcc_s" in argv
                if not implicit:
                    assert any("ohm_rc20_native_choice_20261029" in arg for arg in argv)
                assert any("/usr/lib" in arg for arg in argv if arg.startswith("-L"))
            critical = phase in ("declared-valid","declared-malformed")
            if critical and no_change:
                assert not links and not probe
            if critical and not no_change:
                assert len(links)==1 and probe
                if fixed and not off:
                    assert len(probe)==1 and ("link-only" in probe[0] or "-Zlink-only" in probe[0])
            if phase in ("settled","repeat-valid"):
                assert not links and not probe
            if (phase=="repeat-malformed" and status) or phase=="empty":
                assert links and probe
            totals["commands"]+=1
            totals["physical test links"]+=len(links)
assert set(streams)==seen and len(records)==4
print("Verified four independent toolchain/fixture cohorts,",dict(totals))

"""Export registered portable native reruns after completion, retaining per-exec digests without private arguments."""
from collections import Counter
import ast
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time

base=Path.home()/".cache/ohm-233-position-qualified-20261027"
src=base/"corrected-native-rerun-v2"
out=base/"corrected-toolchain-portable-rerun-v2"
rc=src/"queue.rc"
while not rc.exists():time.sleep(30)
assert rc.read_text().strip()=="0" and (out/"complete.json").is_file()
sha=lambda b:hashlib.sha256(b).hexdigest()
def successful_records(d):
    for f in sorted(d.glob("exec.*")):
        pending=None
        for line in f.read_bytes().splitlines():
            if line.startswith((b"execve(",b"execveat(")) and line.endswith(b"<unfinished ...>"):
                assert pending is None;pending=line.removesuffix(b"<unfinished ...>");continue
            m=re.match(rb"^<\.\.\. (execve(?:at)?) resumed>(.*)$",line)
            if m:
                assert pending is not None and pending.startswith(m[1]+b"(")
                line,pending=pending+m[2],None
            if not re.search(rb"\)\s+= 0$",line):continue
            assert not line.startswith(b"execveat(")
            if not line.startswith(b"execve("):continue
            m=re.match(rb'execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*(?:0x[\da-f]+|NULL)',line)
            assert m is not None
            name=Path(ast.literal_eval(m[1].decode())).name
            event={"trace":f.name,"image":name,"sha256":sha(line)}
            if name=="rustc":
                cp=re.search(rb'"--crate-name", "([A-Za-z0-9_]+)"',m[2])
                if cp and cp[1] not in (b"__",b"___"):
                    event.update(crate=cp[1].decode(),mode="link-only" if re.search(rb'"(?:-Z)?link-only"',m[2]) else "full")
            if name in {"ld","ld.bfd","ld.gold","ld.lld","rust-lld","wild","ld.wild","mold"}:
                assert m[1].endswith(b'/wild-ld/ld.bfd"')
                event["wild"]=True
            yield event
        assert pending is None

with (Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027")/"native-measure.lock").open("a") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    complete=json.loads((out/"complete.json").read_bytes())
    j={"complete":complete,"witnesses":{},"code_sha256":{f:sha((src/f).read_bytes()) for f in ("run.py","rerun-native-edit.py","replacement.json","SHA256SUMS")}}
    assert complete["source_clean"] and set(complete["outcomes"])=={f"{e}-{m}" for e in ("doc","parser") for m in ("build","test")}
    for k,summary in complete["outcomes"].items():
        d=out/k; r=json.loads((d/"stdout").read_bytes()); events=list(successful_records(d/"raw-exec"))
        assert r["edit_seconds"] is None and r["source_restored"] and r["fresh_units"]==summary["fresh_units"]
        assert sorted([ev["crate"],ev["mode"]] for ev in events if ev.get("crate"))==summary["rustcs"]
        assert sorted(ev["image"] for ev in events if ev.get("wild"))==summary["linkers"]
        assert any(ev["image"]=="cargo" for ev in events)
        j["witnesses"][k]={"execs":events,"helper_stdout_sha256":sha((d/"stdout").read_bytes()),"summary":{n:r[n] for n in ("edit","command","toolchain","source_restored","fresh_units","edit_seconds")}}
print(json.dumps(j,sort_keys=True,separators=(",",":")))

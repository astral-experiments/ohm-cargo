"""Independently reparse the unmodified process, decision, artifact and diagnostic channels."""
import ast
import hashlib
import json
from pathlib import Path
import re
import tarfile

HERE = Path(__file__).resolve().parent
SHA = lambda b: hashlib.sha256(b).hexdigest()
GATE = "7a6c8c588068b3f49f94dcf52f383c8f6562c811cf258059902d2243e860a72e"
STOCK = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
R2 = "22abce6921b46f93f387c7d3d99cefa4df9c0a866619447077699ef81a73827f"
PIN = {"h2-native.tgz":"c10ff02e9c0124b989c7d7510b1ec32bfd971e2a067941b842b0550cd62c33a7",
       "h2-faults.tgz":"c1c7862b6bab6a8b2e207e57e358fa34d5b59d09e0b685cac40b118d62d26f06"}
PRIVATE = re.compile(rb"openai[.](org|com|internal)|artifactory[.]|authorization[:][ ]bearer|github[_]pat[_]|ghp[_][A-Za-z0-9]{16}",re.I)
EXEC = re.compile(rb'^(\d+)\s+execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[^ ]+ )?/\* [0-9]+ vars \*/\)\s+= 0$')
SCOPE = {"cc","collect2","ld.bfd","ld.stock","check"}
NAMES = ["cold","training","same","refuse","wrong-nonce","diagnostic","untrained","provider","badprovider","restore"]
BASE_ARGV = ["+ohm","test","--no-run","-p","reader","--test","generate_inline_tests","--locked",
             "--offline","-j1","--message-format=json"]

def roster(raw):
    processes = []
    for line in raw.splitlines():
        m=EXEC.fullmatch(line)
        if m is None:
            continue
        executable=ast.literal_eval(m[2].decode())
        args=ast.literal_eval(m[3].decode())
        role=Path(executable).name
        unit=None
        if role=="rustc":
            if "--crate-name" not in args:
                continue
            unit=args[args.index("--crate-name")+1]
            if unit=="___":
                continue
            split={b for a,b in zip(args,args[1:]) if a=="-Z"}
            attached={a[2:] for a in args if a.startswith("-Z")}
            role="link-only" if "link-only" in split|attached else "full"
        elif role not in SCOPE:
            continue
        processes.append(dict(pid=int(m[1]),role=role,unit=unit,executable=executable,
                              argv=args,sha256=SHA(line)))
    return processes

def verify(archive):
    file=HERE/archive
    assert SHA(file.read_bytes())==PIN[archive]
    with tarfile.open(file) as tar:
        names=tar.getnames()
        assert len(set(names))==len(names) and all(m.isfile() for m in tar.getmembers())
        members={n:tar.extractfile(n).read() for n in names}
    ledger=json.loads(members["sha256.json"])
    assert set(ledger)==set(members)-{"sha256.json"}
    assert all(SHA(members[n])==h for n,h in ledger.items())
    assert all(not PRIVATE.search(b) for b in members.values())
    q=json.loads(members["reports/qualified.json"])
    assert q["pass"] and q["gate"]==GATE
    phases=NAMES if archive=="h2-native.tgz" else NAMES[:6]
    if len(phases)==10:
        assert q["driver"]==R2 and q["stock"]==STOCK
    seen={}
    lines=members["worker/v1.stdout"].decode().splitlines()
    assert [line.split()[0] for line in lines]==phases
    for name in phases:
        where="reports/"+name+"/"
        r=json.loads(members[where+"result.json"])
        assert r["commands"]==roster(members[where+"trace"])
        assert r["argv"][1:]==BASE_ARGV and r["architecture"]=="x86_64" and r["euid"]==1000
        msgs=[json.loads(l) for l in members[where+"stdout"].splitlines() if l]
        assert msgs[-1]=={"reason":"build-finished","success":name!="badprovider"}
        assert r["status"]==(101 if name=="badprovider" else 0)
        assert r["value"]==(None if name=="badprovider" else "native-value="+("83" if name=="provider" else "41"))
        roles=[p["role"] for p in r["commands"]]
        assert roles.count("cc")==roles.count("collect2")==roles.count("ld.bfd")
        assert roles.count("ld.stock")== (0 if name=="same" else 3 if name=="cold" else 1)
        for decision in r["decisions"]:
            raw=json.loads(members["decisions/"+decision["nonce"]+".json"])
            assert decision==raw and decision["workers"]==1
        if name not in ("cold","training"):
            assert len(r["decisions"])==1
            d=r["decisions"][0]
            shim=next(p for p in r["commands"] if p["role"]=="ld.bfd")
            assert d["pid"]==shim["pid"] and d["target"]==shim["argv"][shim["argv"].index("-o")+1]
            assert d["before"][2]&0o7777==0o775
        if name=="same":
            assert [(p["unit"],p["role"]) for p in r["commands"] if p["unit"]]==[
                ("leaf","full"),("generate_inline_tests","link-only")]
            assert roles.count("check")==1 and d["decision"]==d["reason"]=="fixture-native-fresh"
            assert d["training_sha256"]==SHA(members["decisions/training.json"])
            assert d["output_blake3"]==json.loads(members["decisions/training.json"])["output_blake3"]
            artifact=next(m for m in msgs if m["reason"]=="compiler-artifact" and m["target"]["name"]=="generate_inline_tests")
            assert not artifact["fresh"] and Path(artifact["executable"]).name==Path(d["target"]).name
        if name=="badprovider":
            assert b"libutil.a" in members[where+"stdout"] and b"parse error at line 1, column 9" in members[where+"stdout"]
        if name in ("provider","badprovider","untrained"):
            assert d["decision"]=="real-stock" and "link-only" in roles
        if name=="untrained":
            assert d["reason"]=="untrained-width" and "check" not in roles
        if archive=="h2-faults.tgz" and name in ("wrong-nonce","diagnostic"):
            assert d["checker_code"]==0 and d["reason"]=={"wrong-nonce":"invalid-response","diagnostic":"checker-refusal"}[name]
        seen[name]=r
    assert seen["training"]["exe_sha256"]==seen["same"]["exe_sha256"]
    if len(phases)==10:
        assert seen["provider"]["exe_sha256"]!=seen["same"]["exe_sha256"]
    return len(phases)

if __name__=="__main__":
    print("Reparsed",sum(verify(f) for f in PIN),"ordinary Cargo commands, including both ABI fault responses, the missing provider, the added provider, and the malformed linker script.")

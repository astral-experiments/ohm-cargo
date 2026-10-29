"""Project the retained Linux strace, Cargo JSON and file witnesses into portable evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path

CRATES = {"api", "provider", "reader", "client"}
PIDS = re.compile(r"^\s*(\d+)\s+\d+\.\d+\s+(.*)$")
RESUMED = re.compile(r"^<\.\.\. (\w+) resumed>(.*)$")
HELD = " <unfinished ...>"

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def syscalls(path):
    pending = {}
    with path.open("rb") as trace:
        for at, original in enumerate(trace, 1):
            match = PIDS.match(original.decode().rstrip("\n"))
            if not match:
                continue
            pid, body = match.groups()
            if body.endswith(HELD):
                assert pid not in pending
                pending[pid] = (at, body.removesuffix(HELD), original)
                continue
            resumed = RESUMED.match(body)
            if resumed:
                start, first, raw = pending.pop(pid)
                assert first.startswith(resumed[1] + "(")
                yield start, at, first + resumed[2], sha(raw + original)
            else:
                yield at, at, body, sha(original)
    assert not pending, pending

def native(trace, sdk):
    launches, witness = [], []
    for start, end, body, source in syscalls(trace):
        key = value = None
        if body.startswith("execve(") and body.endswith(" = 0"):
            program = re.match(r'execve\("([^"]+)", (\[.*\]), [^,]*?\) = 0$', body)
            # strace can print a counted environment pointer after its argv.
            if not program:
                program = re.match(r'execve\("([^"]+)", (\[.*\]), .+\) = 0$', body)
            assert program, body[:150]
            argv = json.loads(program[2])
            if "--crate-name" in argv:
                name = argv[argv.index("--crate-name") + 1]
                if name in CRATES:
                    assert Path(program[1]).samefile(sdk / "bin/rustc")
                    launches.append(dict(crate=name, start=start, end=end, literal_syscall_sha256=source,
                                         argv_sha256=sha(b"\0".join(x.encode() for x in argv) + b"\0")))
        if not body.startswith("write(") or not re.search(r" = [0-9]+$", body):
            continue
        if body.startswith("write(2<pipe:") and r'\"emit\":\"metadata\"' in body:
            found = re.search(r'/out/lib(provider|reader)-[0-9a-f]+\.rmeta', body)
            if found:
                key, value = "rustc-published", found[1]
        if "/control.tsv>" in body:
            found = re.search(r'>, "(hold-fd|release-fd)\\t\d+\\t\d+\\t([12])\\t0', body)
            if found:
                key, value = found[1], {"1":"provider","2":"reader"}[found[2]]
        commit = re.search(r'/fingerprint/lib-(provider|reader)>, "([0-9a-f]{16})", 16\) = 16$', body)
        if commit:
            key, value = "fingerprint-committed", commit[1] + "/" + commit[2]
        if "/cargo.stderr>" in body and "early_cutoff: unit" in body:
            if "built with unchanged public API hash" in body:
                key, value = "reader-published-state", "unchanged" if "dependents may skip" in body else "changed"
            elif "built with changed public API hash" in body:
                key, value = "origin-published-state", "changed"
            elif " CAN skip - all deps allow early cutoff" in body:
                key, value = "client-decision", "skip"
            elif "CANNOT skip - dep 'reader' has build_state=BuiltChanged" in body:
                key, value = "client-decision", "run"
        if key:
            witness.append(dict(event=key, value=value, start=start, end=end, literal_syscall_sha256=source))
    return sorted(launches, key=lambda x:x["start"]), sorted(witness, key=lambda x:x["start"])

def hashes(crates):
    return {crate: {kind: {"sha256": f["digest"], "size": f["nbytes"],
                            **({"value": f["value"]} if "value" in f else {})}
                    for kind, f in files.items()} for crate, files in crates.items()}

def project(role):
    sdk = (role / "rustup/toolchains/ohm").resolve(strict=True)
    driver, = sdk.glob("lib/librustc_driver-*.so")
    identity = {name:digest(file) for name,file in {"cargo":sdk/"bin/cargo", "rustc":sdk/"bin/rustc",
                                                    "driver":driver}.items()}
    terminal = json.loads((role/"terminal.json").read_bytes())
    records = {}
    for path in sorted((role / "records").iterdir()):
        r = json.loads((path/"result.json").read_bytes())
        contents = {p.name:digest(p) for p in sorted(path.iterdir()) if p.is_file()}
        for name,key in [("native.trace","trace"),("cargo.stdout","stdout"),("cargo.stderr","stderr")]:
            assert contents[name] == r[key]
        launches, witness = native(path/"native.trace", sdk)
        messages = [json.loads(line) for line in (path/"cargo.stdout").read_bytes().splitlines()]
        assert messages[-1] == {"reason":"build-finished","success":r["exit"] == 0}
        artifacts = {m["target"]["name"]:m["fresh"] for m in messages if m["reason"]=="compiler-artifact"}
        errors = []
        for m in messages:
            if m["reason"]=="compiler-message" and m["message"]["level"]=="error":
                diag=m["message"]
                errors.append({"crate":m["target"]["name"], "code":diag["code"]["code"],"message":diag["message"],
                               "children":[[x["level"],x["message"]] for x in diag["children"]],
                               "primary":[[s["file_name"],s["line_start"],s["column_start"]] for s in diag["spans"] if s["is_primary"]]})
        assert artifacts==r["artifacts"] and [x["code"] for x in errors]==[x["code"] for x in r["diagnostics"]]
        steps=[]
        if r["order"]:
            lines = (path/"control.tsv").read_text().splitlines()
            assert lines == r["directions"]
            for line in lines:
                action, pid, tid, unit, restore, seen, requested, file = line.split("\t")
                n={"1":"provider","2":"reader"}[unit]
                assert Path(file).name.startswith("lib"+n+"-") and Path(file).suffix==".rmeta"
                steps.append(dict(action=action,crate=n,restore=int(restore),seen_ns=int(seen),requested_ns=int(requested)))
        records[path.name] = dict(exit=r["exit"], order=r["order"], sources=r["source_sha256"],
                                  artifacts=artifacts, errors=errors, compilers=launches,
                                  ordering=witness if r["order"] else [], interposer=steps,
                                  before=hashes(r["before"]),after=hashes(r["after"]),original_files=contents)
    return dict(images=identity, terminal=terminal, original_terminal_sha256=digest(role/"terminal.json"), cases=records)

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="one retained native input directory")
    parser.add_argument("output", type=Path)
    args=parser.parse_args()
    args.output.write_text(json.dumps(project(args.input),indent=1,sort_keys=True)+"\n")

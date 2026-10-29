"""Run one provider/reader publication order with a private installed Linux SDK."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


import hashlib
def fingerprint_state(paths):
    h=hashlib.sha256(); files=0
    for top in paths:
        for f in sorted(top.rglob("*")):
            if f.is_file():
                st=f.stat()
                with f.open("rb") as fd:
                    content=hashlib.file_digest(fd,"sha256").hexdigest()
                h.update(json.dumps([top.name,f.relative_to(top).as_posix(),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,content],separators=(",",":")).encode()+b"\n")
                files+=1
    return [files,h.hexdigest()]
def upgrade(alias, original, dest, states, receipt):
    assert alias.is_symlink() and alias.resolve()==original.resolve() and dest.is_dir()
    def images():
        bound={}
        for name in ("rustc","cargo"):
            with (alias/"bin"/name).open("rb") as fd:
                bound[name]=hashlib.file_digest(fd,"sha256").hexdigest()
        return bound
    before=images(); prior=fingerprint_state(states)
    assert prior[0]>8
    swap=alias.with_name("next-private-ohm")
    assert not swap.exists() and not swap.is_symlink()
    swap.symlink_to(dest.resolve(),target_is_directory=True)
    os.replace(swap,alias)
    assert alias.resolve()==dest.resolve() and fingerprint_state(states)==prior
    receipt.write_text(json.dumps({"before":before,"after":images(),"state_files":prior[0],"state_identity_and_digest":prior[1]},indent=2)+"\n")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("sdk", type=Path, help="directory containing bin/cargo and bin/rustc")
parser.add_argument("root", type=Path, help="new directory for this one run")
parser.add_argument("order", choices=["provider-late", "provider-first"])
parser.add_argument("--expect", choices=["stale", "correct"])
parser.add_argument("--replacement-sdk", type=Path,required=True)
parser.add_argument("--replacement-verdict",type=int,choices=[0,101],required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
sdk = args.sdk.resolve(strict=True)
root = args.root.resolve()
root.mkdir(mode=0o700)
src = root / "src"
shutil.copytree(here / "fixture", src)
proxy = shutil.which("cargo")
assert proxy and (sdk / "bin/cargo").is_file()
aliases = root / "rustup" / "toolchains"
aliases.mkdir(parents=True)
(aliases / "ohm").symlink_to(sdk, target_is_directory=True)
env = dict(PATH=os.environ["PATH"], HOME=str(root), CARGO_HOME=str(root / "home"),
           RUSTUP_HOME=str(aliases.parent), RUSTUP_AUTO_INSTALL="0", LANG="C", LC_ALL="C",
           CARGO_TARGET_DIR=str(root / "target"), CARGO_BUILD_BUILD_DIR=str(root / "shared"))
so = root / "commit-order.so"
subprocess.run(["cc", "-O2", "-shared", "-fPIC", here / "commit-order.c", "-ldl", "-o", so], check=True)

def check(label, overrides=None):
    result = subprocess.run([proxy, "+ohm", "check", "--workspace", "--locked", "--offline",
                             "-j4", "--message-format=json"], cwd=src, env=env | (overrides or {}),
                            capture_output=True, timeout=60)
    (root / (label + ".stdout")).write_bytes(result.stdout)
    (root / (label + ".stderr")).write_bytes(result.stderr)
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    errors = [(r["target"]["name"], (r["message"]["code"] or {}).get("code"))
              for r in rows if r["reason"] == "compiler-message" and r["message"]["level"] == "error"]
    assert rows[-1] == {"reason": "build-finished", "success": result.returncode == 0}
    assert (result.returncode, errors) in [(0, []), (101, [("client", "E0034")])], (label, errors)
    fresh = [r["target"]["name"] for r in rows if r["reason"] == "compiler-artifact" and r["fresh"]]
    print(label, result.returncode, errors, "fresh", sorted(fresh), flush=True)
    return result.returncode, len(fresh)

assert check("original")[0] == 0
assert check("original-repeat") == (0, 4)
witness = dict(LD_PRELOAD=str(so), WITNESS_EVENTS=str(root), WITNESS_ORDER=args.order,
               WITNESS_ORIGINAL_CARGO=str(sdk / "bin/cargo"))
for i, crate in enumerate(["provider", "reader"], 1):
    matches = [f for store in ["target", "shared"] for f in (root / store).rglob("lib-" + crate) if f.parent.name == "fingerprint" or f.parent.parent.name == ".fingerprint"]
    fp, = matches
    assert len(fp.read_bytes()) == 16
    witness[f"WITNESS_FINGERPRINT_{i}"] = str(fp)
    witness[f"WITNESS_BEFORE_{i}"] = str(fp.stat().st_mtime_ns)
provider = src / "provider/src/lib.rs"
reader = src / "reader/src/lib.rs"
origin, middle = provider.read_bytes(), reader.read_bytes()
provider.write_bytes(origin + b"impl api::Second for Token { fn priority(&self) -> u8 { 29 } }\n")
assert middle.count(b"{ 11 }") == 1
reader.write_bytes(middle.replace(b"{ 11 }", b"{ 12 }"))
warm, _ = check("edited", witness)
events = [s.split("\t")[:5] for s in (root / "control.tsv").read_text().splitlines()]
held = "1" if args.order == "provider-late" else "2"
assert [e[0] for e in events if e[0].startswith(("hold", "release", "error", "timeout"))] == ["hold-fd", "release-fd"]
assert all(e[3] == held and e[4] == "0" for e in events if e[0] in ("hold-fd", "release-fd"))
repeat, fresh = check("edited-repeat")
assert warm == repeat and (warm != 0 or fresh == 4)
empty, _ = check("edited-clean", dict(CARGO_TARGET_DIR=str(root / "cold-target"),
                                      CARGO_BUILD_BUILD_DIR=str(root / "cold-shared")))
assert empty == 101

assert warm==repeat==0 and empty==101 and args.order=="provider-late"
upgrade(aliases/"ohm",sdk,args.replacement_sdk,[src,root/"target",root/"shared"],root/"upgrade.json")
first,_=check("first-after-upgrade"); second,_=check("second-after-upgrade")
clean,_=check("independent-after-upgrade",dict(CARGO_TARGET_DIR=str(root/"new-cold-target"),CARGO_BUILD_BUILD_DIR=str(root/"new-cold-shared")))
assert clean==101
assert first==second==args.replacement_verdict,(first,second,args.replacement_verdict)
provider.write_bytes(origin)
reader.write_bytes(middle)
assert check("restore")[0] == 0 and check("restore-repeat") == (0, 4)
verdict = "stale" if warm == 0 else "correct"
print("Warm result:", verdict)
assert args.expect is None or args.expect == verdict

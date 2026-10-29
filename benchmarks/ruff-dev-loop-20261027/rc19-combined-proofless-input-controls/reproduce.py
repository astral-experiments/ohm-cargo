"""Run the actual Ruff TextSize edit using an enrolled Linux SDK and a new private directory."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


CALLER = """use ruff_text_size::TextSize;
#[allow(dead_code)]
trait Legacy { fn saturating_sub(self, rhs: Self) -> Self; }
impl Legacy for TextSize {
    fn saturating_sub(self, rhs: Self) -> Self { self.checked_sub(rhs).unwrap_or(TextSize::new(71)) }
}
fn main() { println!("{:?}", TextSize::new(2).saturating_sub(TextSize::new(9))); }
"""
PACKET = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(sdk, work):
    if sys.platform != "linux" or os.geteuid() == 0:
        raise SystemExit("Run as an ordinary user on Linux.")
    sdk = sdk.resolve(strict=True)
    subjects = json.loads((PACKET / "subjects.json").read_text())["subjects"]
    cargo_sha = digest(sdk / "bin/cargo")
    arms = [arm for arm, row in subjects.items() if row["binary"] == cargo_sha]
    if len(arms) != 1:
        raise SystemExit("Expected one of the two enrolled Linux Cargo executables in SDK/bin/cargo.")
    arm = arms[0]
    if digest(sdk / "bin/rustc") != subjects[arm]["rustc"]:
        raise SystemExit("The SDK's rustc differs from the enrolled compiler.")
    drivers = list((sdk / "lib").glob("librustc_driver*.so"))
    if len(drivers) != 1 or digest(drivers[0]) != subjects[arm]["driver"]:
        raise SystemExit("Expected the enrolled compiler driver.")
    linker = sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    if digest(linker) != subjects[arm]["wild"]:
        raise SystemExit("Expected the enrolled stock linker.")
    rustup = shutil.which("rustup")
    if rustup is None:raise SystemExit("Install rustup and its cargo proxy first.")
    proxy = Path(rustup).parent / "cargo"
    if not proxy.is_file():raise SystemExit("The rustup cargo proxy is missing.")
    work = work.absolute()
    if work.exists():raise SystemExit("Choose a new private directory that does not exist yet.")
    work.mkdir(mode=0o700)
    for rel in ["rustup/toolchains","viewer/src","text/src","home","tmp","logs"]:
        (work/rel).mkdir(parents=True, exist_ok=True)
    (work/"rustup/toolchains/ohm").symlink_to(sdk, target_is_directory=True)
    env = {
        "HOME": str(work/"home"), "RUSTUP_HOME": str(work/"rustup"), "RUSTUP_TOOLCHAIN":"ohm",
        "RUSTUP_AUTO_INSTALL":"0","CARGO_HOME":str(work/"cargo-home"),"CARGO_NET_OFFLINE":"true",
        "CARGO_TARGET_DIR":str(work/"target"),"CARGO_BUILD_BUILD_DIR":str(work/"shared"),
        "TMPDIR":str(work/"tmp"),"PATH":str(proxy.parent)+os.pathsep+"/usr/local/bin:/usr/bin:/bin",
        "LANG":"C.UTF-8","LC_ALL":"C.UTF-8",
    }
    (work/"Cargo.toml").write_text('[workspace]\nresolver="2"\nmembers=["text","viewer"]\n')
    (work/"text/Cargo.toml").write_text('[package]\nname="ruff_text_size"\nversion="0.0.1"\nedition="2024"\n[features]\nserde=[]\nschemars=[]\nget-size=[]\n')
    (work/"viewer/Cargo.toml").write_text('[package]\nname="viewer"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nruff_text_size={path="../text"}\n')
    (work/"viewer/src/main.rs").write_text(CALLER)
    results = []
    for phase,version,expected,fresh in [
        ("original","old",71,False),("unchanged","old",71,True),
        ("edited","new",0,False),("edited-unchanged","new",0,True),
    ]:
        src = json.loads(gzip.decompress((PACKET/(version+"-sources.json.gz")).read_bytes()))
        for name, code in src.items():
            rel = Path(name).relative_to("crates/ruff_text_size")
            dest = work/"text"/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.read_text() != code:
                dest.write_text(code)
        cmd=[str(proxy),"+ohm","build","-p","viewer","--offline","-j1","--message-format=json"]
        build=subprocess.run(cmd,cwd=work,env=env,capture_output=True,timeout=120)
        (work/"logs"/(phase+".stdout")).write_bytes(build.stdout)
        (work/"logs"/(phase+".stderr")).write_bytes(build.stderr)
        if build.returncode:
            raise RuntimeError(f"Cargo failed at {phase}, see its private stderr")
        rows=[json.loads(line) for line in build.stdout.splitlines()]
        assert rows[-1] == {"reason":"build-finished","success":True}
        arts=[r for r in rows if r["reason"]=="compiler-artifact"]
        assert {r["target"]["name"]:r["fresh"] for r in arts} == {"viewer":fresh,"ruff_text_size":fresh}
        exe=Path(next(r["executable"] for r in arts if r["executable"]))
        value=subprocess.check_output([exe],cwd=work,env=env).decode()
        assert value == f"{expected}\n"
        recipes=list((work/"target").rglob("viewer.rlink"))
        assert len(recipes)==1
        objects=list(recipes[0].with_suffix(".rlink-objects").glob("*.o"))
        proof=recipes[0].with_suffix(".rlink-cache.json")
        assert objects and proof.exists()==(arm=="A")
        if proof.exists():
            assert "unused_extern_names" not in json.loads(proof.read_bytes())
        result={"phase":phase,"value":expected,"fresh":fresh,"elf_sha256":digest(exe),
                "objects":len(objects),"recipe_bytes":recipes[0].stat().st_size,
                "optional_manifest":proof.exists(),"cargo_sha256":cargo_sha}
        results.append(result)
        print(json.dumps(result,sort_keys=True))
    assert results[0]["elf_sha256"]==results[1]["elf_sha256"]
    assert results[2]["elf_sha256"]==results[3]["elf_sha256"]
    assert results[0]["elf_sha256"]!=results[2]["elf_sha256"]
    (work/"results.json").write_text(json.dumps(results,indent=2)+"\n")


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sdk",type=Path,help="complete enrolled SDK with rustc, Cargo and Wild")
    ap.add_argument("new_directory",type=Path,help="new private path with room for source and artifacts")
    args=ap.parse_args()
    run(args.sdk,args.new_directory)

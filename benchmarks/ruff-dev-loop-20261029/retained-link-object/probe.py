"""Compare true incremental rebuilds after replacing a saved linker object with authentic code."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("root", type=Path, help="new directory on one filesystem")
ap.add_argument(
    "--expect",
    choices=("stale", "correct"),
    required=True,
    help="expected result for the in-place case",
)
args = ap.parse_args()
root = args.root.absolute()
assert sys.platform == "linux" and not root.exists()
assert shutil.disk_usage(root.parent).free > 128 * 2**20
root.mkdir(mode=0o700)
src = root / "project"
for path in [
    src / "src",
    src / "provider/src",
    root / "logs",
    root / "kept",
    root / "elfs",
    root / "cargo-home",
]:
    path.mkdir(parents=True)
target = root / "target"
shared = root / "shared"
target.mkdir()
shared.mkdir()
tool_env = {
    k: os.environ[k]
    for k in ("PATH", "HOME", "USER", "LOGNAME", "RUSTUP_HOME")
    if k in os.environ
}
tool_env.update(
    CARGO_HOME=str(root / "cargo-home"),
    CARGO_TARGET_DIR=str(target),
    CARGO_BUILD_BUILD_DIR=str(shared),
    CARGO_NET_OFFLINE="true",
    CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never",
    RUSTUP_AUTO_INSTALL="0",
    LC_ALL="C",
    TZ="UTC",
)
(src / "Cargo.toml").write_text(
    '[package]\nname="link_probe"\nversion="0.1.0"\nedition="2024"\n[workspace]\n[dependencies]\nprovider={path="provider"}\n[profile.dev]\ncodegen-units=1\nincremental=true\ndebug=0\n'
)
(src / "provider/Cargo.toml").write_text(
    '[package]\nname="provider"\nversion="0.1.0"\nedition="2024"\n'
)


def main_value(n):
    (src / "src/main.rs").write_text(
        f'#[unsafe(no_mangle)]\n#[inline(never)]\npub extern "C" fn model_observable() -> u32 {{std::hint::black_box({n})}}\n'
        'fn main() { println!("{} {}", model_observable(), provider::read()); }\n'
    )


def dep_value(n):
    (src / "provider/src/lib.rs").write_text(
        f"#[inline(never)] pub fn read() -> u32 {{std::hint::black_box({n})}}\n"
    )


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def choutput(cmd):
    return subprocess.check_output(cmd, cwd=src, env=tool_env)


def write_json(path, data):
    with path.open("x") as f:
        json.dump(data, f, sort_keys=True, indent=2)
        f.write("\n")


def props(path):
    st = path.stat()
    return dict(
        device=st.st_dev,
        inode=st.st_ino,
        links=st.st_nlink,
        size=st.st_size,
        mode=stat.S_IMODE(st.st_mode),
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
        sha256=sha_file(path),
    )


def real_tools():
    rustc = Path(
        choutput(["rustup", "which", "--toolchain", "ohm", "rustc"]).decode().strip()
    )
    cargo = Path(
        choutput(["rustup", "which", "--toolchain", "ohm", "cargo"]).decode().strip()
    )
    sdk = rustc.parent.parent
    (driver,) = list((sdk / "lib").glob("librustc_driver-*.so"))
    wild = sdk / "lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd"
    return {
        name: sha_file(f)
        for name, f in (
            ("rustc", rustc),
            ("driver", driver),
            ("cargo", cargo),
            ("wild", wild),
        )
    }


def fresh(label):
    p = root / "kept" / label
    p.mkdir()
    for path in (target, shared):
        path.rename(p / path.name)
        path.mkdir()


def build(tag):
    p = root / "logs" / tag
    p.mkdir()
    with (p / "stdout").open("xb") as out, (p / "stderr").open("xb") as err:
        rc = subprocess.run(
            [
                "strace",
                "-ff",
                "-qq",
                "-s",
                "131072",
                "-e",
                "trace=execve",
                "-o",
                p / "exec",
                "cargo",
                "+ohm",
                "build",
                "--locked",
                "--offline",
                "-j2",
                "--message-format=json",
            ],
            cwd=src,
            env=tool_env,
            stdout=out,
            stderr=err,
        ).returncode
    rows = [json.loads(row) for row in (p / "stdout").read_bytes().splitlines()]
    assert rc in (0, 101) and rows[-1] == {
        "reason": "build-finished",
        "success": rc == 0,
    }, (tag, rc, (p / "stderr").read_bytes()[-900:])
    result = {
        "cargo": rc,
        "source": sha_file(src / "src/main.rs"),
        "provider_source": sha_file(src / "provider/src/lib.rs"),
        "typed": [
            [r["target"]["name"], r["fresh"]]
            for r in rows
            if r["reason"] == "compiler-artifact"
        ],
    }
    if rc == 0:
        (unit,) = [
            row
            for row in rows
            if row["reason"] == "compiler-artifact"
            and row["target"]["name"] == "link_probe"
        ]
        exe = Path(unit["executable"])
        proc = subprocess.run([exe], cwd=src, env=tool_env, capture_output=True)
        assert proc.returncode == 0 and not proc.stderr, (tag, proc)
        digest = sha_file(exe)
        retained = root / "elfs" / digest
        if not retained.exists():
            shutil.copy2(exe, retained)
        assert sha_file(retained) == digest
        check = subprocess.run([retained], cwd=src, env=tool_env, capture_output=True)
        assert (check.returncode, check.stdout, check.stderr) == (
            proc.returncode,
            proc.stdout,
            proc.stderr,
        )
        (p / "program.stdout").write_bytes(check.stdout)
        result.update(verdict=proc.stdout.decode().strip(), elf=digest)
    print(tag, result.get("verdict", rc), flush=True)
    write_json(p / "outcome.json", result)
    return result


def object_state():
    manifests = [p for d in (target, shared) for p in d.rglob("*.rlink-cache.json")]
    roots = []
    for manifest in manifests:
        m = json.loads(manifest.read_bytes())
        if Path(m["executable"]["path"]).name != "link_probe":
            continue
        for row in m["objects"]:
            f = Path(row["path"])
            nm = subprocess.run(
                ["nm", "-g", "--defined-only", f], capture_output=True, check=True
            )
            if any(
                x.split()[-1:] == [b"model_observable"] for x in nm.stdout.splitlines()
            ):
                roots.append((f, manifest, row["blake3"]))
    assert len(roots) == 1, (str(manifests), str(roots))
    f, manifest, blake = roots[0]
    s = f.stat()
    aliases = []
    for directory in (target, shared):
        for x in directory.rglob("*.o"):
            if (
                x.is_file()
                and x.stat().st_ino == s.st_ino
                and x.stat().st_dev == s.st_dev
            ):
                aliases.append(str(x.relative_to(root)))
    return f, dict(
        relative=str(f.relative_to(root)),
        manifest=str(manifest.relative_to(root)),
        blake3=blake,
        stat=props(f),
        aliases=sorted(aliases),
    )


def replace(f, authentic, mode):
    st = f.stat()
    assert st.st_size == len(authentic) and sha_file(f) != sha(authentic)
    if mode == "in-place":
        with f.open("r+b") as out:
            assert out.write(authentic) == len(authentic)
            out.flush()
            os.fsync(out.fileno())
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))
    elif mode == "rename":
        scratch = f.with_name(f.name + ".only-this-probe")
        with scratch.open("xb") as out:
            out.write(authentic)
            out.flush()
            os.fsync(out.fileno())
        scratch.chmod(stat.S_IMODE(st.st_mode))
        os.utime(scratch, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(scratch, f)
    now = f.stat()
    assert now.st_size == st.st_size and now.st_mtime_ns == st.st_mtime_ns
    if mode != "untouched":
        assert (now.st_dev == st.st_dev and now.st_ino == st.st_ino) == (
            mode == "in-place"
        )
        assert sha_file(f) == sha(authentic)


main_value(29)
dep_value(7)
choutput(["cargo", "+ohm", "generate-lockfile", "--offline"])
stages = {}
outputs = {}
tools = real_tools()
stages["alternative"] = build("authentic-alternate")
assert stages["alternative"]["verdict"] == "29 7"
obj, auth = object_state()
authentic = obj.read_bytes()
(root / "authentic-29.o").write_bytes(authentic)
fresh("alternate")
for mode in ("untouched", "rename", "in-place"):
    main_value(17)
    dep_value(7)
    seed = build(mode + "-seed")
    assert seed["verdict"] == "17 7"
    obj, old = object_state()
    assert (
        old["stat"]["size"] == len(authentic)
        and old["stat"]["sha256"] != auth["stat"]["sha256"]
    )
    replace(obj, authentic, mode)
    displaced = props(obj)
    observed_aliases = {a: sha_file(root / a) for a in old["aliases"]}
    dep_value(11)
    edited = build(mode + "-edit-dependency")
    repeated = build(mode + "-unchanged")
    main_value(41)
    repaired = build(mode + "-edit-root")
    outputs[mode] = dict(
        original=seed,
        object=old,
        after=displaced,
        aliases_after=observed_aliases,
        edited=edited,
        repeated=repeated,
        repaired=repaired,
    )
    write_json(root / (mode + ".json"), outputs[mode])
    fresh(mode)
main_value(17)
dep_value(11)
clean17 = build("independent-17-11")
assert clean17["verdict"] == "17 11"
fresh("clean17")
main_value(41)
dep_value(11)
clean41 = build("independent-41-11")
assert clean41["verdict"] == "41 11"
assert (
    outputs["untouched"]["edited"]["elf"]
    == outputs["rename"]["edited"]["elf"]
    == clean17["elf"]
)
assert all(a["repaired"]["elf"] == clean41["elf"] for a in outputs.values())
in_place = outputs["in-place"]
expected = "17 11" if args.expect == "correct" else "29 11"
for observation in (in_place["edited"], in_place["repeated"]):
    assert observation["cargo"] == 0 and observation["verdict"] == expected, observation
    assert (observation["elf"] == clean17["elf"]) == (args.expect == "correct")
write_json(
    root / "result.json",
    dict(
        tools=tools,
        alternate=auth,
        stages=stages,
        outputs=outputs,
        clean17=clean17,
        clean41=clean41,
    ),
)

"""Exercise profile changes using real Cargo, build scripts, rustc, and the linker."""
import argparse
import runpy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
NATIVE = runpy.run_path(str(HERE/"native_execs.py"))


def digest(path):
    with path.open("rb") as reader:
        return hashlib.file_digest(reader, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


def save(path, value):
    write(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def executions(trace):
    rows = NATIVE["native_execs"](trace.read_bytes())
    result = []
    for row in rows:
        name = row["program"]
        if NATIVE["is_compile"](row):
            role = "compile:" + row["crate"]
        elif NATIVE["is_link"](row) or (name=="ld" and row["output_argument"]):
            role = "link"
        elif name.startswith("build-script-") or name == "build_script_build":
            role = "build-script"
        else:
            role = "other"
        result.append([name, role])
    assert result[:2] == [["cargo", "other"], ["cargo", "other"]]
    return result


TOP = """[package]
name = "profile_probe"
version = "0.1.0"
edition = "2021"
description = '''
This is a multiline string.
[profile.fake]
'''

[workspace]
resolver = "2"

[features]
original = []
"""


def manifest(active=True, raw=17, extra="", prefix=TOP):
    return prefix + f"""
[profile.dev]
debug = 0
incremental = false
debug-assertions = {str(active).lower()}
# raw-value={raw}

[profile.fast-test]
inherits = "dev"
opt-level = 1
""" + extra


MAIN = """fn main() {
    println!("{} {}", cfg!(debug_assertions), env!("RAW_PROFILE_VALUE"));
}
"""

BUILDER = """fn main() {
    println!("cargo::rerun-if-changed=Cargo.toml");
    let raw = std::fs::read_to_string("Cargo.toml").unwrap();
    let value = raw.lines().find_map(|line| line.strip_prefix("# raw-value=")).unwrap();
    println!("cargo::rustc-env=RAW_PROFILE_VALUE={value}");
}
"""


def exercise(arm, image, sdk, arena, report, floor, proxies):
    work = arena / "ws"
    config = work / "Cargo.toml"
    private = arena / "ru/toolchains/ohm"
    (private / "bin").mkdir(parents=True)
    for program, source in [("cargo", image), ("rustc", sdk / "bin/rustc")]:
        (private / "bin" / program).symlink_to(source.resolve(strict=True))
    (private / "lib").symlink_to((sdk / "lib").resolve(strict=True), target_is_directory=True)
    write(config, manifest())
    write(work / "build.rs", BUILDER)
    write(work / "src/main.rs", MAIN)
    write(arena / "late/Cargo.toml", '[package]\nname="late"\nversion="0.1.0"\nedition="2021"\n')
    write(arena / "late/src/lib.rs", "pub fn value() -> u8 { 29 }\n")
    cli = [str(proxies / "cargo"), "+ohm"]
    env = dict(HOME=str(Path.home()), PATH=str(proxies) + ":/usr/bin:/bin",
               LC_ALL="C", CARGO_TERM_COLOR="never", RUSTUP_HOME=str(arena / "ru"), RUSTUP_AUTO_INSTALL="0",
               CARGO_HOME=str(arena / "cargo-home"), CARGO_TARGET_DIR=str(arena / "target"),
               CARGO_BUILD_BUILD_DIR=str(arena / "shared"), CARGO_NET_OFFLINE="true",
               CARGO_LOG="cargo::ops::resolve=debug", CARGO_CACHE_AUTO_CLEAN_FREQUENCY="never")
    result = subprocess.run(cli + ["-Vv"], cwd=work, env=env, capture_output=True, check=True)
    assert b"2fe90823d8eadc95de56c2cde8d41e0082aac0eb" in result.stdout
    subprocess.run(cli + ["generate-lockfile", "--offline"], cwd=work, env=env,
                   capture_output=True, check=True)
    lock = work / "Cargo.lock"
    golden = lock.read_bytes()
    marker = arena / "target/.cargo-resolve-cache-v1"
    out = report / arm
    out.mkdir()
    rows = {}
    candidate = arm == "B"

    def check(label, *, text=None, expected=0, hit=None, output=None, error=None, args=(), rebuild=None, script=None):
        assert min(shutil.disk_usage(p).free for p in (arena,report)) > floor, "space reserve"
        if text is not None:
            write(config, text)
        f = out / label
        f.mkdir()
        cmd = ["strace", "-f", "-qq", "-s", "131072", "-e", "trace=execve,execveat",
               "-o", str(f / "exec"), *cli, "build", "-p", "profile_probe", "--locked", "--offline",
               "--message-format=json", *args]
        x = subprocess.run(cmd, cwd=work, env=env, capture_output=True, timeout=100)
        (f / "stdout").write_bytes(x.stdout)
        (f / "stderr").write_bytes(x.stderr)
        events = executions(f / "exec")
        msg = x.stderr.decode()
        reused = "reusing the cached workspace resolution" in msg
        row = dict(exit=x.returncode, hit=reused, manifest=digest(config), lock=digest(lock),
                   marker=marker.read_text().strip() if marker.is_file() else None, events=events,
                   stdout=digest(f / "stdout"), stderr=digest(f / "stderr"), trace=digest(f / "exec"))
        (f/"Cargo.lock").write_bytes(lock.read_bytes())
        (f/"Cargo.toml").write_bytes(config.read_bytes())
        if marker.is_file(): (f/"marker").write_bytes(marker.read_bytes())
        if x.returncode == 0:
            records = [json.loads(line) for line in x.stdout.splitlines()]
            products = [r for r in records if r["reason"] == "compiler-artifact"]
            assert records[-1] == {"reason": "build-finished", "success": True}
            artifact, = [r for r in products if r["target"]["name"] == "profile_probe" and r.get("executable")]
            exe = Path(artifact["executable"])
            raw_runtime=subprocess.check_output([exe], cwd=work, env=env)
            (f/"runtime.stdout").write_bytes(raw_runtime)
            object_path=report/"elf"/digest(exe)
            if not object_path.exists(): shutil.copyfile(exe,object_path)
            assert digest(object_path)==digest(exe)
            row.update(elf=digest(exe), output=raw_runtime.decode().strip(),
                       dirty=sorted(r["target"]["name"] for r in products if not r["fresh"]))
        row["roles"] = [role for _, role in events if role != "other"]
        row["diagnostic"] = "\n".join(line for line in msg.splitlines() if not re.match(r"^\s*\d+\.\d+s\s+", line))
        save(f / "row.json", row)
        print(arm, label, x.returncode, reused, row.get("output"), row["roles"], flush=True)
        assert x.returncode == expected and (hit is None or reused == hit), (label, msg[-2500:])
        if output is not None:
            assert row["output"] == output, (label, row)
        if error is not None:
            assert error in msg, (label, msg)
        if rebuild is not None:
            assert ("compile:profile_probe" in row["roles"]) == rebuild and ("link" in row["roles"]) == rebuild, (label, row)
        if script is not None:
            assert ("build-script" in row["roles"]) == script, (label, row)
        rows[label] = row
        return row

    original = check("01-seed", hit=False, output="true 17", rebuild=True, script=True)
    check("02-unchanged", hit=True, output="true 17", rebuild=False, script=False)
    not_used = manifest(extra='debug = "line-tables-only"\n')
    check("03-inactive", text=not_used, hit=candidate, output="true 17", script=True)
    check("04-restored", text=manifest(), hit=candidate, output="true 17", script=True)
    changed = check("05-active", text=manifest(False), hit=candidate, output="false 17", rebuild=True, script=True)
    assert original["elf"] != changed["elf"]
    changed = check("06-script-value", text=manifest(False, 29), hit=candidate, output="false 29", rebuild=True, script=True)
    check("07-repeat", hit=True, output="false 29", rebuild=False, script=False)
    # Make the clean control at exactly the same paths, independently of all previous products.
    for name in ("target", "shared", "cargo-home"):
        (arena / name).rename(arena / ("old-" + name))
    assert not any((arena / role).exists() for role in ("target", "shared", "cargo-home"))
    clean = check("08-clean-edited", hit=False, output="false 29", rebuild=True, script=True)
    assert clean["elf"] == changed["elf"], (clean["elf"], changed["elf"])
    check("09-missing-profile", expected=101, args=("--profile", "nonexistent"), error="nonexistent")
    check("10-unmatched-override", text=manifest(False, 29, extra='\n[profile.dev.package.no_such_crate]\nopt-level=1\n'),
          hit=candidate, output="false 29", error="did not match any packages")
    check("11-late-dependency", text=manifest(False, 29, extra='\n[dependencies]\nlate={path="../late"}\n'),
          hit=False, expected=101, error="--locked")
    check("12-earlier-dependency", text=manifest(False, 29, prefix=TOP+'\n[dependencies]\nlate={path="../late"}\n'),
          hit=False, expected=101, error="--locked")
    check("13-duplicate-header", text=manifest(False, 29, extra="\n[profile.dev]\ndebug = 1\n"),
          hit=False, expected=101, error="duplicate")
    check("14-invalid-profile", text=manifest(False, 29).replace("opt-level = 1", 'opt-level = "bad"'),
          expected=101, error="opt-level")
    check("15-multiline-feature-error", text=manifest(False, 29), expected=101,
          args=("--features", "new"), error="new")
    check("16-feature-after-fake-header", text=manifest(False, 29, prefix=TOP + "new = []\n"), hit=False,
          output="false 29", args=("--features", "new"))
    assert lock.read_bytes() == golden
    lock.write_bytes(b"version = [\n")
    check("17-malformed-lock", hit=False, expected=101, error="failed to parse lock file")
    lock.write_bytes(golden)
    check("18-recovery", text=manifest(), hit=False, output="true 17", script=True)
    check("19-final", hit=True, output="true 17", rebuild=False, script=False)
    assert lock.read_bytes() == golden
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("control","candidate","sdk","work","out"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--rustup-proxies",type=Path,default=Path.home()/".cargo/bin")
    p.add_argument("--reserve-gib",type=float,required=True,help="minimum free space on both filesystems")
    a=p.parse_args()
    assert a.reserve_gib>=0 and a.work.parent.is_dir() and a.out.parent.is_dir()
    root,report=a.work.absolute(),a.out.absolute()
    assert not os.path.lexists(root) and not os.path.lexists(report)
    assert root not in report.parents and report not in root.parents and root!=report
    floor=int(a.reserve_gib*2**30)
    assert min(shutil.disk_usage(p.parent).free for p in (root,report))>floor
    sdk=a.sdk.resolve(strict=True)
    assert digest(sdk/"bin/rustc")=="fa2ed3ec44adb4455d5323c4ee582becd5307cb4aae6b5cfc3cdc289b3140512"
    assert digest(sdk/"lib/rustlib/x86_64-unknown-linux-gnu/bin/wild-ld/ld.bfd")=="0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
    images=[a.control.resolve(strict=True), a.candidate.resolve(strict=True)]
    hashes=[digest(image) for image in images]
    assert hashes==["967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9","80356b8237d3089d3360b6de5abfc64a17e4b8d3f0ec1fb64e09254418b5c5e5"]
    os.umask(0o077);root.mkdir();report.mkdir();(report/"elf").mkdir()
    arena=root/"arena"
    arms=[]
    for arm,image in zip("AB",images):
        rows=exercise(arm,image,sdk,arena,report,floor,a.rustup_proxies.resolve(strict=True))
        arms.append(rows)
        arena.rename(root/(arm+"-finished"))
    assert arms[0].keys() == arms[1].keys()
    for name in arms[0]:
        a, b = [rows[name] for rows in arms]
        for key in ("exit", "manifest", "lock", "output", "elf", "dirty"):
            assert a.get(key) == b.get(key), (name, key, a.get(key), b.get(key))
        assert sorted(a["roles"]) == sorted(b["roles"]), (name, a["roles"], b["roles"])
    save(report / "complete.json", dict(images=hashes, source_size=len(BUILDER)+len(MAIN),
         scopes=[{"stage": k, "exit": a["exit"], "control_hit": a["hit"], "candidate_hit": b["hit"],
                  "roles": sorted(a["roles"]), "output": a.get("output"), "elf": a.get("elf")}
                 for (k,a),b in zip(arms[0].items(), arms[1].values())]))


if __name__ == "__main__":
    main()

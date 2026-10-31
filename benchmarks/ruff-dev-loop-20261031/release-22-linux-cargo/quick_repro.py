"""Run a real two-crate Cargo error/repair cycle with the currently selected +ohm toolchain."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    work = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) == 2
        else Path(tempfile.mkdtemp(prefix="ohm-repair-"))
    )
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit("provide an empty directory")
    project = work / "project"
    for directory in (project / "src", project / "dep/src"):
        directory.mkdir(parents=True)
    (project / "Cargo.toml").write_text(
        '[package]\nname="app"\nversion="0.1.0"\nedition="2021"\n[dependencies]\ndep={path="dep"}\n'
    )
    (project / "dep/Cargo.toml").write_text(
        '[package]\nname="dep"\nversion="0.1.0"\nedition="2021"\n'
    )
    app = project / "src/lib.rs"
    dep = project / "dep/src/lib.rs"
    good = "pub fn answer() -> u32 { dep::answer() }\nfn unused_after_repair() {}\n"
    bad = 'const _: u32 = "deliberately_invalid";\n'
    app.write_text(good)
    dep.write_text("pub fn answer() -> u32 { 1 }\n")
    env = {
        k: os.environ[k]
        for k in ("HOME", "PATH", "RUSTUP_HOME", "LANG", "LC_ALL", "TMPDIR", "USER")
        if k in os.environ
    }
    env.update(
        CARGO_HOME=str(work / "cargo-home"),
        CARGO_TARGET_DIR=str(work / "target"),
        CARGO_BUILD_BUILD_DIR=str(work / "build"),
        CARGO_NET_OFFLINE="true",
        CARGO_TERM_COLOR="never",
        RUSTUP_AUTO_INSTALL="0",
    )
    cmd = ["cargo", "+ohm", "check", "--offline", "--tests", "--message-format=json"]
    version = subprocess.check_output(
        ["cargo", "+ohm", "-vV"], cwd=project, env=env, text=True
    )
    rustc = subprocess.check_output(
        ["rustc", "+ohm", "-vV"], cwd=project, env=env, text=True
    )
    visits = {}

    def run(name, expected_exit):
        p = subprocess.run(cmd, cwd=project, env=env, capture_output=True)
        (work / (name + ".stdout")).write_bytes(p.stdout)
        (work / (name + ".stderr")).write_bytes(p.stderr)
        events = [json.loads(l) for l in p.stdout.splitlines()]
        if (
            p.returncode != expected_exit
            or not events
            or events[-1] != {"reason": "build-finished", "success": expected_exit == 0}
        ):
            raise RuntimeError((name, p.returncode, p.stderr.decode(errors="replace")))
        diags = [e["message"] for e in events if e["reason"] == "compiler-message"]
        codes = [d["code"]["code"] for d in diags if d.get("code")]
        errors = [
            s["text"]
            for d in diags
            if d["level"] == "error"
            for s in d["spans"]
            if s["is_primary"]
        ]
        warnings = [d["message"] for d in diags if d["level"] == "warning"]
        if name == "invalid" and not any(
            "deliberately_invalid" in t["text"] for span in errors for t in span
        ):
            raise RuntimeError(
                "invalid control did not diagnose the deliberate source error"
            )
        dirty = sorted(
            e["target"]["name"]
            for e in events
            if e["reason"] == "compiler-artifact" and not e["fresh"]
        )
        visits[name] = {
            "exit": p.returncode,
            "codes": codes,
            "warnings": warnings,
            "error_primary": errors,
            "dirty": dirty,
        }
        print(name, p.returncode, ",".join(codes), ",".join(dirty), flush=True)

    run("cold", 0)
    app.write_text(good + bad)
    run("invalid", 101)
    app.write_text(good)
    dep.write_text("pub fn answer() -> u32 { 2 }\n")
    run("repair", 0)
    run("repeat", 0)
    dep.write_text("pub fn answer() -> u32 { 3 }\n")
    run("same-interface-edit", 0)
    # Keep the original cache available for inspection and compare the exact same source in a new installation.
    for key in ("CARGO_TARGET_DIR", "CARGO_BUILD_BUILD_DIR"):
        env[key] += "-empty"
    run("empty", 0)
    if (
        visits["cold"]["codes"] != ["dead_code"]
        or visits["empty"]["codes"] != ["dead_code"]
        or "E0308" not in visits["invalid"]["codes"]
    ):
        raise RuntimeError("positive or negative control failed")
    (work / "repro.json").write_text(
        json.dumps(
            {"cargo": version, "rustc": rustc, "visits": visits},
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    print("Receipts in", work)


if __name__ == "__main__":
    main()

"""Run a path-only build-to-check diamond on an installed Ohm Cargo/rustc pair."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--toolchain", required=True, help="installed rustup toolchain, e.g. ohm")
parser.add_argument("--expect", choices=["baseline", "fixed"], required=True)
parser.add_argument("--proxy", default="cargo", help="rustup's cargo proxy")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="ohm-check-closure-") as directory:
    root = Path(directory)
    for case in ["mixed", "pure", "unshared"]:
        project = root / case
        project.mkdir()
        (project / "Cargo.toml").write_text('[workspace]\nmembers=["mixed","bridge","app"]\nresolver="2"\n')
        for name, source in {
            "mixed": "pub struct Token(pub usize);",
            "bridge": "pub fn token() -> mixed::Token {mixed::Token(7)}",
            "app": "fn main() {let v: mixed::Token=bridge::token(); println!(\"{}\",v.0);}",
        }.items():
            crate = project / name
            (crate / "src").mkdir(parents=True)
            manifest = f'[package]\nname="{name}"\nversion="0.1.0"\nedition="2021"\n'
            if name == "mixed":
                types = ["rlib"] if case == "pure" else ["rlib", "cdylib"]
                manifest += "[lib]\ncrate-type=" + json.dumps(types) + "\n"
            else:
                manifest += '[dependencies]\nmixed={path="../mixed"}\n'
                if name == "app":
                    manifest += 'bridge={path="../bridge"}\n'
            (crate / "Cargo.toml").write_text(manifest)
            (crate / "src" / ("main.rs" if name == "app" else "lib.rs")).write_text(source)
        for step, cmd, store in [
            ("build", ["build"], "warm"),
            ("native-to-check", ["-Zohm-reuse-built-deps", "check"], "warm"),
            ("cold-check", ["-Zohm-reuse-built-deps", "check"], "cold"),
        ]:
            env = dict(os.environ, CARGO_HOME=str(project / "home"),
                       CARGO_TARGET_DIR=str(project / (store + "-target")),
                       CARGO_BUILD_BUILD_DIR=str(project / (store + "-build")), CARGO_TERM_COLOR="never")
            extra = ["-Zohm-shared-stages=no"] if case == "unshared" else []
            result = subprocess.run([args.proxy, "+" + args.toolchain, *extra, *cmd, "--offline", "--message-format=json"], cwd=project, env=env, capture_output=True, text=True)
            messages = [json.loads(line) for line in result.stdout.splitlines()]
            artifacts = [(m["target"]["name"], m["fresh"]) for m in messages if m["reason"] == "compiler-artifact"]
            errors = [m["message"]["message"] for m in messages if m["reason"] == "compiler-message" and m["message"]["level"] == "error"]
            print(case, step, result.returncode, artifacts, errors)
            failure = args.expect == "baseline" and case != "pure" and step == "native-to-check"
            if failure:
                error = "colliding StableCrateId" if case == "mixed" else "mismatched types"
                assert result.returncode != 0 and any(error in m for m in errors), (errors, result.stderr)
            else:
                assert result.returncode == 0, (errors, result.stderr)
                if step == "native-to-check" and case == "pure":
                    assert artifacts and all(fresh for _, fresh in artifacts), artifacts

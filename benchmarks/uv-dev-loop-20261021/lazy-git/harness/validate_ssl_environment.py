#!/usr/bin/env python3
"""Compare Cargo child certificate environments; this runs six tiny builds.

Uses a dependency-free fixture, isolated target directories, and a real external
Cargo subcommand. It does not modify uv, run tests, fetch dependencies, or disable
certificate verification. Run only after performance measurements are idle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


CERT_KEYS = ("SSL_CERT_FILE", "SSL_CERT_DIR")
CAPTURE_KEY = "CARGO_SSL_ENV_CAPTURE"

BUILD_SCRIPT = r'''
fn main() {
    let output = std::path::PathBuf::from(std::env::var_os("CARGO_SSL_ENV_CAPTURE").unwrap());
    std::fs::create_dir_all(&output).unwrap();
    for key in ["SSL_CERT_FILE", "SSL_CERT_DIR"] {
        match std::env::var_os(key) {
            Some(value) => std::fs::write(output.join(key), value.as_encoded_bytes()).unwrap(),
            None => std::fs::write(output.join(format!("{key}.unset")), b"").unwrap(),
        }
    }
    println!("cargo::rerun-if-env-changed=CARGO_SSL_ENV_CAPTURE");
}
'''

EXTERNAL_SUBCOMMAND = r'''
import os
from pathlib import Path

output = Path(os.environ["CARGO_SSL_ENV_CAPTURE"])
output.mkdir(parents=True, exist_ok=True)
for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
    if key in os.environ:
        (output / key).write_bytes(os.fsencode(os.environ[key]))
    else:
        (output / (key + ".unset")).write_bytes(b"")
'''


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_capture(path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for key in CERT_KEYS:
        value = path / key
        unset = path / f"{key}.unset"
        if value.is_file() == unset.is_file():
            raise ValueError(f"expected exactly one value/unset marker for {path / key}")
        result[key] = os.fsdecode(value.read_bytes()) if value.is_file() else None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--cert-file", type=Path, required=True)
    parser.add_argument("--cert-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--cargo-arg", action="append", default=[])
    args = parser.parse_args()

    if os.name != "posix":
        parser.error("this focused fixture requires POSIX executable scripts and environment bytes")
    executables = {
        "baseline": args.baseline.resolve(strict=True),
        "candidate": args.candidate.resolve(strict=True),
        "rustc": args.rustc.resolve(strict=True),
    }
    for executable in executables.values():
        if not executable.is_file() or not os.access(executable, os.X_OK):
            parser.error(f"not an executable file: {executable}")
    cert_file = args.cert_file.resolve(strict=True)
    cert_dir = args.cert_dir.resolve(strict=True)
    if not cert_file.is_file() or not cert_dir.is_dir():
        parser.error("--cert-file and --cert-dir must identify an existing trust bundle and directory")
    if any(character.isspace() for character in sys.executable):
        parser.error("the Python interpreter path must be usable in a POSIX shebang")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs = output / "logs"
    logs.mkdir()
    fixture = output / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "src/lib.rs").write_text("pub fn fixture() {}\n")
    (fixture / "Cargo.toml").write_text(
        "[package]\nname = 'ssl-environment-fixture'\nversion = '0.1.0'\n"
        "edition = '2024'\n\n[workspace]\n"
    )
    (fixture / "build.rs").write_text(BUILD_SCRIPT)
    cargo_home = output / "cargo-home"
    cargo_home.mkdir()
    (cargo_home / "config.toml").write_text("[net]\noffline = true\n[http]\nssl-verify = true\n")
    git_config = output / "git-config"
    git_config.write_text("")

    certificates = output / "certificates"
    certificates.mkdir()
    custom_file = certificates / "custom-trust.pem"
    shutil.copyfile(cert_file, custom_file)
    custom_dir = certificates / "custom-trust-directory"
    custom_dir.symlink_to(cert_dir, target_is_directory=True)
    scenarios = {
        "unset": {},
        "valid": {"SSL_CERT_FILE": str(custom_file), "SSL_CERT_DIR": str(custom_dir)},
        "invalid": {
            "SSL_CERT_FILE": str(certificates / "missing.pem"),
            "SSL_CERT_DIR": str(certificates / "missing-directory"),
        },
    }

    bin_dir = output / "bin"
    bin_dir.mkdir()
    external = bin_dir / "cargo-ssl-env-probe"
    external.write_text(f"#!{sys.executable}\n" + EXTERNAL_SUBCOMMAND)
    external.chmod(0o755)

    environment = os.environ.copy()
    for key in (
        *CERT_KEYS,
        "GIT_SSL_NO_VERIFY",
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
        "CARGO_BUILD_RUSTFLAGS",
        "CARGO_BUILD_TARGET",
        "CARGO_COMPLETE",
        "GIT_CONFIG_COUNT",
    ):
        environment.pop(key, None)
    environment.update(
        CARGO_HOME=str(cargo_home),
        CARGO_NET_OFFLINE="true",
        CARGO_HTTP_SSL_VERIFY="true",
        GIT_CONFIG_GLOBAL=str(git_config),
        GIT_CONFIG_NOSYSTEM="1",
        RUSTC=str(executables["rustc"]),
        PATH=str(bin_dir) + os.pathsep + environment.get("PATH", ""),
    )
    report: dict = {
        "executables": {key: {"path": str(path), "sha256": sha256(path)} for key, path in executables.items()},
        "script_sha256": sha256(Path(__file__).resolve()),
        "trust_bundle_sha256": sha256(cert_file),
        "scenarios": scenarios,
        "cargo_args": args.cargo_arg,
        "logging_environment": {
            key: environment[key] for key in ("CARGO_LOG", "CARGO_LOG_PROFILE", "CARGO_LOG_PROFILE_CAPTURE_ARGS")
            if key in environment
        },
        "results": [],
        "errors": [],
    }
    captures = {}
    for scenario, values in scenarios.items():
        for channel in ("external", "build-script"):
            for variant in ("baseline", "candidate"):
                label = f"{scenario}-{channel}-{variant}"
                capture = output / "captures" / label
                child_env = environment | values | {CAPTURE_KEY: str(capture)}
                command = [str(executables[variant]), *args.cargo_arg]
                if channel == "external":
                    command += ["ssl-env-probe"]
                else:
                    command += [
                        "build", "--offline", "--manifest-path", str(fixture / "Cargo.toml"),
                        "--target-dir", str(output / "targets" / label),
                    ]
                record = {"scenario": scenario, "channel": channel, "variant": variant, "command": command}
                with (logs / f"{label}.stdout").open("wb") as stdout, (logs / f"{label}.stderr").open("wb") as stderr:
                    try:
                        completed = subprocess.run(
                            command, cwd=fixture, env=child_env, stdout=stdout, stderr=stderr,
                            timeout=args.timeout, check=False,
                        )
                        record["returncode"] = completed.returncode
                        if completed.returncode:
                            raise ValueError(f"Cargo exited {completed.returncode}; see {logs / label}")
                        actual = read_capture(capture)
                        record["certificate_environment"] = actual
                        captures[scenario, channel, variant] = actual
                        if scenario == "valid" and actual != values:
                            raise ValueError("valid custom certificate paths were not preserved")
                    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                        record["error"] = str(error)
                        report["errors"].append(f"{label}: {error}")
                report["results"].append(record)
                (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    for scenario in scenarios:
        for channel in ("external", "build-script"):
            baseline = captures.get((scenario, channel, "baseline"))
            candidate = captures.get((scenario, channel, "candidate"))
            if baseline is None or candidate is None or baseline != candidate:
                report["errors"].append(f"{scenario}/{channel}: baseline and candidate captures differ or are missing")
        for variant in ("baseline", "candidate"):
            external_env = captures.get((scenario, "external", variant))
            build_env = captures.get((scenario, "build-script", variant))
            if external_env is None or build_env is None or external_env != build_env:
                report["errors"].append(f"{scenario}/{variant}: external and build-script captures differ or are missing")
    report["passed"] = not report["errors"]
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {output / 'report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Native-only fixture with verified checksum rsync and safe full-copy fallback."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import uuid

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
from paired import atomic_json, install_variant, run_command, sha256, utc_now


BASE = SCRIPT.parent.parent / "loader-fixtures"
VARIANTS = ("baseline", "candidate")
SCHEMA = 1
BUILD_ENVIRONMENT = {
    "PATH", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "RUSTC", "RUSTDOC", "RUSTFLAGS",
    "RUSTDOCFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_ENCODED_RUSTDOCFLAGS",
    "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTC_BOOTSTRAP",
    "RUSTC_OVERRIDE_VERSION_STRING", "RUSTC_LOG", "RUSTC_LOG_COLOR",
    "CARGO_BUILD_JOBS", "CARGO_BUILD_TARGET", "CARGO_INCREMENTAL", "CARGO_LOG",
    "CARGO_LOG_PROFILE", "CC", "CXX", "AR", "CFLAGS", "CXXFLAGS",
    "LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT", "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
}


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture_root(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        raise ValueError("fixture name must contain only lowercase letters, digits, - and _")
    root = BASE.absolute() / name
    if root.resolve() != root:
        raise ValueError("fixture paths must not contain symlinks")
    return root


def load(name):
    root = fixture_root(name)
    manifest_path = root / "fixture.json"
    if manifest_path.is_symlink():
        raise ValueError("fixture marker must not be a symlink")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != SCHEMA or manifest.get("root") != str(root):
        raise ValueError("fixture marker does not own this directory")
    if manifest.get("name") != name or not re.fullmatch(r"[0-9a-f]{32}", manifest.get("id", "")):
        raise ValueError("invalid fixture ownership marker")
    return root, manifest


@contextmanager
def locked(root):
    path = root / "lock"
    if path.is_symlink():
        raise ValueError("fixture lock must not be a symlink")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def journal(root, entry):
    with (root / "journal.jsonl").open("a") as stream:
        stream.write(json.dumps({"at": utc_now(), **entry}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def check_owned_path(root, path):
    """Validate a descendant without resolving away an unexpected symlink."""
    if root not in path.parents or path.resolve() != path or path.is_symlink():
        raise ValueError(f"path is not a plain descendant of the fixture: {path}")


def reject_mounts(path):
    # A bind mount can have the same st_dev as its parent, so consult mountinfo.
    mounts = Path("/proc/self/mountinfo")
    if not mounts.is_file():
        raise ValueError("safe cleanup currently requires Linux /proc/self/mountinfo")
    for line in mounts.read_text().splitlines():
        field = line.split()[4]
        mount = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), field))
        if mount == path or path in mount.parents:
            raise ValueError(f"refusing to remove a mounted directory: {mount}")


def remove_live(root):
    """The only recursive deletion: the fixed live child of a marked fixture."""
    loaded_root, _ = load(root.name)
    if loaded_root != root:
        raise ValueError("fixture ownership changed")
    live = root / "live"
    check_owned_path(root, live)
    reject_mounts(live)
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ValueError("this Python lacks symlink-resistant recursive deletion")
    if live.exists():
        shutil.rmtree(live)


def clone_tree(source, destination, mode):
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"copy destination must be new: {destination}")
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"copy source must be a directory: {source}")
    destination.mkdir()
    # One recursive invocation preserves hardlinks across target and shared.
    subprocess.run(
        ["cp", "-a", f"--reflink={mode}", "--", str(source) + "/.", str(destination)],
        check=True,
    )


def has_external_hardlinks(root):
    """Avoid mutating metadata through links outside the disposable live tree."""
    counts = Counter()
    links = {}
    for directory, _, files in os.walk(root, followlinks=False):
        for name in files:
            metadata = (Path(directory) / name).lstat()
            if stat.S_ISREG(metadata.st_mode):
                key = (metadata.st_dev, metadata.st_ino)
                counts[key] += 1
                links[key] = metadata.st_nlink
    return any(counts[key] != count for key, count in links.items())


def restore_tree(root, snapshot, manifest, expected):
    """Restore exact sealed state; never accept rsync's quick checks as proof."""
    live = root / "live"
    source = snapshot / "tree"
    check_owned_path(root, live)
    check_owned_path(root, source)
    reject_mounts(live)
    fallback = None
    if not live.exists():
        fallback = "live tree absent"
    elif has_external_hardlinks(live):
        # Unlinking live names is safe; updating their inode metadata is not.
        fallback = "live tree has hardlinks outside itself"
    else:
        subprocess.run([
            manifest["restore"]["rsync"], "--archive", "--hard-links", "--checksum",
            "--delete", "--modify-window=-1", "--whole-file", "--no-inplace",
            "--", str(source) + "/", str(live) + "/",
        ], check=True)
        rows = inventory(live)
        if inventory_bytes(rows) != expected:
            # In particular, rsync -H does not promise to split surplus links.
            # No timed sample can run until the existing full-copy check passes.
            fallback = "delta content/metadata/hardlink inventory mismatch"
        elif has_external_hardlinks(live):
            raise ValueError("restored live tree has external hardlinks")
        else:
            return rows, {"method": "rsync-checksum", "fallback": None}
    remove_live(root)
    clone_tree(source, live, manifest["copy"]["mode"])
    rows = inventory(live)
    if inventory_bytes(rows) != expected:
        raise ValueError("restored native state differs from its sealed snapshot")
    if has_external_hardlinks(live):
        raise ValueError("copied live tree has external hardlinks")
    return rows, {"method": "full-copy", "fallback": fallback}


def inventory(root):
    """Content, nanosecond mtime, mode, symlink and hardlink inventory."""
    rows = []
    first_link = {}
    inode_content = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        relative_directory = Path(directory).relative_to(root)
        for name in sorted(directories + files):
            path = Path(directory) / name
            relative = str(relative_directory / name)
            metadata = path.lstat()
            row = {
                "path": relative,
                "mode": stat.S_IMODE(metadata.st_mode),
                "mtime_ns": metadata.st_mtime_ns,
            }
            if stat.S_ISLNK(metadata.st_mode):
                row.update(kind="symlink", target=os.readlink(path))
            elif stat.S_ISDIR(metadata.st_mode):
                row["kind"] = "directory"
            elif stat.S_ISREG(metadata.st_mode):
                key = (metadata.st_dev, metadata.st_ino)
                first = first_link.setdefault(key, relative)
                signature = (metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns,
                             metadata.st_mode, metadata.st_nlink)
                if key in inode_content:
                    previous, content_hash = inode_content[key]
                    if signature != previous:
                        raise ValueError(f"hardlinked file changed during inventory: {path}")
                else:
                    content_hash = sha256(path)
                    after = path.lstat()
                    observed = (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                                after.st_mode, after.st_nlink)
                    if key != (after.st_dev, after.st_ino) or signature != observed:
                        raise ValueError(f"file changed during inventory: {path}")
                    inode_content[key] = (signature, content_hash)
                row.update(kind="file", size=metadata.st_size, sha256=content_hash, link=first)
            else:
                raise ValueError(f"snapshot contains an unsupported special file: {path}")
            rows.append(row)
    rows.sort(key=lambda row: row["path"])
    return rows


def inventory_bytes(rows):
    return b"".join(json_bytes(row) for row in rows)


def summarize_inventory(rows):
    files = [row for row in rows if row["kind"] == "file"]
    return {
        "entries": len(rows),
        "files": len(files),
        "logical_bytes": sum(row["size"] for row in files),
        "inventory_sha256": digest(inventory_bytes(rows)),
    }


def source_identity(workspace):
    revision = subprocess.check_output(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(workspace), "status", "--porcelain", "--untracked-files=normal"],
        text=True,
    )
    if status:
        raise ValueError("source checkout must remain clean during this experiment")
    names = subprocess.check_output(
        ["git", "-C", str(workspace), "ls-files", "-z"]
    ).split(b"\0")
    rows = []
    for name in sorted(name for name in names if name):
        path = workspace / os.fsdecode(name)
        metadata = path.lstat()
        rows.append({
            "path": os.fsdecode(name),
            "mode": stat.S_IMODE(metadata.st_mode),
            "mtime_ns": metadata.st_mtime_ns,
            "sha256": digest(os.fsencode(os.readlink(path))) if path.is_symlink() else sha256(path),
        })
    return {"revision": revision, "tracked_files": len(rows), "sha256": digest(inventory_bytes(rows))}


def check_inputs(manifest):
    if source_identity(Path(manifest["workspace"])) != manifest["source"]:
        raise ValueError("uv source revision, content, mode, or mtime changed")
    for path, expected in manifest["recorded_files"].items():
        if sha256(path) != expected:
            raise ValueError(f"recorded compiler/input file changed: {path}")


def make_environment(manifest):
    environment = os.environ.copy()
    for key, value in manifest["environment"].items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = str(value)
    return environment


def probe_copy(root, requested):
    probe = root / "copy-probe"
    probe.mkdir()
    source, destination = probe / "source", probe / "clone"
    source.write_bytes(b"ohm-loader-fixture-reflink-probe\n")
    result = subprocess.run(
        ["cp", "--reflink=always", "--", str(source), str(destination)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        mode = "always" if requested != "copy" else "never"
    elif requested == "reflink":
        raise ValueError("reflinks were requested but are unsupported on this filesystem")
    else:
        mode = "never"
    source.unlink()
    destination.unlink(missing_ok=True)
    probe.rmdir()
    return {"mode": mode, "reflink_supported": result.returncode == 0, "probe_returncode": result.returncode}


def initialize(name, template_path, candidate, baseline=None, package=None, copy_mode="auto"):
    root = fixture_root(name)
    template_path = Path(template_path).resolve()
    template = json.loads(template_path.read_text())
    command = template["command"]
    if command.count("{cargo}") != 1 or command.count("check") != 1:
        raise ValueError("template must have exactly one {cargo} and one check argument")
    if any(value.startswith("--message-format") for value in command):
        raise ValueError("template must not already select a message format")
    if command.index("check") < command.index("{cargo}"):
        raise ValueError("template check must be an argument to Cargo")
    environments = template.get("variant_env", {})
    if environments.get("baseline", {}) != environments.get("candidate", {}):
        raise ValueError("variant environments must be identical")
    environment = {**template.get("env", {}), **environments.get("baseline", {})}
    build_names = BUILD_ENVIRONMENT | {
        key for key in os.environ if key.startswith(("CARGO_PROFILE_", "CARGO_UNSTABLE_"))
    }
    for key in build_names:
        environment.setdefault(key, os.environ.get(key))
    environment = {key: None if value is None else str(value) for key, value in environment.items()}
    if not environment.get("CARGO_HOME"):
        raise ValueError("template must explicitly identify the package-cache CARGO_HOME")
    package_source = Path(environment["CARGO_HOME"]).resolve()
    if any((package_source / name).exists() for name in ("config", "config.toml")):
        raise ValueError("package-cache config needs explicit review before an isolated copy")
    workspace = Path(template["cwd"]).resolve()
    variants = {
        "baseline": str(Path(baseline or template["variants"]["baseline"]).resolve()),
        "candidate": str(Path(candidate).resolve()),
    }
    hashes = {}
    for variant, path in variants.items():
        if not Path(path).is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"{variant} must be an existing executable")
        hashes[variant] = sha256(path)
    recorded_files = {str(Path(path).resolve()): sha256(path) for path in template.get("record_files", [])}
    recorded_files.update({str(path): sha256(path) for path in (SCRIPT, SCRIPT.parent / "paired.py")})
    rsync = shutil.which("rsync")
    if rsync is None:
        raise ValueError("verified delta restoration requires rsync")
    rsync = str(Path(rsync).resolve())
    recorded_files[rsync] = sha256(rsync)
    rsync_version = subprocess.check_output([rsync, "--version"], text=True)
    source = source_identity(workspace)
    root.parent.mkdir(exist_ok=True)
    root.mkdir(exist_ok=False)
    for directory in ("bin", "logs", "snapshots"):
        (root / directory).mkdir()
    copying = probe_copy(root, copy_mode)
    environment.update({
        "CARGO_HOME": str(root / "package-home"),
        "CARGO_TARGET_DIR": str(root / "live" / "target"),
        "CARGO_BUILD_BUILD_DIR": str(root / "live" / "shared"),
        "LD_LIBRARY_PATH": None,
    })
    check_command = list(command)
    if package:
        check_command += ["--package", package]
    check_command += ["--message-format=json", "-v"]
    seed_command = list(check_command)
    index = seed_command.index("check")
    seed_command[index:index + 1] = ["test", "--no-run"]
    manifest = {
        "schema_version": SCHEMA, "id": uuid.uuid4().hex, "name": name,
        "root": str(root), "created_at": utc_now(), "workspace": str(workspace),
        "source": source, "template": str(template_path), "template_sha256": sha256(template_path),
        "variants": variants, "variant_sha256": hashes, "recorded_files": recorded_files,
        "canonical_executable": str(root / "bin" / "cargo"),
        "environment": environment, "package_cache_source": str(package_source),
        "package": package, "seed_command": seed_command, "check_command": check_command,
        "copy": copying, "verification": "Full content and metadata inventory after every restore",
        "restore": {"method": "rsync-checksum-with-verified-copy-fallback", "rsync": rsync,
                    "version": rsync_version, "checksum_is_not_final_proof": True},
    }
    atomic_json(root / "fixture.json", manifest)
    configuration = {
        "cwd": str(workspace), "canonical_executable": manifest["canonical_executable"],
        "variants": variants, "command": check_command, "env": environment,
        "record_files": list(recorded_files) + [str(root / "fixture.json")],
        "prepare_command": [
            sys.executable, str(SCRIPT), "prepare", "--name", name,
            "--variant", "{variant}", "--batch", "{output}", "--stage", "{stage}",
            "--pair", "{pair}", "--position", "{position}",
        ],
    }
    atomic_json(root / "paired.json", configuration)
    journal(root, {"operation": "initialize", "source": source, "copy": copying})
    return manifest


def prepare_package_home(root, manifest):
    home = root / "package-home"
    marker = root / "package-home.ready.json"
    if marker.exists():
        return
    if home.exists():
        raise ValueError("incomplete package-home copy; inspect it before retrying")
    home.mkdir()
    copied = []
    source = Path(manifest["package_cache_source"])
    # Never copy credentials, user configuration, binaries, or the existing global DB.
    for name in ("registry", "git"):
        path = source / name
        if path.exists():
            clone_tree(path, home / name, manifest["copy"]["mode"])
            copied.append(name)
    atomic_json(marker, {"source": str(source), "copied": copied, "at": utc_now()})


def runlist(stdout_path, stderr_path):
    artifacts = []
    build_script_outputs = []
    for line in stdout_path.read_text().splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("reason") == "compiler-artifact":
            artifacts.append({
                "package_id": message["package_id"], "target": message["target"]["name"],
                "kind": message["target"]["kind"], "profile": message["profile"],
                "fresh": message["fresh"], "filenames": message["filenames"],
                "executable": message.get("executable"),
            })
        elif message.get("reason") == "build-script-executed":
            # Cargo emits this for cached output too; only verbose Running lines
            # establish that a build-script subprocess actually ran.
            build_script_outputs.append({
                "package_id": message["package_id"], "out_dir": message["out_dir"],
            })
    invocations = []
    other_invocations = []
    text = stderr_path.read_text()
    for line in text.splitlines():
        if "Running " not in line or chr(96) not in line:
            continue
        rendered = line.split(chr(96), 1)[1].rsplit(chr(96), 1)[0]
        arguments = shlex.split(rendered)
        if "--crate-name" not in rendered:
            other_invocations.append(arguments)
            continue
        emits = next((arg.split("=", 1)[1] for arg in arguments if arg.startswith("--emit=")), None)
        if emits is None and "--emit" in arguments:
            emits = arguments[arguments.index("--emit") + 1]
        crate = arguments[arguments.index("--crate-name") + 1]
        invocations.append({"crate": crate, "emit": [] if emits is None else emits.split(",")})
    checking = re.findall(r"^\s*Checking\s+(\S+)\s+v\S+", text, re.MULTILINE)
    return {
        "artifacts": artifacts, "rustc_invocations": invocations,
        "other_invocations": other_invocations, "build_script_outputs": build_script_outputs,
        "checking_packages": checking,
    }


def provenance_summary(tree):
    counts = Counter()
    for path in tree.glob("shared/*/build/registries/*/*/*/fingerprint/ohm-message-provenance-*"):
        row = json.loads(path.read_text())
        key = (row.get("loader_injected"), tuple(row.get("compiler_search_directories", [])))
        counts[key] += 1
    return [
        {"loader_injected": key[0], "compiler_search_directories": list(key[1]), "count": count}
        for key, count in sorted(counts.items(), key=lambda item: repr(item[0]))
    ]


def seed(name, variant):
    if variant not in VARIANTS:
        raise ValueError("unknown variant")
    root, manifest = load(name)
    with locked(root):
        snapshot = root / "snapshots" / variant
        check_owned_path(root, snapshot)
        if snapshot.exists():
            raise ValueError("snapshot already exists; create a new fixture to reseed")
        check_inputs(manifest)
        prepare_package_home(root, manifest)
        remove_live(root)
        (root / "live" / "target").mkdir(parents=True)
        (root / "live" / "shared").mkdir()
        executable = Path(manifest["canonical_executable"])
        check_owned_path(root, executable)
        variant_path = Path(manifest["variants"][variant])
        if sha256(variant_path) != manifest["variant_sha256"][variant]:
            raise ValueError("variant binary changed since fixture initialization")
        install_variant(variant_path, executable)
        command = [str(executable) if value == "{cargo}" else value for value in manifest["seed_command"]]
        stdout = root / "logs" / f"seed-{variant}.stdout"
        stderr = root / "logs" / f"seed-{variant}.stderr"
        journal(root, {"operation": "seed-start", "variant": variant, "command": command, "empty_live": True})
        result = run_command(command, manifest["workspace"], make_environment(manifest), stdout, stderr)
        if result["returncode"]:
            journal(root, {"operation": "seed-failed", "variant": variant, "result": result})
            raise RuntimeError(f"native seed failed; inspect {stderr}")
        check_inputs(manifest)
        if sha256(executable) != manifest["variant_sha256"][variant]:
            raise ValueError("canonical executable changed during native seed")
        runs = runlist(stdout, stderr)
        if not runs["artifacts"] or not runs["rustc_invocations"]:
            raise ValueError("seed lacks compiler-artifact messages or verbose rustc evidence")
        if runs["checking_packages"] or any("link" not in row["emit"] for row in runs["rustc_invocations"]):
            raise ValueError("seed contained metadata-only checking; not a native-only seed")
        snapshot.mkdir()
        clone_tree(root / "live", snapshot / "tree", manifest["copy"]["mode"])
        rows = inventory(snapshot / "tree")
        (snapshot / "inventory.jsonl").write_bytes(inventory_bytes(rows))
        atomic_json(snapshot / "runlist.json", runs)
        record = {
            "schema_version": SCHEMA, "fixture_id": manifest["id"], "variant": variant,
            "created_at": utc_now(), "command": command, "source": manifest["source"],
            "environment": manifest["environment"], "cargo_sha256": sha256(executable),
            "canonical_executable": str(executable), "tree": str(snapshot / "tree"),
            "native_only": True, "empty_live_before_seed": True, "result": result,
            "stdout_sha256": sha256(stdout), "stderr_sha256": sha256(stderr),
            "runlist_sha256": sha256(snapshot / "runlist.json"),
            "provenance": provenance_summary(snapshot / "tree"), **summarize_inventory(rows),
        }
        atomic_json(snapshot / "manifest.json", record)
        journal(root, {"operation": "seed-complete", "variant": variant, "snapshot": record})
        return record


def prepare(name, variant, batch, stage, pair, position, environment=None):
    if variant not in VARIANTS or stage not in ("warmup", "measurement") or pair < 0 or position not in (0, 1):
        raise ValueError("invalid sample identity")
    root, manifest = load(name)
    environment = os.environ if environment is None else environment
    with locked(root):
        check_inputs(manifest)
        for key, value in manifest["environment"].items():
            if environment.get(key) != value:
                raise ValueError(f"sample environment differs from its seed: {key}")
        if sha256(manifest["canonical_executable"]) != manifest["variant_sha256"][variant]:
            raise ValueError("paired runner installed the wrong Cargo binary")
        snapshot = root / "snapshots" / variant
        check_owned_path(root, snapshot)
        record = json.loads((snapshot / "manifest.json").read_text())
        if record["fixture_id"] != manifest["id"] or record["variant"] != variant or not record["native_only"]:
            raise ValueError("snapshot ownership or native-only provenance mismatch")
        if record["cargo_sha256"] != manifest["variant_sha256"][variant]:
            raise ValueError("snapshot was produced by a different Cargo binary")
        expected = (snapshot / "inventory.jsonl").read_bytes()
        if digest(expected) != record["inventory_sha256"]:
            raise ValueError("snapshot inventory was changed")
        started = time.perf_counter_ns()
        rows, restoration = restore_tree(root, snapshot, manifest, expected)
        actual = inventory_bytes(rows)
        if actual != expected:
            raise ValueError("restored native state differs from its sealed snapshot")
        entry = {
            "operation": "prepare", "batch": str(Path(batch).resolve()), "stage": stage,
            "pair": pair, "position": position, "variant": variant,
            "snapshot_manifest_sha256": sha256(snapshot / "manifest.json"),
            "inventory_sha256": digest(actual), "cargo_sha256": record["cargo_sha256"],
            "canonical_executable": manifest["canonical_executable"],
            "target": manifest["environment"]["CARGO_TARGET_DIR"],
            "shared": manifest["environment"]["CARGO_BUILD_BUILD_DIR"],
            "restore_wall_ns": time.perf_counter_ns() - started,
            "full_content_verification": True,
            "restoration": restoration,
        }
        journal(root, entry)
        return entry


def verify(name, results):
    root, manifest = load(name)
    results = Path(results).resolve()
    run_manifest = json.loads((results / "manifest.json").read_text())
    samples = json.loads((results / "samples.json").read_text())
    entries = [json.loads(line) for line in (root / "journal.jsonl").read_text().splitlines()]
    prepared = {}
    errors = []
    for entry in entries:
        if entry["operation"] == "prepare" and entry["batch"] == str(results):
            key = (entry["stage"], entry["pair"], entry["position"], entry["variant"])
            if key in prepared:
                errors.append(f"duplicate restoration: {key}")
            prepared[key] = entry
    if run_manifest.get("state") != "complete" or not samples:
        errors.append("paired run did not complete with samples")
    summaries = []
    seen = set()
    for sample in samples:
        key = (sample["stage"], sample["pair"], sample["position"], sample["variant"])
        entry = prepared.get(key)
        if key in seen or entry is None:
            errors.append(f"duplicate sample or missing restoration: {key}")
            continue
        seen.add(key)
        snapshot = root / "snapshots" / sample["variant"]
        if entry["snapshot_manifest_sha256"] != sha256(snapshot / "manifest.json"):
            errors.append(f"snapshot manifest changed: {key}")
        if sample["returncode"] or sample["installed_sha256"] != entry["cargo_sha256"]:
            errors.append(f"failed sample or wrong executable: {key}")
        expected_command = [
            manifest["canonical_executable"] if value == "{cargo}" else value
            for value in manifest["check_command"]
        ]
        if sample["command"] != expected_command:
            errors.append(f"timed command differs from fixture: {key}")
        runs = runlist(Path(sample["stdout"]), Path(sample["stderr"]))
        summaries.append({
            "sample": list(key), "checking_packages": runs["checking_packages"],
            "rustc_invocations": runs["rustc_invocations"],
            "other_invocations": runs["other_invocations"],
            "build_script_outputs": runs["build_script_outputs"],
            "fresh_artifacts": sum(row["fresh"] for row in runs["artifacts"]),
            "compiled_artifacts": sum(not row["fresh"] for row in runs["artifacts"]),
            "inventory_sha256": entry["inventory_sha256"],
            "restore_wall_ns_excluded": entry["restore_wall_ns"],
        })
    if seen != set(prepared):
        errors.append("restoration runlist and measured samples differ")
    check_inputs(manifest)
    report = {"valid": not errors, "errors": errors, "samples": summaries, "source": manifest["source"]}
    atomic_json(results / "loader-fixture-validation.json", report)
    if errors:
        raise ValueError("; ".join(errors))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    init = commands.add_parser("init")
    init.add_argument("--name", required=True)
    init.add_argument("--template", required=True)
    init.add_argument("--candidate", required=True)
    init.add_argument("--baseline")
    init.add_argument("--package")
    init.add_argument("--copy-mode", choices=("auto", "reflink", "copy"), default="auto")
    producer = commands.add_parser("seed")
    producer.add_argument("--name", required=True)
    producer.add_argument("--variant", choices=VARIANTS, required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--name", required=True)
    prepare_parser.add_argument("--variant", choices=VARIANTS, required=True)
    prepare_parser.add_argument("--batch", required=True)
    prepare_parser.add_argument("--stage", choices=("warmup", "measurement"), required=True)
    prepare_parser.add_argument("--pair", type=int, required=True)
    prepare_parser.add_argument("--position", type=int, required=True)
    validation = commands.add_parser("verify")
    validation.add_argument("--name", required=True)
    validation.add_argument("--results", required=True)
    args = parser.parse_args()
    if args.operation == "init":
        result = initialize(args.name, args.template, args.candidate, args.baseline, args.package, args.copy_mode)
    elif args.operation == "seed":
        result = seed(args.name, args.variant)
    elif args.operation == "prepare":
        result = prepare(args.name, args.variant, args.batch, args.stage, args.pair, args.position)
    else:
        result = verify(args.name, args.results)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

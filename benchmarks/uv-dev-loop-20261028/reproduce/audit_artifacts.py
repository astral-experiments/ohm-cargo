"""Verify a fresh uv command returns and preserves the same artifacts for both Cargo binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import BENCH, COMMANDS, RUST, WORK


def snapshot(paths):
    hashes = {}
    result = {}
    for path in sorted(paths):
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino)
        if key not in hashes:
            with path.open("rb") as f:
                hashes[key] = hashlib.file_digest(f, "sha256").hexdigest()
        result[str(path)] = (stat.st_size, stat.st_mtime_ns, hashes[key])
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("endpoint", choices=COMMANDS)
    p.add_argument("base", type=Path)
    p.add_argument("head", type=Path)
    p.add_argument("result", type=Path)
    p.add_argument("--target", required=True)
    p.add_argument("--source", type=Path, default=WORK / "uv")
    p.add_argument("--cargo-home", type=Path, default=BENCH / "cargo")
    a = p.parse_args()
    a.result.mkdir(exist_ok=False, parents=True)
    target = BENCH / f"target-{a.target}"
    slot = WORK / f"bin/measured-{a.target}/cargo"
    slot.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=f"{RUST}:{os.environ['PATH']}", CARGO_HOME=str(a.cargo_home),
               CARGO_NET_OFFLINE="true", CARGO_TARGET_DIR=str(target), CARGO_TERM_COLOR="never",
               RUSTC=str(RUST / "rustc"), RUSTDOC=str(RUST / "rustdoc"))
    records = {}
    summaries = {}
    for label, binary in (("base", a.base), ("head", a.head)):
        tmp = slot.with_suffix(".audit")
        os.link(binary.resolve(), tmp)
        os.replace(tmp, slot)
        tmp.unlink(missing_ok=True)
        cmd = [str(slot), *COMMANDS[a.endpoint], "--locked", "--offline", "-j16", "--message-format=json"]
        product_paths = set()
        messages = []
        with (a.result / f"{label}.log").open("wb") as log:
            output = subprocess.run(cmd, cwd=a.source, env=env, stdout=subprocess.PIPE, stderr=log, check=True)
        for line in output.stdout.splitlines():
            event = json.loads(line)
            if event["reason"] == "compiler-artifact":
                if not event["fresh"]:
                    raise ValueError(f"{label} rebuilt {event['target']['name']}")
                product_paths.update(map(Path, event["filenames"]))
                messages.append(json.dumps(event, sort_keys=True))
        if not messages:
            raise ValueError("no artifact messages returned")
        depfiles = set((target / "debug").glob("*.d"))
        observed = snapshot(product_paths | depfiles)
        records[label] = (sorted(messages), observed)
        summaries[label] = {"artifact_messages": len(messages), "product_paths": len(product_paths),
                            "depfiles": len(depfiles), "bytes": sum(x[0] for x in observed.values())}
        (a.result / f"{label}.json").write_text(json.dumps(observed, indent=2) + "\n")
    if records["base"] != records["head"]:
        raise ValueError("artifact roster, mtime, or digest differed")
    print(json.dumps(summaries, indent=2))
    (a.result / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()

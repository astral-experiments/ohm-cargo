"""One command inside the canonical mount namespace. Only the subprocess is timed."""

import argparse
import json
from pathlib import Path
import subprocess
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (
    FROZEN,
    MATCH_FILE,
    MODE_COUNTS,
    NEEDLE,
    PIN,
    RUFF,
    SONAME,
    diagnostics,
    dump,
    elf,
    env,
    git,
    load,
    need,
    sha,
    trace,
)


def stamp(path):
    st = path.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def run(out, mode, phase, arm, expected_cargo, expected_driver, reference):
    edited = phase == "edit"
    timed = phase.startswith("pair-")
    need(
        sha(FROZEN / "bin/cargo") == expected_cargo and sha(FROZEN / "lib" / SONAME) == expected_driver,
        "subject mount mismatch",
    )
    need(
        git("rev-parse", "HEAD") == PIN and MATCH_FILE.read_bytes().count(NEEDLE) == (0 if edited else 1),
        "Ruff source mismatch",
    )
    out.mkdir()
    config = env()
    command = ["cargo", "+ohm", mode] + (["--no-run"] if mode == "test" else []) + ["--locked", "--offline"]
    ref = load(reference) if reference else None
    before = {p: stamp(Path(p)) for p in ref["elf"]} if timed else {}
    if not timed:
        command += ["--message-format=json"]
        command = [
            "strace",
            "-ff",
            "-qq",
            "-s",
            "65536",
            "-e",
            "trace=execve,execveat",
            "-o",
            str(out / "exec"),
            *command,
        ]
    with (out / "stdout").open("wb") as stdout, (out / "stderr").open("wb") as stderr:
        start = time.monotonic_ns()
        result = subprocess.run(command, env=config, cwd=RUFF, stdout=stdout, stderr=stderr)
        ns = time.monotonic_ns() - start
    info = dict(
        argv=command,
        elapsed_ns=ns,
        returncode=result.returncode,
        timed=timed,
        arm=arm,
        mode=mode,
        phase=phase,
    )
    dump(out / "invocation.json", info)
    err = (out / "stderr").read_text()
    need(result.returncode == 0 and "Blocking waiting" not in err, [str(out), err[-2200:]])
    if timed:
        status = [
            s.strip()
            for s in err.splitlines()
            if s.lstrip().startswith(("Compiling ", "Checking ", "Running "))
        ]
        if arm == "candidate":
            need(
                not status and before == {p: stamp(Path(p)) for p in before},
                ("candidate did physical work", out, status),
            )
        info.update(
            compile_status=status,
            candidate_elf_stats_unchanged=(True if arm == "candidate" else None),
            diagnostics=diagnostics(Path(ref["ruff"]), False),
        )
        need(info["diagnostics"] == ref["diagnostics"], ["changed timed diagnostic", out])
        dump(out / "receipt.json", info)
        return
    rows = [json.loads(line) for line in (out / "stdout").read_bytes().splitlines() if line]
    arts = [x for x in rows if x["reason"] == "compiler-artifact"]
    need(rows and rows[-1] == {"reason": "build-finished", "success": True}, out)
    count, native = MODE_COUNTS[mode]
    need(len(arts) == count, (mode, len(arts), count))
    roster = sorted(
        json.dumps(
            {
                k: a[k]
                for k in (
                    "package_id",
                    "manifest_path",
                    "target",
                    "profile",
                    "features",
                    "filenames",
                    "executable",
                )
            },
            sort_keys=True,
        )
        for a in arts
    )
    paths = {Path(p) for a in arts if a["package_id"].startswith("path+") for p in a["filenames"]}
    elf_files = {}
    for p in sorted(paths):
        if p.suffix not in {"", ".so"}:
            continue
        with p.open("rb") as f:
            magic = f.read(4)
        if magic == b"\x7fELF":
            elf_files[str(p)] = elf(p)
    need(len(elf_files) == native, [out, "workspace ELF count", len(elf_files), native])
    dump(out / "elf.json", elf_files)
    exe = sorted({a["executable"] for a in arts if a["executable"]})
    need(
        len(exe) == (6 if mode == "build" else 102) and set(exe) <= elf_files.keys(),
        ("missing executable ELF", set(exe) - elf_files.keys()),
    )
    (ruff,) = {
        a["executable"]
        for a in arts
        if a["executable"]
        and a["target"]["name"] == "ruff"
        and a["target"]["kind"] == ["bin"]
        and not a["profile"]["test"]
    }
    dirty = sorted(
        json.dumps([a["package_id"], a["target"]["name"], a["target"]["kind"], a["profile"]["test"]])
        for a in arts
        if not a["fresh"]
    )
    physical = trace(out)
    loaded = [
        p
        for _, p in physical["executions"]
        if Path(p).name == "cargo" and Path(p).is_file() and Path(p).samefile(FROZEN / "bin/cargo")
    ]
    need(loaded, ("trace did not execute selected Cargo", out, physical["executions"][:8]))
    info["selected_cargo_exec"] = loaded
    need(
        not (set(exe) & set(physical["target_execs"])),
        ["built program or test executed", out, set(exe) & set(physical["target_execs"])],
    )
    dump(out / "trace.json", physical)
    if phase in {"preflight", "final", "restored-noop"} and arm == "candidate":
        need(
            not dirty and not physical["rustc"] and not physical["linkers"] and not physical["target_execs"],
            ["candidate no-op dirtiness", out, dirty, physical],
        )
    messages = sorted(
        json.dumps([a["package_id"], a["target"]["name"], a["message"]], sort_keys=True)
        for a in rows
        if a["reason"] == "compiler-message"
    )
    info.update(
        diagnostics=diagnostics(Path(ruff), edited),
        compiler_messages=messages,
        dirty=dirty,
        roster=roster,
        units=count,
        executables=exe,
        elf=elf_files,
        ruff=ruff,
        rustc=physical["rustc"],
        linkers=physical["linkers"],
        cargo=expected_cargo,
        driver=expected_driver,
    )
    dump(out / "receipt.json", info)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    p.add_argument("mode", choices=MODE_COUNTS)
    p.add_argument("phase")
    p.add_argument("arm", choices=["parent", "candidate"])
    p.add_argument("cargo")
    p.add_argument("driver")
    p.add_argument("--reference", type=Path)
    a = p.parse_args()
    run(a.out, a.mode, a.phase, a.arm, a.cargo, a.driver, a.reference)

"""Independently read a completed local run and project its raw process and timing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess as sp
import sys


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def check(ok, msg):
    if not ok:
        raise ValueError(str(msg))


def project(root):
    enc = read(root / "enrollment.json")
    run = read(root / "result.json")
    check(run["status"] == "passed" and run["enrollment"] == sha(root / "enrollment.json"), "run did not finish")
    runner = root / "runner"
    for name, claimed in enc["runner"].items():
        check(sha(runner / name) == claimed, name)
    check(run["data"] == sha(root / "wall/paired-wall.json"), "statistic binding")
    rawfn = runpy.run_path(str(runner / "native_execs.py"))
    modes = ["build", "test"] if enc["workload"] == "both" else [enc["workload"]]
    recalculated = sp.check_output([sys.executable, "-IB", str(runner / "analyze.py"), str(root / "wall/results"), *modes])
    check(json.loads(recalculated) == read(root / "wall/paired-wall.json"), "statistical reread")
    result = {"kind": enc["kind"], "workload": enc["workload"], "cargo": [enc["cargo_a"], enc["cargo_b"]],
              "rustc": enc["runtime_rustc"], "driver": enc["driver"], "wild": enc["runtime_wild"],
              "sdk_marker": enc["sdk_marker"], "source_build_receipt": enc["build_receipt"],
              "upstream_runner_manifest": enc["original_manifest"], "cpus": enc["cpus"],
              "space_reserve_gib": enc["reserve_gib"], "statistics": json.loads(recalculated),
              "guards": {}, "chronology": {}, "ordinary_streams": {}, "products": {}, "raw_index_sha256": {}}
    for study in ("mechanism", "wall"):
        check(read(root / study / "exit.json")["exit"] == 0, study)
        rows = []
        files = {}
        for mode in modes:
            base = root / study / "results" / ("toml-" + mode + "-v1")
            samples = read(base / "terminal.json")
            check(samples["base"] == enc["cargo_a"] and samples["candidate"] == enc["cargo_b"], "arm verification")
            names = ("00-prepare", "01-edited", "02-restored", "03-settled", "99-terminal")
            if study == "mechanism":
                names += ("04-reverse", "05-repeat", "06-restore", "07-repeat")
            same_runtime = read(base / "C/runtime-identity.json")
            reference = None
            for arm in "CAB":
                lane = base / arm
                binding = read(lane / "enrollment.json")
                check(read(lane / "runtime-identity.json") == same_runtime and len(same_runtime) == 4, "runtime inode or paths differed")
                check(binding["rust"] == enc["runtime_rustc"] and binding["wild"] == enc["runtime_wild"], "toolchain mismatch")
                check(binding["cargo"] == enc["cargo_b" if arm == "B" else "cargo_a"], "per-arm image")
                for tag in (("00-prepare", "00-frozen") if arm == "C" else names):
                    stem = lane / tag
                    data = read(stem.with_suffix(".json"))
                    execs = rawfn["native_execs"](stem.with_suffix(".exec").read_bytes())
                    roles = [[r["program"], rawfn["is_compile"](r), rawfn["is_link"](r)] for r in execs]
                    check(data["exec"] == roles and [r["cargo_args"] for r in execs[:2]] ==
                          [["+ohm", *binding["argv"], "--message-format=json"], [*binding["argv"], "--message-format=json"]], "native argv or counts")
                    compiles, links = [sum(role[n] for role in roles) for n in (1, 2)]
                    objects = [json.loads(line) for line in stem.with_suffix(".jsonl").read_bytes().splitlines()]
                    arts = [r for r in objects if r["reason"] == "compiler-artifact"]
                    check(objects[-1] == {"reason":"build-finished","success":True} and arts, "typed verdict")
                    cold = arm == "C" and tag == "00-prepare"
                    if not cold:
                        check(not compiles and not links and all(r["fresh"] for r in arts), "unsettled command")
                    else:
                        check((compiles, links) == ((1, 0) if mode == "build" else (15, 6)), "different warmup work")
                    proof = {k: data[k] for k in ("roster", "files", "oracle")}
                    if reference is None:
                        reference = proof
                    check(proof == reference, "unequal product or caller")
                    real = stem.with_suffix(".stderr").read_bytes()
                    row = dict(workload=mode, arm=arm, stage=tag, rustc=compiles, links=links,
                               typed_artifacts=len(arts), trace_sha256=sha(stem.with_suffix(".exec")),
                               stdout_sha256=sha(stem.with_suffix(".jsonl")), stderr_sha256=sha(stem.with_suffix(".stderr")))
                    if study == "mechanism":
                        full = real.count(b"resolve_with_registry:resolve_with_previous:register_patch_entries:")
                        hits = real.count(b"reusing the cached workspace resolution")
                        check((full, hits) == (data["full"], data["hits"]), "resolver event count")
                        check(full + hits > 0, "missing resolver events")
                        if arm in ("A", "B") and tag not in ("00-prepare", "99-terminal"):
                            edited = tag in ("01-edited", "02-restored", "04-reverse", "06-restore")
                            check((full > 0) == (arm == "A" and edited), "resolver path")
                        row.update(full=full, hits=hits)
                    rows.append(row)
            result["products"][study + "-" + mode] = {"files": reference["files"], "oracle": reference["oracle"],
                                                       "runtime_roles": sorted(same_runtime), "same_physical_runtime": True}
            if study == "wall":
                result["chronology"][mode] = samples["events"]
                streams = []
                for event in samples["events"]:
                    stem = base / event["arm"] / (f'{event["pair"]:02}-' + event["phase"])
                    report = read(stem.with_suffix(".json"))
                    streams.append({"exit": report["exit"], "ns": report["ns"], "stdout": stem.with_suffix(".stdout").read_text(),
                                    "stderr": stem.with_suffix(".stderr").read_text()})
                result["ordinary_streams"][mode] = streams
            # This index binds each private original without publishing paths from its contents.
            files.update({p.relative_to(base.parent).as_posix(): sha(p) for p in base.rglob("*") if p.is_file()})
        result["raw_index_sha256"][study] = hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        result["guards"][study] = rows
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output_directory", type=Path)
    print(json.dumps(project(ap.parse_args().output_directory), indent=2, sort_keys=True))

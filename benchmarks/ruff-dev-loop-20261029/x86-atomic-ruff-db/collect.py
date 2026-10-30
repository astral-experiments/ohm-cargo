"""Project Cargo results, genuine process invocations and independent program verdicts."""

import argparse
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re

W = "ad005f99d0b51fd62b5c237bc13b31b371a1686e"
X = "b9b4105463dd4a9a16f39509d868aa15d5f96e00"
CARGO = "96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5"
WILD = "0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5"
CASES = [
    "system::memory_fs::tests::" + s
    for s in (
        "remove_non_empty_directory",
        "remove_directory",
        "remove_non_existing_directory",
    )
]
EXEC = re.compile(
    r'^execve\(("(?:[^"\\]|\\.)*"), (\[.*\]), (?:0x[\da-f]+(?: /\* [^*]* \*/)?|NULL|\[.*\])\)\s+= 0$'
)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def blob(p):
    return gzip.decompress(p.read_bytes())


def atomic_json(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":")).encode()


def reassemble(stream):
    pending = None
    split = 0
    for line in stream.splitlines():
        if line.startswith("execve(") and line.endswith("<unfinished ...>"):
            assert pending is None
            pending = line.removesuffix("<unfinished ...>")
            continue
        if line.startswith("<... execve resumed>"):
            assert pending is not None
            line = pending + line.removeprefix("<... execve resumed>")
            pending = None
            split += 1
        if line.startswith("execve(") and re.search(r"= 0\s*$", line):
            m = EXEC.fullmatch(line)
            assert m, line[:180]
            argv = ast.literal_eval(m[2])
            exe = ast.literal_eval(m[1])
            assert (
                isinstance(exe, str)
                and isinstance(argv, list)
                and all(isinstance(a, str) for a in argv)
            )
            yield exe, argv, split
            split = 0
    assert pending is None and split == 0


def option(argv, key):
    assert argv.count(key) == 1, (key, argv[:4])
    return argv[argv.index(key) + 1]


def arm(d):
    terminal = read(d / "terminal.json")
    assert not (d / "failure.json").exists()
    obs = terminal["observations"]
    subj = read(d / "subjects.json")
    assert subj["commit"] == terminal["subject"] == {"P": W, "Q": X}[terminal["arm"]]
    assert subj["cargo"] == CARGO and subj["stock"] == WILD
    aliases = {"rustc": set(), "wild": set()}
    for path in d.glob("*.aliases.json"):
        for name, vals in read(path).items():
            aliases[name].update(vals)
    assert len(aliases["rustc"]) == len(aliases["wild"]) == 1
    phases = {}
    for tag, (reported, outputs) in sorted(obs["jobs"].items()):
        raw = blob(d / (tag + ".exec.json.gz"))
        streams = json.loads(raw)
        jobs = []
        cats = Counter()
        split = 0
        for pid, stream in streams.items():
            assert re.fullmatch(r"exec\.[0-9]+", pid)
            for exe, av, joined in reassemble(stream):
                split += joined
                if exe in aliases["rustc"]:
                    link_only = "link-only" in av or any(
                        s.startswith("-Zlink-only") for s in av
                    )
                    if link_only:
                        kind = "cached"
                        label = (
                            option(av, "--crate-name") if "--crate-name" in av else ""
                        )
                    elif "--crate-name" in av and "--out-dir" in av:
                        kind = "full"
                        label = option(av, "--crate-name")
                    else:
                        cats["other_rustc"] += 1
                        continue
                elif exe in aliases["wild"]:
                    kind = "wild"
                    label = Path(option(av, "-o")).name
                else:
                    assert not (
                        Path(exe).name == "rustc"
                        and (
                            "link-only" in av
                            or "--crate-name" in av
                            and "--out-dir" in av
                        )
                    ), (tag, exe)
                    assert not (
                        Path(exe).name in ("ld.bfd", "wild", "ld.wild") and "-o" in av
                    ), (tag, exe)
                    continue
                cats[kind] += 1
                jobs.append([kind, label, digest(atomic_json(av))])
        assert Counter(reported) == Counter(j[1] for j in jobs if j[0] == "full")
        assert Counter(Path(o).name for o in outputs) == Counter(
            j[1] for j in jobs if j[0] == "wild"
        )
        assert not cats["cached"]
        stdout = blob(d / (tag + ".stdout.gz"))
        rows = [json.loads(l) for l in stdout.splitlines()]
        valid = not tag.startswith("invalid-")
        assert rows[-1] == {"reason": "build-finished", "success": valid}
        errors = [
            m["message"]
            for m in rows
            if m["reason"] == "compiler-message"
            and m["message"].get("code")
            and m["message"]["level"] == "error"
        ]
        assert [e["code"]["code"] for e in errors] == ([] if valid else ["E0425"])
        if errors:
            assert "ohm_missing_directory_error" in errors[0]["message"]
        units = [m for m in rows if m["reason"] == "compiler-artifact"]
        assert any(
            u["target"]["name"] == "portable_atomic"
            and u["features"] == ["default", "fallback"]
            for u in units
        )
        rec = {
            "jobs": sorted(jobs),
            "other_rustc": cats["other_rustc"],
            "typed": len(units),
            "fresh": sum(u["fresh"] for u in units),
            "trace_files": len(streams),
            "rejoined": split,
            "exec_sha256": digest(raw),
            "cargo_sha256": digest(stdout),
            "errors": [e["code"]["code"] for e in errors],
            "runtime": [],
        }
        if valid:
            act = "build" if "-build" in tag else "test"
            source = "old" if tag.startswith(("original-", "reverted-")) else "new"
            product = obs["products"][source + "/" + act]
            if act == "build":
                output = blob(d / (tag + "-reader-run.stdout.gz"))
                assert product["verdict"] == output.decode().strip()
                rec["runtime"] = [output.decode().strip()]
            else:
                inventory = (
                    blob(d / (tag + "-inventory.stdout.gz")).decode().splitlines()
                )
                assert (
                    sorted(l[:-6] for l in inventory if l.endswith(": test"))
                    == product["inventory"]
                )
                assert (
                    set(CASES) <= set(product["inventory"])
                    and len(product["inventory"]) > 50
                )
                rec["inventory_sha256"] = digest(atomic_json(product["inventory"]))
                for i, name in enumerate(CASES):
                    result = blob(d / (tag + f"-test-{i}.stdout.gz")).decode()
                    verdict = "FAILED" if source == "old" and i == 0 else "ok"
                    assert "test " + name + " ... " + verdict in result
                    if verdict == "FAILED":
                        assert "Other" in result and "DirectoryNotEmpty" in result
                    rec["runtime"].append(verdict)
            rec["product"] = product["elf"]
        phases[tag] = rec
    assert len(phases) == 20
    return {
        "arm": terminal["arm"],
        "subjects": subj,
        "products": obs["products"],
        "phases": phases,
        "terminal_sha256": digest((d / "terminal.json").read_bytes()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", type=Path)
    ap.add_argument("schedule", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--screen-only", action="store_true")
    args = ap.parse_args()
    schedule = read(args.schedule)
    if args.screen_only:
        roster = [["member-p", "P", 0], ["member-q", "Q", 0]]
    else:
        assert (args.runs.parent / "safe-x86-ruff-primary.json").is_file()
        roster = schedule
        assert len(roster) == 16 and len(set(x[0] for x in roster)) == 16
    rows = {}
    for label, which, _ in roster:
        view = arm(args.runs / label)
        assert view["arm"] == which
        rows[label] = view
    content = atomic_json(
        {
            "scope": "screen" if args.screen_only else "registered",
            "schedule": roster,
            "arms": rows,
        }
    )
    with args.output.open("xb") as f:
        f.write(gzip.compress(content, compresslevel=6, mtime=0))
    print(len(rows), "complete independent projections", digest(content))


if __name__ == "__main__":
    main()

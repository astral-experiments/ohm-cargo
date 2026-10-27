"""Check protocol analysis, exact ELF comparison and tracing with independent real command records."""

import argparse
import collections
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import evaluate, holm
from common import compare_elf, elf, load, need, PLAN, trace

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--old-ruff", type=Path)
p.add_argument("--trace", action="store_true")
opts = p.parse_args()
report = {}
orders = load(PLAN)["cargo_companion_support"]["build"]["orders"]
flat = evaluate(orders, [(100, 100)] * 12)
fixed = evaluate(orders, [[100 if a == "parent" else 80 for a in order] for order in orders])
need(
    flat["exact_two_sided_balanced_p"] == 1
    and fixed["extreme_assignments"] == 2
    and abs(fixed["geometric_wall_time_reduction_pct"] - 20) < 1e-12,
    (flat, fixed),
)
families = dict(build=fixed, test=flat)
holm(families)
need(
    fixed["holm_p"] == 4 / 924 and fixed["qualifies_for_speedup"] and not flat["qualifies_for_speedup"],
    families,
)
report["balanced_reference"] = {
    a: [v["extreme_assignments"], v["assignments"], v["holm_p"], v["paired_bootstrap_95_pct"]]
    for a, v in families.items()
}
with tempfile.TemporaryDirectory(prefix="ohm-companion-verifier-") as tmp:
    base = Path(tmp)
    file = base / "elf"
    data = bytearray(Path("/bin/true").read_bytes())
    file.write_bytes(data)
    one = elf(file)
    (offset,) = struct.unpack_from("<Q", data, 40)
    size, count, names = struct.unpack_from("<HHH", data, 58)
    hdr = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size) for i in range(count)]
    ss = hdr[names][4]
    for i, s in enumerate(hdr):
        name = data[ss + s[0] : data.index(0, ss + s[0])]
        if name == b".note.gnu.build-id":
            data[s[4] + 16] ^= 1
        if name == b".rodata":
            data[offset + i * size + 56] ^= 1
        if name == b".text":
            text = s[4]
    file.write_bytes(data)
    two = elf(file)
    need(compare_elf({"test": one}, {"test": two}).keys() == {"test"}, "known Wild differences")
    data[text] ^= 1
    file.write_bytes(data)
    try:
        compare_elf({"test": one}, {"test": elf(file)})
    except ValueError:
        report["ELF"] = "exact bytes outside the two declared fields, executable-code mutation rejected"
    else:
        raise ValueError("mutated .text accepted")
    interrupted = base / "interrupted"
    interrupted.mkdir()
    fragment = interrupted / "exec.1"
    fragment.write_text(
        'execve("/bin/cargo", ["cargo"], 0xabc /* 1 var */) = 0\nexecve("/bin/rustc", ["rustc", "--crate-name", "foo"], 0xabc /* 1 var */ <unfinished ...>\n<... execve resumed>) = 0\n'
    )
    need(trace(interrupted)["rustc"] == [["foo", "full"]], "lost a resumed compiler")
    fragment.write_text(fragment.read_text().split("<... execve resumed>")[0])
    try:
        trace(interrupted)
    except ValueError:
        report["split_exec_record"] = "resumed compiler counted, truncated exec rejected"
    else:
        raise ValueError("incomplete exec record accepted")
    if opts.trace:
        dest = base / "trace"
        dest.mkdir()
        subprocess.run(
            [
                "strace",
                "-ff",
                "-qq",
                "-s",
                "65536",
                "-e",
                "trace=execve,execveat",
                "-o",
                str(dest / "exec"),
                "cargo",
                "+ohm",
                "--version",
            ],
            check=True,
            capture_output=True,
        )
        physical = trace(dest)
        need(not physical["rustc"] and not physical["linkers"], physical)
        report["real_cargo_proxy"] = physical["executions"]
    if opts.old_ruff:
        for mode in ("build", "test"):
            replay = base / mode
            replay.mkdir()
            archive = opts.old_ruff / (mode + "-candidate-execs.tar.gz")
            with tarfile.open(archive) as t:
                for m in t.getmembers():
                    if "/candidate-verify-edit/" in m.name and m.isfile():
                        (replay / Path(m.name).name).write_bytes(t.extractfile(m).read())
            rows = [json.loads(line) for line in (replay / "stdout").read_bytes().splitlines()]
            art = [a for a in rows if a["reason"] == "compiler-artifact"]
            exes = {a["executable"] for a in art if a["executable"]}
            ref = load(replay / "receipt.json")["processes"]
            found = trace(replay, require_cargo=False)
            counts = collections.Counter(k for _, k in found["rustc"])
            need(
                (counts["full"], counts["link-only"], len(found["linkers"]))
                == (ref["rustc_full"], ref["rustc_link_only"], ref["wild"])
                and not set(found["target_execs"]) & exes,
                (mode, found, ref),
            )
            report[mode] = dict(
                units=len(art), executables=len(exes), rustc=dict(counts), linkers=len(found["linkers"])
            )
print(json.dumps(report, indent=2, sort_keys=True))

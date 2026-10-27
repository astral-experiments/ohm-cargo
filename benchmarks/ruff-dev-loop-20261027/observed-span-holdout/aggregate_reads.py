"""Stream a Linux strace from stdin. Retain integer SDK and fixture-library read counts only."""

from collections import Counter
import csv
from pathlib import Path
import re
import sys


def aggregate(lines, allowed):
    pending, parents, programs = {}, {}, {}
    reads = Counter()
    for line in lines:
        pid, _, row = line.rstrip("\n").partition(" ")
        if not pid.isdecimal():
            continue
        if "<unfinished ...>" in row:
            pending[pid] = row.partition("<unfinished ...>")[0]
            continue
        if row.startswith("<... ") and " resumed>" in row:
            row = pending.pop(pid, "") + row.partition(" resumed>")[2]
        if row.startswith("execve(") and re.search(r"= 0$", row):
            image = re.match(r'execve\("([^"]+)"', row)
            if image is None:
                continue
            program = Path(image[1]).name
            if program == "rustc":
                name = re.search(r'"--crate-name", "(hold_[a-z]+)"', row)
                if name:
                    program = "rustc:" + name[1] + (":relink" if "link-only" in row else "")
            programs[pid] = program
        elif row.startswith(("clone(", "clone3(", "fork(", "vfork(")):
            child = re.search(r"= ([1-9][0-9]*)$", row)
            if child:
                parents[child[1]] = pid
        elif row.startswith(("read(", "pread64(")):
            fd = re.match(r"(?:read|pread64)\(\d+<([^>]+)>", row)
            amount = re.search(r"\)\s+= (\d+)$", row)
            if not fd or not amount:
                continue
            filename = Path(fd[1]).name
            if filename in allowed:
                reads[pid, "sdk" if "/lib/rustlib/" in fd[1] else "other", filename] += int(amount[1])
    totals = Counter()
    for (pid, kind, filename), amount in reads.items():
        seen = set()
        while pid not in programs and pid in parents and pid not in seen:
            seen.add(pid)
            pid = parents[pid]
        program = programs.get(pid, "unknown")
        if not re.fullmatch(r"cargo|rustc:hold_[a-z]+(?::relink)?", program):
            program = "other_process"
        totals[program, kind, filename] += amount
    return totals


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    with (here / "library-reads.csv").open(newline="") as f:
        names = {r["library_basename"] for r in csv.DictReader(f)}
    totals = aggregate(sys.stdin, names)
    with Path(sys.argv[1]).open("x", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("process", "input_class", "library_basename", "bytes"))
        for key, value in sorted(totals.items()):
            writer.writerow([*key, value])

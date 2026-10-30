#!/usr/bin/env python3
"""Check the complete public projection and recompute the registered statistics."""
import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import statistics

HERE = Path(__file__).resolve().parent
def read(file):
    return json.loads((HERE / file).read_bytes())

def require(condition, detail):
    if not condition:
        raise ValueError(detail)

def quantile(values, fraction):
    position = (len(values) - 1) * fraction
    lo = int(position)
    return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (position - lo)

def endpoint(pairs):
    require(len(pairs) == 12 and sum(first == "P" for first, _, _ in pairs) == 6, "pair balance")
    changes = []
    groups = {"P": [], "Q": []}
    for first, p, q in pairs:
        changes.append(1 - q / p)
        groups[first].append(changes[-1])
    difference = sum(p - q for _, p, q in pairs)
    chronological = [p - q if first == "P" else q - p for first, p, q in pairs]
    extremes = 0
    assignments = 0
    for flips in itertools.combinations(range(12), 6):
        assignments += 1
        total = sum(delta if i in flips else -delta for i, delta in enumerate(chronological))
        extremes += abs(total) >= abs(difference)
    rng = random.Random(202610292112267)
    bootstrap = sorted(statistics.median([rng.choice(groups[first]) for first in "PQ"
                                          for _ in range(6)]) for _ in range(20_000))
    return dict(median_fraction=statistics.median(changes),
                ci95=[quantile(bootstrap, .025), quantile(bootstrap, .975)],
                two_sided_exact_p=extremes / assignments,
                median_Ir={r: statistics.median([pair[i] for pair in pairs])
                           for i, r in enumerate("PQ", start=1)},
                favorable=sum(d > 0 for d in changes), ties=changes.count(0))

def check(rows, compute=True):
    source, schedule, recorded = read("sources.json"), read("schedule.json"), read("original-scores.json")
    native = read("native-admission.json")
    require(len(schedule) == len(rows) == 48 and len(set(x[0] for x in schedule)) == 48, "48 unique slots")
    by = {"forward": {}, "reverse": {}}
    for record, (name, direction, arm, number) in zip(rows, schedule):
        require(record["slot"] == name == f"pair-{number:02}-{direction}-{arm.lower()}", "chronological order")
        gold = recorded["runs"][name]
        require(record["source"] == source["roles"][arm]
                and record["driver"] == source["driver_sha256"][arm] == gold["driver"], "physical compiler")
        require(record["cargo"] == source["cargo_sha256"] and record["wild"] == source["wild_sha256"], "native tools")
        require(record["collected_Ir"] == record["profile_total_Ir"] == record["self_Ir"] == gold["total"] > 0, "three counts")
        require(record["profile_sha256"] == gold["profile_sha256"] and record["source_terminal_sha256"] == recorded["source_terminal"][name], "raw profile/terminal")
        fds = record["jobserver_distinct_fds"]
        require(len(fds) == len(set(fds)) == 2 and record["same_live_pipe"] is True, "live jobserver")
        require(record["argc"] == native[direction]["argc"] == 119
                and record["argv_sha256"] == native[direction]["argv_sha256"] == gold["argv"], "literal arguments")
        before = native[direction]["old"]
        after = native[direction]["changed"]
        require(record["native_and_profile_consumer"] == [before, after] and record["clean_consumer"] == after
                and before["elf"] != after["elf"] and before["verdict"] != after["verdict"], "clean native consumer")
        expected = {"native-initial": [39,39,8,39], "profile-initial": [39,39,8,39],
                    "independent-changed": [39,39,8,39], "native-edit": [39,1,0,1]}
        expected.update({p: [39,0,0,0] for p in ("native-warm", "profile-warm", "native-edited-unchanged", "profile-edited-unchanged")})
        require(record["native_phases"] == expected, "ordinary build roster")
        by[direction].setdefault(number, []).append((arm,record["self_Ir"]))
    if not compute:
        return
    answers = {}
    for direction, blocks in by.items():
        pairs = []
        require(sorted(blocks) == list(range(1,13)), "block numbering")
        for block in blocks.values():
            require(len(block) == 2 and {a for a,_ in block} == {"P","Q"}, "paired subjects")
            arms = dict(block)
            pairs.append((block[0][0], arms["P"], arms["Q"]))
        answers[direction] = endpoint(pairs)
        original = read("independent-result.json")["directions"][direction]
        require(all(original[k] == v for k,v in answers[direction].items()), "independent estimator")
    return answers

def manifest():
    lines = (HERE / "SHA256SUMS").read_text().splitlines()
    names = []
    for line in lines:
        digest, name = line.split("  ", 1)
        require(".." not in Path(name).parts and not Path(name).is_absolute(), "relative manifest path")
        require(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name)
        names.append(name)
    require(len(set(names)) == len(names), "manifest names")

def bad_cases(rows):
    def wrong(i, key, value):
        r=copy.deepcopy(rows); r[i][key]=value; return r
    changed = copy.deepcopy(rows); changed[0]["native_phases"]["native-edited-unchanged"][1] += 1
    mixed = copy.deepcopy(rows); mixed[0]["clean_consumer"] = mixed[0]["native_and_profile_consumer"][0]
    return [rows[:-1], [rows[1],rows[0],*rows[2:]], wrong(3,"self_Ir",rows[3]["self_Ir"]+1),
            wrong(0,"same_live_pipe",False), wrong(0,"argc",118), wrong(0,"driver","0"*64),
            wrong(0,"profile_sha256","0"*64), changed, mixed]

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--self-test",action="store_true")
    opt=cli.parse_args(); manifest(); rows=read("observations.json")
    answers=check(rows)
    if opt.self_test:
        for i,attempt in enumerate(bad_cases(rows)):
            try: check(attempt,compute=False)
            except ValueError: continue
            raise AssertionError(f"corruption case {i} passed")
    print(json.dumps({"full_rustc_profiles":len(rows),"directions":answers,
                      "corruption_cases_rejected":len(bad_cases(rows)) if opt.self_test else 0},indent=2))

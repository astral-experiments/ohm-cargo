"""Independently check every recorded historical schedule, verdict and folded unit suite."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
sources = json.loads((root / "sources.json").read_bytes())
cases = json.loads((root / "cases.json").read_bytes())
commits = {
    "original/transport":"1aa523118aad2b32eb365589956a96587e527f92",
    "original/check":"a43bb550de710e8b6e81c170a470dfc7f060dbb9",
    "original/defaults":"d75606fa80966b4107d7625e4279c5f400307428",
    "fixed/transport":"613667eadce39c044ec1cf4327a985619de636f7",
    "fixed/defaults":"aa935f6f696f1281a98ccbad2403ca4bb5df3892",
}
compiler = "c6ab483d6698f68eebb49d74b27361f3e02ede55452dc0416c3fdec9a45b7f60"
for key, commit in commits.items():
    s = sources[key]
    assert s["source"] == commit and "commit-hash: " + commit in s["version"] and s["compiler"] == compiler
    assert ("ohm-defaults" in s["features"]) == key.endswith("/defaults")
for arm, count in [("transport",57),("defaults",65)]:
    s = sources["fixed/"+arm]
    assert s["parents"][0] == commits["original/"+arm]
    assert s["parents"][1:] == ([commits["fixed/transport"]] if arm=="defaults" else [])
    assert s["unit_suite"]["source"] == s["source"] and len(set(s["unit_suite"]["passed"])) == count
    assert sum("changed_or_pending_metadata_dependency_propagates_through_unchanged_public_api" in x for x in s["unit_suite"]["passed"]) == 1
for label in ("parent","head","seedparent","seeddefault"):
    assert sources["historical/"+label]["rustc"] == compiler

full = {"original","original-repeat","edited","edited-repeat","edited-clean","restore","restore-repeat"}
small = {"original","original-repeat","edited"}
all_four = {n:True for n in ("api","provider","reader","client")}
stats = Counter()
rendered = set()
labels = [(f"original/{a}/{b}") for a in ("transport","check","defaults") for b in ("provider-first","provider-late")]
labels += [(f"control/{a}/{b}") for a in ("transport","check","defaults") for b in (("ordinary",) if a=="defaults" else ("ordinary","unavailable"))]
labels += [f"historical/{a}/{b}" for a in ("parent","head","seedparent","seeddefault") for b in ("provider-first","provider-late")]
labels += [f"fixed/{a}/{b}" for a in ("transport","defaults") for b in ("ordinary-provider-late","reproduce-provider-first",
           "unavailable-provider-late" if a=="transport" else "reproduce-provider-late")]
assert set(cases)==set(labels) and len(cases)==25
for key, item in cases.items():
    family, arm, method = key.split("/")
    p = item["phases"]
    partial = family=="original" and arm in ("transport","check") and method=="provider-late"
    blocked = partial or "unavailable" in method
    if "ordinary" in method:
        assert item["trace"] is None and item["control"] == []
    else:
        target = 2 if method.endswith("provider-first") else 1
        assert re.fullmatch(r"[0-9a-f]{64}",item["trace"])
        assert item["control"] == [["hold-fd",target,0],["timeout-fd" if blocked else "release-fd",target,0]]
    assert set(p) == (small if partial else full)
    stale = family in ("historical","original") and method=="provider-late" and not blocked
    for phase, outcome in p.items():
        assert all(re.fullmatch("[a-f0-9]{64}",outcome[k]) for k in ("stdout","stderr"))
        valid = phase in ("original","original-repeat","restore","restore-repeat") or (stale and phase in ("edited","edited-repeat"))
        assert outcome["success"] is valid
        if valid:
            assert outcome["errors"]==[]
            if phase in ("restore-repeat","original-repeat","edited-repeat"):
                assert outcome["artifacts"] == all_four
        else:
            error, = outcome["errors"]
            assert error[:4]==["client","E0034","multiple applicable items in scope",[["client/src/main.rs",3]]]
            rendered.add(error[4])
    stats["commands"] += len(p)
    stats["full"] += not partial
    stats["stale"] += stale
assert stats == {"commands":167,"full":23,"stale":5}
assert len(rendered)==1 and next(iter(rendered)).startswith("f56ad66c2eeaee")
assert "impl api::Second for Token" not in (root/"fixture/provider/src/lib.rs").read_text()
if (root/"SHA256SUMS").exists():
    for line in (root/"SHA256SUMS").read_text().splitlines():
        digest,name=line.split("  ",1)
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
print("Verified 167 actual Cargo commands, 23 complete histories, two unavailable original orders, five stale histories and all 122 folded fingerprint tests.")

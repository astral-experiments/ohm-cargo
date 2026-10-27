"""Export byte-identical process ledgers from the fixed parent/candidate instruction comparison."""
from pathlib import Path
import json
import shutil
import sys

root=Path("/mnt/devbox-scratch/dev-user/ohm-whole-skips-20261027/mixed-registry-only-pilot")
src=root/"scoped-parser-ir-holdout-v3"; dst=Path(sys.argv[1]); assert not dst.exists()
native=root/"scoped-parser-overhead-v3-r2/qualification"
dst.mkdir()
for k in ("admission.json","inputs.json","inner-binding.json"):
    shutil.copyfile(src/k,dst/k)
for arm in ("parent","candidate"):
    for ep in ("retained","empty"):
        n=native/arm/ep
        f=dst/"ordinary"/arm/ep; f.mkdir(parents=True)
        for k in ("result.json","stdout","stderr","child.json","launcher.stderr","metadata.root"):
            shutil.copyfile(n/k,f/k)
for p in sorted((src/"score").iterdir()):
    if p.is_file():
        shutil.copyfile(p,dst/p.name); continue
    f=dst/"records"/p.name;f.mkdir(parents=True)
    for k in ("counter.txt","native-archive.json","stdout","stderr","launcher.stderr","child.json","mappings.json","metadata.root"):
        source=p/"physical"/k
        if source.is_file():shutil.copyfile(source,f/k)
    if (p/"outcome.json").is_file():shutil.copyfile(p/"outcome.json",f/"outcome.json")
print(len(list((dst/"records").iterdir())))

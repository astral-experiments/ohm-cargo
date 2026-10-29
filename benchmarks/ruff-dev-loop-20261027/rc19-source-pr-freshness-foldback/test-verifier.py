"""Check that a plausible intermediate or corrupted result cannot pass the offline verifier."""
import copy
import json
from pathlib import Path
import runpy

root = Path(__file__).resolve().parent
verify = runpy.run_path(str(root / "verify.py"))["validate"]
original = json.loads((root / "results.json").read_bytes())
assert verify(original)

def rejects(change):
    sample = copy.deepcopy(original)
    change(sample)
    try:
        verify(sample)
    except AssertionError:
        return
    raise AssertionError("Mutation was accepted")

rejects(lambda p: p["arms"]["stamped-101"]["image"].update(commit_reported=p["source"]["101"]["prior"]["commit"]))
rejects(lambda p: p["arms"]["stamped-103"]["recovery"]["result"].update(first_success="untouched-1"))
rejects(lambda p: p["arms"]["stamped-101"]["fifo"]["default/parent-error"]["opens"]["fifo"][0]["flags"].remove("O_NONBLOCK"))
rejects(lambda p: p["arms"]["stamped-103"]["suites"]["sets"]["conditional"]["mount_witness"].update(same_inode=False))
rejects(lambda p: p["arms"]["stamped-101"]["suites"]["sets"]["conditional"]["tests"].pop())
print("Rejected a stale version stamp, second-attempt recovery, blocking speculative read, substituted product, and missing test.")

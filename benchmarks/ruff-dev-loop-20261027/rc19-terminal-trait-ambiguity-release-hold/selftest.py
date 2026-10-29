"""Check that forged execution, publication, and diagnostic evidence is rejected."""
import copy
import importlib.util
import json
from pathlib import Path

here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("check_receipts",here/"verify.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rows=json.loads((here/"official-18.json").read_bytes())
mod.check_arm(rows,"official-18")
def reject(change):
    bad=copy.deepcopy(rows)
    change(bad["cases"])
    try:
        mod.check_arm(bad,"official-18")
    except AssertionError:
        return
    raise RuntimeError("mutated receipt accepted")
reject(lambda cases:cases["1-provider-late-edit"]["compilers"].pop())
reject(lambda cases:cases["1-provider-late-edit"]["ordering"].pop(0))
reject(lambda cases:cases["1-provider-late-repeat"].update(exit=101))
reject(lambda cases:cases["1-provider-late-clean"]["errors"][0].update(code="E0308"))
reject(lambda cases:cases["1-provider-late-repeat"]["artifacts"].update(client=False))
print("Rejected five independently altered receipts.")

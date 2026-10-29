"""Compare both assembled results to the independent full compiler and error oracle."""
from pathlib import Path
import hashlib, json, sys

d = Path(sys.argv[1]).resolve()
def load(name):
    return json.loads((d/name/"result.json").read_bytes())

edit = load("03-edit-and-new-asset")
empty = load("04-independent-clean")
forced = load("05-forced-full-keep-incremental")
missing = load("07-source-restore-missing-asset")
empty_missing = load("08-independent-missing")
forced_missing = load("09-forced-same-missing")
assert empty["native"] == forced["native"] == 29 and empty["status"] == forced["status"] == 0
assert empty_missing["status"] == forced_missing["status"] == 101
assert empty_missing["diagnostic_mentions_incbin"] and forced_missing["diagnostic_mentions_incbin"]
checks = {"changed_existing_payload": edit.get("native") == empty["native"] and edit["status"] == empty["status"],
          "missing_payload": missing["status"] == empty_missing["status"] and missing["diagnostic_mentions_incbin"]}
print(json.dumps({"checks":checks, "changed":{"actual":edit.get("native"), "forced":forced["native"], "empty":empty["native"]},
                  "missing":{"actual":missing["status"], "forced":forced_missing["status"], "empty":empty_missing["status"]},
                  "terminal":hashlib.sha256((d/"terminal.json").read_bytes()).hexdigest()}, sort_keys=True))
sys.exit(0 if all(checks.values()) else 1)

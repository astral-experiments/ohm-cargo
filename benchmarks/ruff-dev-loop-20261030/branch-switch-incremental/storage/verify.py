"""Recompute the physical disk ratios from both counterbalanced installations."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
data = json.loads((root / "observations.json").read_bytes())
assert data["public_measurement_script"] == hashlib.sha256((root / "count.py").read_bytes()).hexdigest()
rows = data["observations"]
assert len(rows) == 24
for record in rows.values():
    assert record["bytes"] <= sum(record["root_bytes"].values())
    assert 0 <= record["exclusive_older_bytes"] <= record["bytes"]
    assert record["exclusive_older_bytes"] == sum(record["older_categories"].values())
    if record["role"] == "P":
        assert record["older_sessions"] == 0
        assert record["exclusive_older_bytes"] == 0
for phase in ("empty-A", "first-B", "return-A", "return-B", "unchanged-B"):
    ratios = []
    for pair in (1, 2):
        p, q = [rows[f"pair-{pair:02d}-{arm}/{phase}"] for arm in "PQ"]
        assert q["older_sessions"] == (0 if phase == "empty-A" else 2)
        ratios.append(q["bytes"] / p["bytes"])
    print(phase, *(f"{ratio:.4f}×" for ratio in ratios))

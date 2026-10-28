"""Verify the four saved invocations of the portable reproducer and their original images."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
cargo = {
    "A": "0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2",
    "Q": "03c851e44a863bb0d2cb8c9a98df1eef33310c8f3fbc77cdbb48aee516e68400",
    "N": "d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde",
}
for case in ("A-ignored", "N-legacy", "N-optional", "Q-probe"):
    arm, mode = case.split("-")
    result = json.loads((root / "results" / (case + ".json")).read_bytes())
    assert result["expected"] == mode and result["images"]["cargo"] == cargo[arm]
    assert result["images"]["frontend"] == "4fa9a18b77430bcc416e88561b6fe5797d98b996a7698b9f3bd11d4e7817a19f"
    assert result["images"]["driver"] == (
        "52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955" if mode == "legacy"
        else "ee9448c27a69a06a50abe707797637638dc6b2a226011339b35adc2b9a065b99"
    )
    rows = result["rows"]
    assert rows["first"]["external_sha256"] != rows["changed"]["external_sha256"]
    for phase, row in rows.items():
        value = 17 if phase == "first" else 29
        assert row["native"].endswith("escape-value=" + str(value))
        assert row["caller_full"] == int(phase != "noop")
        assert row["capability_queries"] == int(arm == "Q" and phase != "noop")
        assert row["complete"] == (mode in ("optional", "probe") or phase in ("changed", "noop"))
        assert row["all_fresh"] == (phase == "noop")
print("Verified four native modes, 16 Cargo commands and all external-library results.")

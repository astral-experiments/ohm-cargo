"""Verify the public six-phase Ruff production edit and ELF comparison."""
from pathlib import Path
import gzip,json,subprocess,sys,tempfile
base=Path(__file__).resolve().parent
packet=base/"cohort.json.gz"
d=json.loads(gzip.decompress(packet.read_bytes()));ph=d["phases"]
assert d["arm"]=="release" and d["group"]=="dedent"
a=json.loads(subprocess.check_output([sys.executable,"-IB",base/"compare-cohort.py",packet]))
assert a["warm_edit_matches_clean_elf"]
expected={"seed":2,"edited":None,"edited-repeat":None,"clean":None,"restore":2,"final-repeat":2}
for key,ret in expected.items():
    p=ph[key]
    assert p["ret505"]["false_branch"]==ret and p["units"]==619
    assert p["command"]["images"]["cargo"]=="02a86ebd2d9e4f237b33f212102b81ed145eb77fae090d67e379cb6f1d70a573"
    assert p["command"]["source"]=="93526150df078af7dd8fc4226cdcc469539d2001"
assert ph["edited"]["actual_ruff_cli_fixed_source"]==ph["clean"]["actual_ruff_cli_fixed_source"]
assert ph["seed"]["actual_ruff_cli_fixed_source"]==ph["restore"]["actual_ruff_cli_fixed_source"]
assert ph["edited"]["native"]==ph["restore"]["native"]=={"full":111,"wild":75}
assert ph["edited"]["command"]["state"]==ph["clean"]["command"]["state"]=="reversed"
assert ph["clean"]["fresh"]==0 and ph["clean"]["command"]["empty_target"] and ph["clean"]["command"]["empty_shared"]
for k in ("seed","edited-repeat","final-repeat"):
    assert ph[k]["fresh"]==563 and ph[k]["native"]=={"full":1,"link-only":50,"wild":50}
with tempfile.TemporaryDirectory() as t:
    dest=Path(t)/"elf.json"
    subprocess.run([sys.executable,"-IB",base/"classify-elf.py",packet,"--output",dest],check=True)
    elf=json.loads(dest.read_bytes())
rows={(p["left"],p["right"]):p for p in elf["comparisons"]}
assert elf["original_targets_identified"]==50
assert rows["seed","edited"]["counts"]=={"exact":26,"machine-code bytes changed":5,"other ELF changes, identical allocated bytes except build ID":19}
assert rows["edited","clean"]["counts"]=={"exact":46,"rodata header or build ID differs":4}
assert rows["seed","restore"]["counts"]=={"exact":48,"rodata header or build ID differs":2}
assert rows["restore","final-repeat"]["counts"]=={"exact":47,"rodata header or build ID differs":3}
print("Verified six released Cargo builds, independent edited Python output, and full section-by-section evidence for 50 compiled programs.")

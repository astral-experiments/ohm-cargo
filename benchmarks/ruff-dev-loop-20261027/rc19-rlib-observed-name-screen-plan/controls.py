"""Exercise isolated corruption, missing evidence, wrong-name and wrong-source controls outside timing."""
import argparse
import copy
import json
from pathlib import Path
import runpy
import subprocess
import tempfile

verify = runpy.run_path(str(Path(__file__).with_name("name_oracle.py")))["verify"]


def rejects(label, call, caught):
    try:
        call()
    except (ValueError, AssertionError) as err:
        caught[label] = {"exception": type(err).__name__, "detail": str(err)}
    else:
        raise AssertionError(f"{label} unexpectedly admitted")


def controls(gold, witness, watch, product, alternate_gold, alternate_witness, scratch):
    accepted = verify(gold, witness, watch, product)
    receipts = {}
    wrong = copy.deepcopy(watch)
    old = accepted["current_nonce"]
    fake = "1000000" if old != "1000000" else "2000000"
    for event in wrong["objects"]:
        suffix = "." + old + ".rcgu.o"
        assert event["name"].endswith(suffix)
        event["name"] = event["name"][:-len(suffix)] + "." + fake + ".rcgu.o"
    rejects("wrong-current-name", lambda: verify(gold,witness,wrong,product),receipts)
    missing = copy.deepcopy(watch)
    missing["objects"].pop()
    rejects("missing-current-name", lambda: verify(gold,witness,missing,product),receipts)
    assert alternate_witness["product_sha256"] != witness["product_sha256"]
    rejects("wrong-real-source", lambda: verify(alternate_gold,alternate_witness,watch,product),receipts)
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        copyfile=Path(temp)/"intentionally-corrupt.rlib"
        subprocess.run(["cp","--reflink=auto","--",product,copyfile],check=True)
        # Flip one byte in an actual CGU payload, outside the two special members.
        member = witness["archive_members"][4]
        assert member["name"].endswith(".rcgu.o") and member["size"] > 64
        with copyfile.open("r+b") as out:
            pos = member["offset"] + 63
            out.seek(pos)
            value = out.read(1)[0]
            out.seek(pos)
            out.write(bytes([value ^ 4]))
        rejects("changed-object-byte",lambda: verify(gold,witness,watch,copyfile),receipts)
    assert verify(gold,witness,watch,product) == accepted
    return {"accepted": accepted,"rejected":receipts}


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("gold","witness","watch","product","alternate_gold","alternate_witness","scratch"):
        p.add_argument(arg,type=Path)
    a=p.parse_args()
    read=lambda path:json.loads(path.read_bytes())
    print(json.dumps(controls(a.gold,read(a.witness),read(a.watch),a.product,a.alternate_gold,
                              read(a.alternate_witness),a.scratch),sort_keys=True))

from pathlib import Path
import hashlib
import json
import tarfile


here = Path(__file__).resolve().parent
for line in (here / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split("  ")
    assert hashlib.sha256((here / name).read_bytes()).hexdigest() == digest, name

tools = {
    "rc17": (
        "e74dddbed648ca90bd5cabab90d9e02517478e40f5552a0a8369d72d15596d33",
        "787ed90b5a14000ac0b1efc1d1aac5d730e0107b2e995cc0471138402759a4d5",
        "36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05",
        "52d5c046f570d3d61ff8bbaeff0d44798df916306110b4a2cac7fe459bc11955",
    ),
    "r16": (
        "42e90992cec21a29956e20fd52ab952472a9dbc1dcc7a3b60c92aad101b5f568",
        "6b5fb3614ad1bea619df417e20a51d3c3dec397118e87edc782b4cce99ca2873",
        "c442c2a36e1f37c92f138a8fb367fc09982931b5f1055e9742fb402566ad46a4",
        "7c5a9f5a874274de911d81d0d3bb2af3839380f43dc8521aa7f248f416880d49",
    ),
}
root = "equal-length-release-v4-20261028/"
with tarfile.open(here / "observations.tar.gz") as archive:
    names = set(archive.getnames())
    def read(name):
        return archive.extractfile(root + name).read()
    def data(name):
        return json.loads(read(name))
    commands = dict(r.split() for r in read("commands.log").decode().splitlines())
    assert len(commands) == 12 and set(commands.values()) == {"0"}
    builds = checks = cases = 0
    sizes = []
    for name in sorted(commands):
        if name == "r16-permanent-test":
            passed = data(name + "/receipt.json")
            assert passed["exit"] == 0 and passed["driver"] == tools["r16"][3]
            assert passed["test_binary"] == "1f971549e0d7b15096692b5adcac2320e14b882e009899fc4c95900c3bd1cb69"
            continue
        release, action, cargo, rust = name.split("-")
        result = data(name + "/result.json")
        if action == "check":
            checks += len(result)
            independent = result["independent"]
            assert independent["exit"] == 101 and any(row["code"]["code"] == "E0308" for row in independent["diagnostics"])
            if cargo == "upgrade":
                assert result["changed"]["all_fresh"] and result["changed"]["exit"] == 0
                assert result["corrected"]["diagnostics"] == independent["diagnostics"]
            else:
                assert result["changed"]["diagnostics"] == independent["diagnostics"]
            continue
        identity = data(name + "/identity.json")
        old_c, new_c, old_r, new_r = tools[release]
        assert (identity["old_cargo"], identity["new_cargo"]) == (old_c, new_c)
        assert identity["driver"] == (old_r if rust == "old" else new_r)
        for mode, rows in result.items():
            cases += 1
            builds += len(rows)
            same, changed, clean = (rows[k] for k in ("unchanged", "changed", "empty"))
            assert same["value"] == 17 and clean["value"] == 29
            assert same["real"] != changed["real"] == clean["real"]
            assert same["stamps"] == changed["stamps"]
            sizes.append(same["stamps"][2])
            stale = rust == "old" and cargo in ("old", "upgrade") and mode.startswith("decoy")
            assert (changed["value"], changed["fresh"], len(changed["compiler_exec"])) == ((17, True, 0) if stale else (29, False, 1))
            if stale:
                assert same["shadow"] == changed["real"]
            if rust == "fixed" or mode == "ordinary":
                assert same["fresh"] and not same["compiler_exec"]
            if rust == "old" and cargo == "fixed" and mode != "ordinary":
                assert not same["fresh"] and same["complete"] == 0
            if cargo == "upgrade":
                assert rows["upgrade"]["value"] == rows["upgrade-noop"]["value"] == 29
                assert rows["upgrade"]["version"] == 4
            for label, row in rows.items():
                assert read(f"{name}/{mode}/records/{label}/native").decode() == row["native"]
                assert data(f"{name}/{mode}/records/{label}/row.json") == row
                if row["compiler_exec"]:
                    assert all(line.encode() in read(f"{name}/{mode}/records/{label}/exec") for line in row["compiler_exec"])
    assert (cases, builds, checks, min(sizes), max(sizes)) == (24, 132, 16, 7528, 7568)
    assert len([n for n in names if n.endswith("/row.json")]) == builds + checks
    assert len([n for n in names if n.endswith("/exec")]) == builds
portable = json.loads((here / "portable-r16.json").read_bytes())
assert portable["changed"] == {"value": 17, "fresh": True} and portable["empty"] == {"value": 29, "fresh": False}
print(f"Verified {builds} native builds, {checks} real checks, {cases} preserved inode/size/mtime edits, the packaged standalone replay and the permanent source test.")

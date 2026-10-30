"""Check the three released toolchains and the independent candidate-Cargo observations."""

import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path


def verify(rows):
    subjects = {
        "published-17",
        "published-18",
        "published-19",
        "published-19-independent",
        "candidate-W-release-Cargo",
        "candidate-W-companion-Cargo",
    }
    assert set(rows) == subjects
    release = rows["candidate-W-release-Cargo"]["tools"]
    companion = rows["candidate-W-companion-Cargo"]["tools"]
    assert release["cargo"] != companion["cargo"]
    assert all(release[k] == companion[k] for k in ("rustc", "driver", "wild"))
    assert rows["published-19"]["tools"] == rows["published-19-independent"]["tools"]
    jobs = Counter()
    for label, sample in rows.items():
        assert sample["expected"] == "stale" and sample["subject"] == label
        phases = sample["phases"]
        assert len(phases) == 15
        clean = phases["independent-17-11"]
        repaired = phases["independent-41-11"]
        assert clean["verdict"] == "17 11" and repaired["verdict"] == "41 11"
        assert phases["authentic-alternate"]["verdict"] == "29 7"
        for phase in phases.values():
            assert phase["cargo"] == 0 and phase["exec_files"] > 0
            assert (
                len(bytes.fromhex(phase["exec_sha256"]))
                == len(bytes.fromhex(phase["cargo_json_sha256"]))
                == 32
            )
            if sample["retained_executables_replayed"]:
                stdout = (phase["verdict"] + "\n").encode()
                assert (
                    hashlib.sha256(stdout).hexdigest()
                    == phase["replayed_stdout_sha256"]
                )
            jobs.update(job[0] for job in phase["native_jobs"])
        for mode in ("untouched", "rename", "in-place"):
            obj = sample["objects"][mode]
            before, after = obj["before"], obj["after"]
            assert before["links"] == 2 and set(obj["alias_sha256"]) == {
                "saved",
                "incremental",
            }
            assert (
                before["size"] == after["size"]
                and before["mtime_ns"] == after["mtime_ns"]
            )
            assert before["sha256"] != obj["alternate_sha256"]
            assert obj["alias_sha256"]["saved"] == after["sha256"]
            assert (before["inode"] == after["inode"]) == (mode != "rename")
            assert before["device"] == after["device"]
            assert obj["alias_sha256"]["incremental"] == (
                obj["alternate_sha256"] if mode == "in-place" else before["sha256"]
            )
            assert after["sha256"] == (
                before["sha256"] if mode == "untouched" else obj["alternate_sha256"]
            )
            seed = phases[mode + "-seed"]
            edited = phases[mode + "-edit-dependency"]
            repeated = phases[mode + "-unchanged"]
            root_edit = phases[mode + "-edit-root"]
            assert (
                seed["verdict"] == "17 7"
                and edited["source"] == clean["source"] == seed["source"]
            )
            assert (
                edited["provider_source"]
                == clean["provider_source"]
                != seed["provider_source"]
            )
            assert edited["native_jobs"] == [
                ["full", "link_probe"],
                ["full", "provider"],
                ["wild", "link_probe"],
            ]
            assert edited["typed"] == [["provider", False], ["link_probe", False]]
            assert repeated["native_jobs"] == [] and repeated["typed"] == [
                ["provider", True],
                ["link_probe", True],
            ]
            assert (
                edited["elf"] == repeated["elf"]
                and edited["verdict"] == repeated["verdict"]
            )
            assert edited["verdict"] == ("29 11" if mode == "in-place" else "17 11")
            assert (edited["elf"] == clean["elf"]) == (mode != "in-place")
            assert (
                root_edit["verdict"] == repaired["verdict"]
                and root_edit["elf"] == repaired["elf"]
            )
            assert root_edit["source"] == repaired["source"] != clean["source"]
    return dict(
        installs=len(rows),
        commands=sum(len(x["phases"]) for x in rows.values()),
        native_jobs=jobs,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    rows = json.loads(
        gzip.decompress(Path(__file__).with_name("observations.json.gz").read_bytes())
    )
    result = verify(rows)
    if args.self_test:
        for path, value in [
            (("phases", "in-place-edit-dependency", "verdict"), "17 11"),
            (("phases", "in-place-unchanged", "native_jobs"), [["wild", "link_probe"]]),
            (("objects", "in-place", "after", "inode"), -1),
            (("phases", "rename-edit-dependency", "elf"), "0" * 64),
        ]:
            sample = deepcopy(rows)
            node = sample["published-19"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            try:
                verify(sample)
            except AssertionError:
                continue
            raise RuntimeError(f"accepted corrupt field {path!r}")
        result["rejected_mutations"] = 4
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

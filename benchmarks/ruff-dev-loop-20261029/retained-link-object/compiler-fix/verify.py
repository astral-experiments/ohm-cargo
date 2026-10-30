"""Verify the upgrade-independent repaired compiler specimen and its run-make control."""

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path


def verify(samples, regression):
    assert set(samples) == {"E-O", "E-K"}
    assert regression["old"]["source_files"] == regression["fixed"]["source_files"]
    assert (
        regression["old"]["exit"] != 0 and regression["old"]["complete_compilers"] == 2
    )
    assert (
        regression["fixed"]["exit"] == 0
        and regression["fixed"]["complete_compilers"] == 3
    )
    assert regression["fixed"]["source"] == "05efba7a06f5bb71d1efb4b86805800f8b810779"
    driver = "5becad96c462ebded234e1cfe87d9ed86f66d7ef364a26cff507495165a7ad82"
    assert regression["fixed"]["driver"] == driver != regression["old"]["driver"]
    assert (
        samples["E-O"]["tools"]["cargo"]
        == "43acdc336b077657fc4182a2ad79a6dc1cfb2f5e84f83dcd9ab6576e037aa276"
    )
    assert (
        samples["E-K"]["tools"]["cargo"]
        == "96d49e1e0609d39bbfe6dc804ef0dc30211e0dc4bab24a1cb0b243f32c36b3a5"
    )
    for sample in samples.values():
        assert (
            sample["expected"] == "correct" and sample["retained_executables_replayed"]
        )
        assert sample["tools"]["driver"] == driver
        phases = sample["phases"]
        assert len(phases) == 15
        clean = phases["independent-17-11"]
        repaired = phases["independent-41-11"]
        assert clean["verdict"] == "17 11" and repaired["verdict"] == "41 11"
        for phase in phases.values():
            assert phase["cargo"] == 0 and phase["exec_files"] > 0
            assert (
                phase["replayed_stdout_sha256"]
                == hashlib.sha256((phase["verdict"] + "\n").encode()).hexdigest()
            )
        for mode in ("untouched", "rename", "in-place"):
            obj = sample["objects"][mode]
            before, after = obj["before"], obj["after"]
            assert before["links"] == after["links"] == 1 and obj["alias_sha256"] == {
                "saved": after["sha256"]
            }
            assert (
                before["size"] == after["size"]
                and before["mtime_ns"] == after["mtime_ns"]
            )
            assert before["device"] == after["device"] and (
                before["inode"] == after["inode"]
            ) == (mode != "rename")
            assert before["sha256"] != obj["alternate_sha256"]
            assert after["sha256"] == (
                before["sha256"] if mode == "untouched" else obj["alternate_sha256"]
            )
            seed = phases[mode + "-seed"]
            edited = phases[mode + "-edit-dependency"]
            repeated = phases[mode + "-unchanged"]
            root_edit = phases[mode + "-edit-root"]
            assert (
                seed["verdict"] == "17 7"
                and seed["source"] == edited["source"] == clean["source"]
            )
            assert (
                seed["provider_source"]
                != edited["provider_source"]
                == clean["provider_source"]
            )
            assert edited["verdict"] == repeated["verdict"] == clean["verdict"]
            assert edited["elf"] == repeated["elf"] == clean["elf"]
            assert edited["native_jobs"] == [
                ["full", "link_probe"],
                ["full", "provider"],
                ["wild", "link_probe"],
            ]
            assert repeated["native_jobs"] == [] and repeated["typed"] == [
                ["provider", True],
                ["link_probe", True],
            ]
            assert (
                root_edit["verdict"] == repaired["verdict"]
                and root_edit["elf"] == repaired["elf"]
            )
    return sum(len(sample["phases"]) for sample in samples.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    samples = json.loads(
        gzip.decompress((directory / "observations.json.gz").read_bytes())
    )
    regression = json.loads((directory / "run-make.json").read_bytes())
    count = verify(samples, regression)
    if args.self_test:
        for path, value in [
            (("phases", "in-place-edit-dependency", "verdict"), "29 11"),
            (("objects", "in-place", "before", "links"), 2),
            (("phases", "in-place-unchanged", "native_jobs"), [["wild", "link_probe"]]),
            (("phases", "independent-17-11", "elf"), "0" * 64),
        ]:
            broken = deepcopy(samples)
            node = broken["E-O"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            try:
                verify(broken, regression)
            except AssertionError:
                continue
            raise RuntimeError(f"accepted corrupt field {path!r}")
    print(
        f"verified {count} real Cargo commands, two Cargo versions, and the run-make regression"
    )


if __name__ == "__main__":
    main()

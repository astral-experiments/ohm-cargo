# Exporting the corrected release-17 Ruff first-selection trial

V1 stopped at admission after findmnt identified ext4 on H5. It recorded zero wall commands. This exporter retains v1's actual traceback and handles the separately registered v2 probe, ensuring the changed storage rule stays explicit. The source trial compares Cargo #261 with the same source plus #260 on Ohm 1.99.0-17. It clocks the first full Ruff test selection after an independently restored excluded-selection seed. The untouched post-check still runs a true ron compilation and 50 real Wild links. The frozen wall protocol defines the exact primary analysis and native output rules. The independent admission contains the 320 same-input linker replays. [Wall protocol](https://github.com/astral-sh/ohm-cargo/tree/3a7bba8da2347af0ee04f847ddc786e7be3783f2/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-plan-v2) · [Native evidence](https://github.com/astral-sh/ohm-cargo/tree/a75e5f17c07081cfcc9fabfcccd7a5022528641b/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-native-results)

Admission bound the exact seed and original images before the first wall command. [Final wall admission](https://github.com/astral-sh/ohm-cargo/tree/bd7280e6aa38f26f48181d4c26a75f1508985203/benchmarks/ruff-dev-loop-20261027/rc17-composed-wall-admission-v2)

The separately witnessed one-MiB physical copy preserved the source after a destination write on the same ext4 device. FICLONE returned EOPNOTSUPP (95), and every score slot must use the same full-copy method. [Original XFS gate](https://github.com/astral-sh/ohm-cargo/tree/480e5f2dc1f69866145c98909ed0f327141e2928/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-wall-plan) · [Build and QA evidence](https://github.com/astral-sh/ohm-cargo/tree/d699d4cc9651cb91e84d1a012eadc9b53883f9ef/benchmarks/ruff-dev-loop-20261027/rc17-composed-early-safety-results)

V2 uses distinct wall-protocol-v2, wall-launch-v2, early-scheduler-wall-admission-v2.json and early-scheduler-wall-rc17-v2 locations. It reads the same published QA receipts as v1. The remote exporter opens the status files for admission, scoring and the independently launched original verifier before inspecting a single slot. For a success it requires all three exits. A nonzero terminal admission, score or verification exit produces a failure packet. Each original invocation remains authoritative, including the unmodified published verify_result.py and its actual stdout, stderr and exit code. The exporter writes to stdout and performs no compiler or linker invocation. The separate transfer command reads this single gzip stream over SSH and checks the producer's full-file SHA-256 and byte count before accepting it locally.

## Evidence retained

- Original wall plan and tool file hashes, native protocol versions, previously admitted raw ELF layouts, QA/source/build receipt commitments, copy method, checked seed bytes, SHA-256 commitment for the admission, independently preserved failed-state ELF commitments, and the approved Git revisions in the actual grant.
- All emitted ordinary command argv, monotonic start/stop times, duration and exit. The packet stores the ordinary stdout/stderr and test listing byte-for-byte when suitable for public release, with a separate digest for each source. Any sensitive raw text is held in its original private file and reported as a commitment-only field. Such a file cannot satisfy a required verbatim check.
- Each existing slot and its original order, full first and follow-up output hashes, 78 registry hashes, typed Cargo unit SHA-256 identities, freshness and counts, warnings, test listing, and one raw trace-file commitment per traced process. Native process projections retain the PID, role, target, exit, successful exec-line hash and argument hash. General Cargo JSON, physical argv and native trace text contain host registry paths. Their raw digests remain in the packet with independently checkable projections.
- All available first exceptions, untouched preserved failed-state file hashes for the 110 workspace and 78 registry identities when the failed state exists, and each retained source reference. The source path and successful/failed phase remain distinguishable when a command aborted during setup or before it could produce a complete map.
- The exact enrolled 24 pair schedules, crossed whole-ELF differences, all original pairs/summary/result digests, and the original native verifier receipt. A failed series has no computed partial effect, interval or p-value. Individual completed or failed clocks remain readable.

## Offline checks

This directory contains only the tools and their synthetic test receipt before the actual trial is exported. To exercise it locally, place the published wall v1/v2, native v2/v3, native result and safety result directories alongside it, or pass the actual protocol and native result locations for verification.

```sh
/usr/bin/python3 -IB selftest.py ../rc17-composed-early-wall-plan-v2
/usr/bin/python3 -IB verify.py results.json.gz ../rc17-composed-early-wall-plan-v2 ../rc17-composed-early-native-results
```

On complete data the portable reader replays the real clock order, all raw outputs and sampled warnings, then reruns the published exact permutation and bootstrap calculation. Its statistics and all 2,640 first-selection comparisons must agree with the original verifier's terminal stdout. The prior native packet provides the actual 619 typed identities, 102 runtime products, both subject hashes, all admitted raw ELF hashes and the real unchanged post-check roster. The portable reader separately reports the original launcher exits on failed runs.

After the owner authorizes the single terminal H5 read, the exporter can be relayed by running the following on the coordinator. A partial download stays separate from any accepted file.

```sh
/usr/bin/python3 -IB transfer.py /absolute/path/to/new/results.json.gz
```

The synthetic checks construct known 35% timing differences, a failed third clock, an aborted admission, a failing final native verifier, a changed native process role and altered stderr and a clocked trial still awaiting its final verification. They run no Cargo subprocess, rustc process, linker or test executable.

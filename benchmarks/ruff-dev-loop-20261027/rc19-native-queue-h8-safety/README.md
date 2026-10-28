# Native Cargo scheduling checks on the independent machine

The candidate uses the size of a previous regular executable when Cargo has already dequeued two eligible native test units with equal dependency priority. Both arms use Cargo source 235f9228651b74c591e6f62cae4c9b761448dd2d and the same installed Linux x86_64 Rust and Wild. The queue patch is 4b0751af97bfa22204a013d0d1f0707382b0df52. The ordinary command compiled ron once, ran 50 cached rustc drivers, and launched 50 GCC, 50 collect2 and 50 stock Wild processes in each accepted native measurement. The checks in this packet took place outside the wall-time experiment.

## Inputs and output verification

For each of two independently settled batches, the machine copied all six state directories to a separate set of mutable inodes and compared file contents, modes, owner, nanosecond mtimes and symlink contents. The files named quiescent-copy contain the complete tree digests. The pre-admission traced exact Rust options, the full ordered argument list for each native process, 50 executable files, a 200-entry test listing and two real notebook regression tests. The three path roles that Rust and GCC populate afresh are the temporary symbols object, empty raw library directory and empty GCC resolution file. Their actual input contents were checked when stock Wild executed.

The earlier independently built pair had 3,060 file positions with distinct codegen member names but matching contents, and 835 same-name file positions with differing contents. The two matched batches require both spelling and contents for every explicitly named regular file. The first matched batch verified 11,983 such ordered file positions across the 50 link commands. These quiescent reads do not enumerate implicit system library opens or unsuccessful library searches. Both native linkers still execute.

## Enforced memory controls

The table reports the third group. Each arm used its own complete copy of the byte-verified first batch. Its Cargo and child tools ran unprivileged with the native UID map inside a dedicated cgroup v2 service. The recorded memory limit and zero swap limit apply to that service. The kernel accounts charged pages to the cgroup. Summing per-process PSS can include shared pages charged elsewhere. All six arms recorded zero OOM and kill events. The original one-ID and separate-input full-UID–map controls are in the same packet.

| Limit | Arm | Peak cgroup MiB | Peak PSS MiB | Peak summed RSS MiB | Largest child RSS MiB | Memory max events |
|---|---|---:|---:|---:|---:|---:|
| 2 GiB | A | 2,048.00 | 2,456.0 | 4,705.7 | 382.9 | 1269 |
| 2 GiB | B | 2,048.00 | 2,704.6 | 5,574.0 | 382.1 | 1551 |
| 3 GiB | A | 3,072.00 | 2,268.0 | 4,637.5 | 385.2 | 596 |
| 3 GiB | B | 3,072.00 | 2,691.4 | 5,386.3 | 379.9 | 489 |
| 4 GiB | A | 4,095.88 | 2,246.9 | 4,414.3 | 378.8 | 61 |
| 4 GiB | B | 4,095.81 | 2,760.0 | 5,064.0 | 375.8 | 15 |

The kernel recorded a transient peak above the configured limit in ordinary_full_map 2 GiB B (4,096 bytes above). The raw cgroup counters are retained.

## Ordering and fallbacks

physical-wild-launch-order records actual exec order under stock Wild. Each row shows the ten largest outputs in decreasing size order. Rank 1 means the first of the 50 native launches.

- Batch 1. Control [26, 32, 20, 39, 5, 14, 15, 10, 12, 11]. Candidate [7, 6, 4, 5, 2, 1, 8, 9, 11, 10].
- Batch 2. Control [28, 35, 18, 42, 2, 13, 14, 11, 10, 12]. Candidate [6, 8, 4, 5, 3, 1, 7, 9, 14, 10].

The focused Cargo unit test passed. The 18 small fixture scenarios include cold/fresh checks, builds, tests, single-job runs, removal, a zero-sized output, a symlink, a directory output, a true compiler error and recovery, a wrapper, an explicit rustc, and disabled Ohm defaults. Verdicts and actual Rust command lines were checked with the A/B product builds. setup-stops preserves every setup failure separately.

Verify with `sha256sum -c SHA256SUMS` and `python3 -IB verify.py`.

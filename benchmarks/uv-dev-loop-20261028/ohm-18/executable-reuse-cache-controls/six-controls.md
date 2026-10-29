# Crossed same-predecessor uv build diagnosis

The prior executable-reuse comparison rejected its first build admission when the normalized library archives differed. It produced no timings. This diagnostic rebuilt one fixed-width private uv edit from a fresh copy of each preserved post-admission donor for every observation. The base driver is the earlier five-Cargo plus guarded-std stack (bc362fc8…). The candidate adds only the executable unused-self proof (db912558…). Both use the distributed Ohm-18 rustc (c6ab483d…), the same measured Wild (3b31c5ba…), fixed source and target paths, the same complete Cargo home image, -j8, rustc -Zthreads=8 and CPUs 0–15.

| Donor | Driver | Cargo / rustc / Wild | Standalone rmeta SHA-256 prefix | Original normalized rlib SHA-256 prefix |
| --- | --- | --- | --- | --- |
| Base-seeded | base-1 | 1 / 3 / 2 | 42e59d9aac286380 | 44609f76a33472ee |
| Base-seeded | base-2 | 1 / 3 / 2 | 42e59d9aac286380 | 44609f76a33472ee |
| Base-seeded | proof | 1 / 3 / 2 | 42e59d9aac286380 | 44609f76a33472ee |
| Proof-seeded | proof | 1 / 2 / 1 | 3885344fc12c15f7 | ea08cc894b3d5dca |
| Proof-seeded | base-1 | 1 / 3 / 2 | 3885344fc12c15f7 | ea08cc894b3d5dca |
| Proof-seeded | base-2 | 1 / 3 / 2 | 3885344fc12c15f7 | ea08cc894b3d5dca |

## Within-donor comparisons

Base-seeded donor. standalone metadata matched, the registered normalized archive matched, all named codegen-object hashes matched, all stable per-definition fingerprints matched.
Proof-seeded donor. standalone metadata matched, the registered normalized archive matched, all named codegen-object hashes matched, all stable per-definition fingerprints matched.

The base-seeded predecessor had no cached uvx unused-extern proof. The proof-seeded predecessor recorded the package library as unused. All six retained commands recompiled the uv package. Only proof Cargo on the proof-seeded predecessor skipped the uvx compiler process and its linker. None ran tests.

For this fixed next edit, the raw metadata value followed the donor. Changing Cargo on a fixed predecessor did not change it. This identifies an effect of the preserved incoming build state on this edit. The first admission lacked comparable hashes for its independently settled predecessors before the failing edit.

Across donors, the embedded lib.rmeta member was the only difference remaining under the original archive comparison. All 256 named LLVM object hashes matched across all six commands. Both executable products matched in raw bytes. The private and public crate hashes, public global fingerprint and all 16,664 stable per-definition fingerprints matched. The numeric definition ordering and the standalone metadata bytes differed by donor.

The six library invocations produced 1 distinct complete argv digests and 1 sorted effective-environment digests. Raw archive and executable bytes, emitted standalone metadata, all archive-member hashes, child exec traces and compiler environments are retained. The observed minimum free space from retained checkpoints was 153.17 GiB against the 120 GiB floor.

The first prior-stack control completed and its exec receipt survives. Its archive was lost when an optional metadata reader rejected an encoding before detachment. One registered identical replacement brought the total to seven Cargo launches and six complete observations. The replacement briefly parked when a JSON equality check compared ELF field tuples with serialized arrays. Independent hashes of all four stored and originating files, every archive member and canonical JSON agreed. That verification used the retained clone. The original rejected admission, damaged observation and both guard-failure receipts are preserved.

The original Cargo home and target inodes, driver slots and source bytes/timestamps were restored after every observation. All input home paths used matching contents, ownership, permissions, modification and access times, symlink targets and internal hardlink topology. Fresh disposable inodes and ctimes differ. The end-of-study audit rechecked the original Cargo home and both donor inventories.

## Files

* The frozen input and explicit capture exception are in protocol.json and capture-amendment.json.
* The observed directory contains per-PID exec traces, complete argv, environments, archive member hashes, six raw-capture manifests and fixture restoration receipts. Each raw capture identifies its SHA-256 object-store paths.
* summary.json and the two donor reports contain full digests. compare_donor.py, decode_complete.py and summarize.py reproduce those outputs using the separate, versioned metadata reader. The original product comparisons retain their frozen, narrowly scoped rules.

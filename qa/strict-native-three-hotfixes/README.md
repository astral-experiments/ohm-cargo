# Native Cargo CI for the strict native-input candidate

Cargo `761ea115605c34f11a1cd29afd68812c1e1359dd`, tree `19c379477ec24be16c82b952dc2e892c0563e2c7`, passed every one of its eight native CI jobs on the first run. The normal job commands, platform-specific target matrix, package installer hashes and test expectations come from this exact source. The test observer uses Linux executable tmpfs and native macOS APFS. [Frozen workflow](https://github.com/astral-experiments/ohm-cargo/blob/d7f0af36add4ef537d9e8332595ee5a7fa03f751/.github/workflows/ci.yml) · [Eight-job run](https://github.com/astral-experiments/ohm-cargo/actions/runs/41151353468)

| Standard cargo test -p cargo | Linux | macOS |
| --- | ---: | ---: |
| Passed | 4,827 | 4,799 |
| Suite-declared ignores | 433 | 430 |
| Failed or filtered | 0 | 0 |
| Additional pinned Ohm cases passed | 15 | 8 |

The stable integration executable’s complete name inventory matched the separately collected libtest output on each OS. Both ran the actual compiled profile cases, the same-process repaired crate regression, both GC lease controls and #292’s native-recheck cached-codegen regression. Linux also ran all three mount and handle controls. The full Linux workspace, resolver, schema, formatting, and Linux and macOS Clippy jobs passed. Workspace runs its inheritable-file-descriptor helper seven times under an intentional exact child filter. [Linux Cargo job](https://github.com/astral-experiments/ohm-cargo/actions/runs/41151353468/job/124388378735) · [macOS Cargo job](https://github.com/astral-experiments/ohm-cargo/actions/runs/41151353468/job/124388378717)

Run `python3 -IB verify.py` here to verify both compressed case inventories and all pinned profiles. The replay checks out the exact candidate named above. In an authorized checkout run `gh workflow run ci.yml --repo astral-experiments/ohm-cargo --ref charlie/qa-strict-native-eight-jobs-20261031`.

The source recipe proves that clean application of the complete three-fix delta to #292 and the complete strict delta to the three-fix release candidate produce the identical tree. It records both parents, every changed Git blob, the direction-specific patch IDs and where each compiler/reader fingerprint was introduced.

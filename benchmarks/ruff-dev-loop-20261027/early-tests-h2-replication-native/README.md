# Whole-workspace Ruff first-test selection on a second host

This packet contains only three entirely unscored, traced release arms for unmodified Ruff 93526150df with the exact historical test reversal 1b931047. Parent and candidate are authenticated matched PGO Cargo images. The third native control is the genuinely distributed Cargo. All use the official release 1.99.0-16 compiler, SDK, system GCC and bundled Wild. The 16 fixed logical CPUs and tmpfs on H2 are separate from the original ext4 H7 cohort.

Every block cold-compiles and settles an independent 617-unit seed excluding ty_server, then independently restores the actual pre-selection source and outputs for both arms. The fully trained ty_server normal library is a dependency even when its tests are excluded. The selected workspace emits 619 Cargo artifacts, 102 executables and 110 native products. There are 84 test-profile executables and 18 ordinary binaries or examples. All 110 raw ELF hashes and diagnostics agree between the ordinary and guarded arms in each source state. The first complete selection classified two distinct test outputs; the native unscored references differentiate a duplicate physical compile and link from the one legitimate e2e compiler.

The edited e2e caller listed 200 tests and inlay_hints::default_inlay_hints returned pass (exit 0); after genuine source restoration it returned pass (exit 0). The unchanged selection and unchanged restoration were entirely fresh. The historical edit and restoration changed exactly one reported native product, the actual e2e test binary. Tests were executed only as post-command behavior checks outside any timed command.

| Release arm | Whole selection rustc / Wild | Actual e2e rustc / Wild |
|---|---:|---:|
| A | 3 / 3 | 2 / 2 |
| B | 3 / 3 | 2 / 2 |
| C | 2 / 2 | 1 / 1 |

The workspace study had zero elapsed observations at this gate. None of the traced command durations are used in a performance estimate. The first setup stopped before any Cargo artifact, because a private rustup mount was absent. A subsequent original-release seed correctly produced the pre-existing dead-code warning. The full warning JSON, including its two spans, matched H2 and five independent H7 records byte for byte after replacing only the known source root. Both historical setup failures and the private lossless seed archive are bound in the two setup receipts. Run analyze-admission.py to verify those distinct phases.

Run python3 -B verify.py to recheck the released image bindings, rosters, raw ELF hashes, ordinary caller status and complete matched records. The durable SHA-256 commitments point to the lossless private before/after inputs and full native command traces on H2. The H2 source holds all flags, placements, storage checks, exact historical patch and original boot-time setup failure.

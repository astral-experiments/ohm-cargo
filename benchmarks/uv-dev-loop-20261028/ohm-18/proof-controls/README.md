# Cargo executable reuse on Ohm -18

The release-only regression test changes the private implementation of a package library. One binary calls the library, and a second binary and its test harness leave it unused. Released Cargo relinked the second binary and its harness. Cargo with the patch reused both outputs and rebuilt the binary that needed the new implementation.

The same Cargo testsuite test ran against two separate builds of release commit `7caf39914da1e28a67744ecbc963a5f26361474d`. The release control contains only the test change. The treatment contains the same test and the production patch. The verified binaries have distinct SHA-256 digests and the expected implementation symbols. Two preliminary runs are archived separately. The first checked the wrong label for a cold compile-and-link event. The second shared a target directory and selected the patched binary as its control. The displayed result comes from the corrected fixture and separate targets.

On a completely warm uv workspace, the new code showed no material Cargo-process regression on either counter. Each cell contains 12 order-balanced randomized pairs. The table gives paired median instruction savings with 96.14% intervals. The two counters used independent checkout roots and the same fast Cargo control and candidate executables used by the edited-command experiment.

| Command | DynamoRIO | Cachegrind |
|---|---:|---:|
| `cargo check` | 0.004% (−0.022% to 0.016%) | 0.003% (−0.005% to 0.009%) |
| `cargo build` | 0.014% (−0.010% to 0.023%) | 0.000% (−0.004% to 0.014%) |
| `cargo test --no-run` | 0.017% (−0.020% to 0.030%) | 0.006% (−0.006% to 0.021%) |

All 144 measured Cargo commands had fresh packages. Every test-preparation command reported the same 72 executable targets. The preregistered material-regression bound was 0.5%. Edited-command wall time is measured separately.

From an extracted copy of `raw-and-scorer.zip`, run `sha256sum -c SHA256SUMS` and `python3 proof-warm-score.py` using Python 3.11 or later. The scorer reads every raw log, checks the registered assignment and produces `results.json`. The official Cargo test logs, source and binary identities, and the applied production and test patches are under `regression/`.

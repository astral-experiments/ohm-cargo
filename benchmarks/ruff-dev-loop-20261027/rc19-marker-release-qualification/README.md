# Ohm 1.99.0-19 release sign-off

**I’d start the protected `1.99.0-19` release workflow after the release manifest lands on `main`.** This applies to the three exact revisions below. Both the published `-17` and `-18` Linux Cargo executables overwrote an unrelated file when an Ohm cache marker was a symlink to it. The candidate fixed the five observed writes. Linux and macOS Cargo and compiler validation passed. The normal release workflow still needs to produce, install and smoke-test the official packages.

| Component | Exact qualified revision | Pull request |
| --- | --- | --- |
| Cargo | `235f9228651b74c591e6f62cae4c9b761448dd2d` | [astral-sh/ohm-cargo#274](https://github.com/astral-sh/ohm-cargo/pull/274) |
| Rust | `5cf1bf9cd196046897a7aeeaf128833d6a464dfe` | [astral-sh/ohm-rust#249](https://github.com/astral-sh/ohm-rust/pull/249) |
| Release manifest | `49ba4f5bb311a193905f759f7748e3aa5c3cd814` | [astral-sh/ohm#201](https://github.com/astral-sh/ohm/pull/201) |

On two independent Linux hosts, the corrected Cargo replaced each final symlink with a regular marker and preserved the file at its destination. A released `cargo build` could trigger the overwrite with all artifacts already fresh. A deliberately symlinked user manifest still behaved normally with `cargo add`. A conventional Cargo integration test failed at the external file's contents on the released executable and passed with the fix. These checks cover the five marker writes and their final path components. [Released regression and reproducer](https://github.com/astral-sh/ohm-cargo/tree/43aedc5b8aff9868d81d5c166dac56446821d434/benchmarks/ruff-dev-loop-20261027/rc18-worktree-marker-symlinks) · [Source-bound fixture, ordinary worktrees and test results](https://github.com/astral-sh/ohm-cargo/tree/61923deedae198a997d1797a2583a2d84558055b/benchmarks/ruff-dev-loop-20261027/rc18-marker-symlink-fixed-acceptance)

Relative to `-18`, the Rust source change is one Cargo gitlink and the release manifest selects that Rust and Cargo. The Clippy and rustfmt revisions and the bundled stock Wild 0.11.0 archive checksum match `-18`. Eight Cargo jobs, three Rust jobs and three packaging checks passed. Cargo's branch-conditional Clippy APFS replay was skipped. The Linux native fixture used the source-bound development-profile Cargo binary recorded in `bindings.json`. The release team still owns publication of the official packages. [Cargo CI](https://github.com/astral-sh/ohm-cargo/actions/runs/40773392297) · [Rust CI](https://github.com/astral-sh/ohm-rust/actions/runs/40775131467) · [Packaging CI](https://github.com/astral-sh/ohm/actions/runs/40775384825)

The three pull requests were drafts when qualified. The latest published release at the recorded snapshot was `-18`. The experimental Ruff scheduling work is separate from this release. Run `sha256sum -c SHA256SUMS` and `python3 -IB verify.py` in this directory to verify the enclosed manifest and check receipts.

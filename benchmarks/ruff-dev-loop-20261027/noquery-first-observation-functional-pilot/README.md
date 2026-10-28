# First observer acquisition without a capability subprocess

These native controls use Rust's actual proc-macro span observer, compiled independent programs, raw rustc dep-info and Cargo's encoded fingerprint. The compiled observer imports an external Rust library through a path containing a space. It also reads a UTF-8 source file named `incidental.rlib` with `include_bytes!`. The ordinary checksum header and that source filename are present on both compiler builds. Only the newer compiler emits a separate checksummed record identifying the full input list.

| Cargo source | Supporting Rust on the first build | Compiled observer after a same-length external library edit | Next unchanged build |
| --- | --- | --- | --- |
| Base `a0c7d08c` | Records an incomplete observation with zero capability queries | Once, producing 29 | Fresh |
| Probe `97c04e44` | Runs a capability query and captures the complete observation | Once, producing 29 | Fresh |
| Producer record `b538e174` | Captures the complete observation with zero capability queries | Once, producing 29 | Fresh |
| Producer record with older Rust | Records an incomplete observation with zero capability queries | Once, producing 29 | Fresh |

Every original program printed 17. The edit preserves the actual library inode, length and nanosecond mtime. Every independently compiled edited program printed 29. The final independent cold run repeats each arm's own first-observer behavior. The Rust source revision is `337a07a79cf8f2b9466cf8593344e5a9c479a927` and the older compiler subtree is identical at `4c0f6097` and `bfa236f6`. Both run through the identical native `rustc` frontend. `build-controls.json` binds the exact three native Cargo executables and their PGO compilation. Each used its own build-state clone. Their compiler argv match, but independent builds produced three to four different dependency `.rmeta` files. These binaries establish functional behavior and are ineligible for time comparisons.

## Scope

The earlier functional runs switched the loaded driver behind the same physical frontend in place. Real source edits and backdated extern edits returned 29 across both directions. An opaque `RUSTC_WRAPPER` kept the observer incomplete even when the new compiler wrote a record. Disabling the proc-macro cache withheld the optional record. The next known-observer compilation still captured ordinary explicit binary dependencies. The Cargo unit rejects truncated or conflicting records and records describing a different output, ordinary checksum, source set or environment. The Rust run-make compares the decoded first-observer payload to a separately requested binary-dep-info compilation.

A separate small Cargo workspace builds the real `ron 0.12.0` pinned in Ruff's lockfile and four integration tests. On the first cold command, A and N each launched 27 rustcs and 15 native linkers. On the first unchanged command A launched one full rustc for ron, five link-only rustcs and five native linkers. N launched none. On the next unchanged command all 23 artifacts were fresh in both arms. Each arm preserved its five executable hashes through these repeats. Independent target directories gave distinct integration-test ELF hashes across arms. All four tests executed and passed. These are job counts on a constructed registry workspace. Whole-Ruff wall or instruction measurements require their own registered endpoints.

## Reproduction

Run `python3 -B verify.py` next to this file. It checks the complete product images, real Cargo/ELF receipts, probe counts and contents of the raw native record archive. `workers/` contains the original study programs including the runner that binds each qualified Cargo over the same compiler SDK path. `heldout-fixture/` contains all 16 checked Rust and TOML files. The production Rust and Cargo source diffs and the permanent run-make case are supplied with the packet. The workers name study-local private toolchain and build-state paths for the native rerun. The offline verification requires Python 3.11 or newer.

The development Cargo executables used for the earlier wrapper, driver and ron mechanism checks are recorded in `observations.json`, separately from the release-built sources in `native-release.json`. Four intermediate harness observations covering the wrapper exec classifier, old/new fingerprint namespaces, one expected query on unsupported Rust, and initial missing registry/symlink mounts are preserved under `prior_parser_failures`. No wall-time observation was collected in these trials.

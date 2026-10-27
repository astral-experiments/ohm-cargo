# Ordinary binary include paths in the Ohm 1.99.0-16 cache

A single Rust binary embeds four bytes with `include_bytes!`. The real file initially contains 17 in its first byte. A separate literal backslash-space neighbor contains 29. The released compiler loads the real file for the program and records the neighbor’s BLAKE3 checksum in its depfile. After the real byte changes to 29 with the same length and timestamp, Cargo incorrectly accepts the existing binary, which still prints 17. An empty build prints 29.

The check-only version requires an array of length 17. After the same file change, a warm `cargo check` exits successfully. A clean check emits E0308. The crate has no dependencies, proc macro, custom build script or foreign-span observer.

| Case | Shipped Cargo after the edit | First attempted Cargo migration | Independent empty state |
| --- | --- | --- | --- |
| Binary with the spaced input and matching neighbor | Fresh, prints 17 | Fresh, prints 17 | Prints 29 |
| Invalid typed array with the same input | Fresh, exits 0 | Fresh, exits 0 | E0308, exits 101 |
| Spaced input without a neighbor | Recompiles, correct output or diagnostic | Correct output or diagnostic | Same |
| Ordinary hyphenated input | Fresh when untouched, correct after the edit | Correct output or diagnostic | Same |

The first migration recognized old foreign-span records. This experiment independently shows why the ordinary checksum format also needs migration. The affected Cargo file and all three Rust production files had identical blobs in released 1.99.0-16 and its initially prepared 1.99.0-17 manifest.

Additional runs used a symlink with a space and a space in the absolute package root. Both ordinary builds and checks returned stale results with each spelling. Default Ohm retained the spelling in its worktree-capable format. With worktree seeds disabled and ordinary checksum freshness enabled, the old cache reduced both paths to `ordinary-input/value.bin`. None of the four affected records retained a space in any stored filename. The original unscored diagnostic expected canonicalization under default Ohm and stopped after its five completed commands. Its records and error are retained separately.

Run `python3 reproduce.py` on Linux with an installed Ohm toolchain to repeat the basic warm and clean build/check controls. `--toolchain NAME` selects a different linked installation, and `--keep NEW_DIRECTORY` retains every source and Cargo output. Shipped `-16` returns 17 and exit 0 from its changed warm commands. A corrected compiler and Cargo should agree with the two clean references.

`python3 -B verify.py` checks all 70 captured Cargo commands, 35 recorded native outputs, and the original Cargo/rustc depfiles. The archive includes all emitted Cargo JSON and stderr, encoded paths, checksum lines and a later re-execution of both retained binaries in each build case. The initial input bytes and neighboring bytes have distinct BLAKE3 digests. The verifier requires each poisoned depfile to contain the digest of the neighbor before the real input changes.

The independent four-crate test exercises foreign spans. [Earlier observer-only migration](https://github.com/astral-sh/ohm-cargo/tree/4502783bc030439a87a2eccf0001c07926f48218/benchmarks/ruff-dev-loop-20261027/spaced-checksums-cargo-migration) · [Original released path and FIFO controls](https://github.com/astral-sh/ohm-cargo/tree/dfcbdbd318e5bfa1154ae1537b02df7bdb2d79b0/benchmarks/ruff-dev-loop-20261027/released16-spaced-checksums)

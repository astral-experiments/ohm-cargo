# Cargo native-build to metadata-check regression

Ruff's `ruff_linter` checks the registry library `pep440_rs` directly. A previously built `pyproject-toml` can load its native copy as a transitive dependency. Since `pep440_rs` also produces a cdylib, Cargo keeps the direct dependency in check mode. One rustc invocation can then see two incompatible copies of the same Rust type.

The source patch rejects a promoted ancestor when both variants can enter one consumer's Rust library graph. Separate roots, procedural macro runtime dependencies and build scripts have separate consumers. The recorded check uses the exact submitted source and regression. The Cargo and release compiler SHA-256 values are in `subjects.json`.

## Portable reproduction

Install separate rustup toolchains for unmodified and fixed Ohm Cargo, with the same compiler in both. From this directory run

```sh
python3 reproduce.py --toolchain ohm-parent --expect baseline
python3 reproduce.py --toolchain ohm-fixed --expect fixed
python3 verify.py
```

The reproducer needs Python 3.11 or later and runs offline with three new path-only workspaces. Each case performs a native build, a warm check, and an independent check from an empty target and build directory. With shared compiler stages on, baseline Cargo fails with a StableCrateId collision. With stages off, the same typed program fails with E0308. Both fixed checks succeed. The pure-rlib variant emits five fresh artifacts in both warm checks. The actual compiler invocations in `actual-rustc-metadata.json` explain why comparing only `-C metadata` misses the second failure.

## Checked-in tests

The new Cargo testsuite case uses a fake registry containing a library that produces rlib and cdylib, an ordinary rlib bridge, and an independent rlib. The project both declares its return type as the mixed library's type and calls the bridge to produce it. It requires the bridge and mixed dependency to be checked while the independent dependency remains fresh. We compiled the exact registered test function with its existing Cargo test-support crate and original command helper. Under both the matched #232 release compiler and the corrected #233 release compiler, the baseline test fails with the expected collision and the final test passes.

We also ran six pre-existing registry, build-helper and artifact-dependency tests from the original testsuite executable. Applying the explicit defaults opt-out uniformly to each build and check makes all six pass on both Cargo versions. With ordinary packaged defaults, both versions pass the same three tests. The other three strict stderr snapshots expected workspace roots to be checked or an unadorned rustc argv. When only nightly-labeled calls consume the inherited opt-out, four tests fail identically on both arms because the build and check use different policies. The test harness marks ordinary builds stable. `results.json` identifies every case and `raw-output.json.gz` contains each assertion and command output. These are correctness observations, with no elapsed-time claim.

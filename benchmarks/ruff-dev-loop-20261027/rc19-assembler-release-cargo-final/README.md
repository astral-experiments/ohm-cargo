# Release-profile Cargo qualification for the assembler fix

The Cargo binary built from commit `a8f0c9aa04` fixes the tested assembler failures under the defaults. Explicit `-Zrelink-only=yes` still produces a stale executable. The packaging draft still pins the affected predecessor. [Cargo #282](https://github.com/astral-sh/ohm-cargo/pull/282) · [Packaging #202](https://github.com/astral-sh/ohm/pull/202)

| Linux x86-64, real Rust dependency edit | Default | Explicit cached relink | Empty build |
| --- | --- | --- | --- |
| Replace an assembler input containing 17 with 29 | `9:29` | `9:17` | `9:29` |
| Remove the input and change the Rust result to 7 | Cargo 101 | Cargo 0, prints `7:17` | Cargo 101 |

The executable forbids unsafe code in its own source. A dependency supplies the generic inline assembly that rustc instantiates. These commands use `CARGO_INCREMENTAL=0`. An exact unchanged repeat performed no compiler work for either setting. In a separate ordinary integration test and binary using the checked-in regression sources, the default reread the changed file for both native targets. Removing it produced two missing-file observations. The previously built executable still on disk printed `22:66` after Cargo returned 101. It was the incumbent executable. [Origins on released toolchains and default behavior](https://github.com/astral-sh/ohm-cargo/tree/ddc37dc81d391b0d100bbc9a2ecdd493ab3d25b9/benchmarks/ruff-dev-loop-20261027/rc19-assembler-default-fallback)

## Upgrades from published Ohm 1.99.0-19

Two independently populated targets started with the published Cargo. One upgrade installed this Cargo with the optimized compiler and 53 target-library files built from Rust `ca780121`. The other changed only Cargo and kept the published compiler. Both caught the ambiguous call on the first and second unchanged checks. The E0034 diagnostic and primary span matched an empty build. Both produced the reverted program, which printed `1`, on the first build after a failed compile.

Two native-provider histories per compiler started with cached byte 17. The first post-upgrade command returned 29 or failed on the malformed archive according to the independently prepared input. Each successful unchanged repeat ran zero compilers and linkers. Reversing the input reversed the outcome. The upgraded Cargo and all four histories used the same stock Wild binary. [Native provider and upgrade reproducer](https://github.com/astral-sh/ohm-cargo/tree/99e90db029089bf5f1fe335b3fc7b42a7ef20c0f/benchmarks/ruff-dev-loop-20261027/rc19-native-same-stamp-migration)

## Source and binary checks

The two PGO builds used the same profile, both rustc command lines, 239 independent compiler arguments that name crate artifacts, and 335 physical linker inputs including 326 rlibs. The source revision, full Cargo version, compiler and linker identities, and digests for the private build records are in `subjects.json`. Eight applicable checks passed on the exact commit. [Hosted CI](https://github.com/astral-sh/ohm-cargo/actions/runs/40841955598)

The first attempt to reuse the historical parent stopped because its temporary build directory had expired. Rebuilding the same parent reproduced the executable code but gave a different whole-file digest. All 69,007 symbols had the same values, types and binding. One LLVM-generated suffix changed on 232 local symbol names, increasing the non-loadable string table by 232 bytes. Across all four loadable segments, the only differences were the 32-byte GNU build ID and the ELF section-table offset. The comparison uses the reconstructed parent bound by its own digest. No wall-time samples are included here.

## Replay

Verify the portable observations. Each recorded Cargo verdict is accompanied by the original stream digests. The private full traces and native binaries are represented by their checksums.

```sh
sha256sum -c SHA256SUMS && python3 -IB verify.py
```

To rerun the assembler cases, use a Linux x86-64 host with strace, Python, rustup, a complete private SDK and fresh output directories. `CARGO_SOURCE` must contain the Cargo source used for the checked-in fixture.

```sh
python3 -IB reproduce-generic.py "$NEW_OUTPUT/generic" "$SDK"
python3 -IB reproduce-native-test.py "$NEW_OUTPUT/native" "$SDK" \
  "$CARGO_SOURCE/tests/testsuite/freshness.rs"
```

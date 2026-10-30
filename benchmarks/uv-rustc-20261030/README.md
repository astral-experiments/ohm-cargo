# Ohm rustc on the first build after editing uv

On x86-64 Linux, teaching rustc to recognize two file-free assembly templates cut the median time to rebuild uv’s `tool` integration test from 4.757 s to 2.712 s. The median paired speedup was **1.771×**, with a 96.14% exact interval of **1.708–1.843×**. All 12 paired builds improved. The largest speedup was 1.943×.

| Measured workflow | Control median | Candidate median | Median paired saving |
| --- | ---: | ---: | ---: |
| First `cargo test --locked --offline -j8 -p uv --test tool --no-run` after the edit | 4.757 s | 2.712 s | 2.038 s |

The control used the source shipped in Ohm 1.99.0-20 plus the existing libm assembly fix. The candidate added one compiler line for the x86-64 `# {reg}` barrier used by `zeroize` and the unsigned `div {reg}` used by `num-bigint`. Both matched SDKs were built from source. Their 64 common files, including Cargo, Wild, LLVM and the target standard library, were identical. Only the rustc driver differed. [Ohm release](https://github.com/astral-experiments/ohm/releases/tag/ohm-1.99.0-20) · [Existing libm PR](https://github.com/astral-experiments/ohm-rust/pull/270)

The uncommitted edit removed a 62-line integration test from `crates/uv/tests/tool/tool_list.rs` on uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`. Each invocation started from a separate copy of its compiler’s warm, pre-edit checkout and target. Six pairs ran the control first and six ran the candidate first. Their median speedups were 1.771× and 1.763×. The two-sided exact sign test against 1× gave p = 0.000488. All 12 pairs also fell below 2×. The separate 1.806× pilot was excluded. [Original uv change](https://github.com/astral-sh/uv/pull/20770)

Separate traced runs showed eight rustc commands and three linker invocations with the control, versus one rustc command and one linker invocation with the candidate. Five dependency files on the control contained an always-missing input that forced Cargo to recompile. The candidate removed all five. The output bytes for `uv`, `uvx`, and the test executable agreed. Both compilers listed the same 180 tests after the edit, down from 181. The ordinary timings cover the complete untraced Cargo command. Listing tests and verifying artifacts happened outside the clock.

The regression fixtures exercise register, literal, symbol, memory, malformed and external-file forms. A normal Cargo fixture also changes, removes and restores an actual assembler input and checks that the new compiler rebuilds the affected output.

## Reproduce

[Raw observations and standalone verifier](tool-test-pairs.zip) · [Per-pair clocks](tool-test-pairs.csv) · [Machine-readable statistics](tool-test-result.json) · [Fresh-run scripts, exact compiler patches and SDK identities](rerun.zip)

Unpack `tool-test-pairs.zip` and run `python3 -ISB fresh-edit/verify.py` to recompute the times, verify all three output hashes and check the test inventory. To run fresh builds, unpack `rerun.zip` and follow its `README.md` and `REBUILD.md`. `PACKAGE.md` covers the full `cargo test -p uv --no-run`. Both runners pin Git abbreviation in their private clone and check the uv version description.

# Ohm rustc on the first build after editing uv

Recognizing two register-only x86-64 assembly templates in rustc sped up the first full uv test build after a real test edit by **3.183×**. All 12 pairs exceeded 2×. The complete Cargo command went from a median **9.973 s to 3.233 s**.

| Build after the edit | Control median | Candidate median | Median paired speedup (96.14% interval) |
| --- | ---: | ---: | ---: |
| `cargo test -p uv --no-run` | 9.973 s | 3.233 s | 3.183× (2.988–3.330×) |
| `cargo test -p uv --test tool --no-run` | 4.757 s | 2.712 s | 1.771× (1.708–1.843×) |

Both commands used `--locked --offline -j8` on x86-64 Linux.

The control used the source shipped in Ohm 1.99.0-20 plus the existing libm assembly fix. The candidate added one compiler line for the x86-64 `# {reg}` barrier used by `zeroize` and the unsigned `div {reg}` used by `num-bigint`. Both matched SDKs were built from source. Their 64 common files, including Cargo, Wild, LLVM and the target standard library, were identical. Only the rustc driver differed. [Ohm release](https://github.com/astral-experiments/ohm/releases/tag/ohm-1.99.0-20) · [Existing libm PR](https://github.com/astral-experiments/ohm-rust/pull/270)

For the targeted test, the uncommitted edit removed a 62-line integration test from `crates/uv/tests/tool/tool_list.rs` on uv `c22e6b71933443e9cd299d4b6ac8de035ed4825b`. Each invocation started from a separate copy of its compiler’s warm, pre-edit checkout and target. Six pairs ran the control first and six ran the candidate first. Their median speedups were 1.771× and 1.763×. The two-sided exact sign test against 1× gave p = 0.000488. All 12 pairs also fell below 2×. The separate 1.806× pilot was excluded. [Original uv change](https://github.com/astral-sh/uv/pull/20770)

Separate traced runs showed eight rustc commands and three linker invocations with the control, versus one rustc command and one linker invocation with the candidate. Five dependency files on the control contained an always-missing input that forced Cargo to recompile. The candidate removed all five. The output bytes for `uv`, `uvx`, and the test executable agreed. Both compilers listed the same 180 tests after the edit, down from 181. The ordinary timings cover the complete untraced Cargo command. Listing tests and verifying artifacts happened outside the clock.

The regression fixtures exercise register, literal, symbol, memory, malformed and external-file forms. A normal Cargo fixture also changes, removes and restores an actual assembler input and checks that the new compiler rebuilds the affected output.

## Full-package test preparation

The single uncommitted edit removes 62 lines from `crates/uv/tests/tool/tool_list.rs` at uv `c22e6b7`. Each arm restored its own untouched A history before timing the first unwrapped `cargo test --locked --offline -j8 -p uv --no-run`. The A and B test inventories were checked outside the clock.

C and CZD were rebuilt from the same Ohm −20 compiler source with the x86 libm classifier from #270 present in both. CZD adds the two register-only patterns in this PR. The median first build went from 9.973 s on C to 3.233 s on CZD. The median of the 12 paired speedups was 3.183× (96.14% exact median interval 2.988–3.330×). The six C-first pairs had a median of 3.179× and the six CZD-first pairs 3.183×. 12/12 exceeded 1× and 12/12 exceeded 2×. The two-sided exact sign-test p-values were 0.000488281 and 0.000488281, respectively. The registered 10-test Holm-adjusted p against 2× was 0.00488281. The combined package result met the registered criterion. The separate 2.891× pilot (9.395 → 3.249 s) was excluded. The traced admission launched 22 rustc and 17 linker processes for C, and 1 rustc and 1 linker processes for CZD. All 15 test-list outputs and both CLI version outputs agreed between compilers. The edit removed one test (3298 → 3297 listed package-wide). For B, `tests/pip_install/main.rs` (33 bytes) had two raw SHA-256 values. Each reciprocal comparison changed only the low byte of `.rodata.sh_entsize` (0/8) and the derived GNU build ID. The section header lies outside every loaded segment. All other bytes agree, including executable code, symbols and relocations. The native window ran from 2026-10-30T08:46:18Z to 2026-10-30T09:11:05Z.

The separate run on rebuilt Ohm −20 without #270 stopped before the edit. Two consecutive warm builds with the same candidate compiler produced the two previously predicted hashes of `pip_install`. Its rule required identical raw hashes within each compiler. That run contributes zero edited pairs and p = 1. The rerun kit now enforces this same rule in both its runner and its scorer. The earlier kit also allowed the two hashes within a compiler. All recorded warm builds in the completed 3.183× experiment pass the corrected check. [Standalone records and replay](standalone-warm-exclusion.zip)

The PR head `2035696c` reformats one line in the regression fixture. Its compiler implementation matches the measured PR leaf.

The two earlier package attempts each contribute zero usable pairs and p = 1. The first failed strict raw equality on `pip_install`. The second stopped during admission on the uv CLI unit-test harness. Both involved 0/8 in the merged read-only section header and its derived 32-byte GNU build ID. The new protocol froze each role’s allowed raw image(s) from a fresh control before running the candidate.

[Raw combined packet and detached verifier](package-test-v3-combined.zip) · [Per-pair CSV](package-test-v3-pairs.csv) · [Machine-readable scope and scores](package-test-v3-result.json)

## Reproduce

Download the [one-command verifier](replay-combined.py) and the [full-package observations](package-test-v3-combined.zip) into the same directory. Python 3.11 or newer can recompute the wall times and confidence interval without a compiler SDK.

```sh
python3 -ISB replay-combined.py package-test-v3-combined.zip
```

The verifier checks the downloaded packet’s digest and replays the original scorer on its 12 raw pairs. To measure fresh builds on another machine, use the source and compiler instructions below.

[Raw observations and standalone verifier](tool-test-pairs.zip) · [Per-pair clocks](tool-test-pairs.csv) · [Machine-readable statistics](tool-test-result.json) · [Fresh-run scripts, exact compiler patches and SDK identities](rerun.zip)

Unpack `tool-test-pairs.zip` and run `python3 -ISB fresh-edit/verify.py` to recompute the times, verify all three output hashes and check the test inventory. To run fresh builds, unpack `rerun.zip` and follow its `README.md` and `REBUILD.md`. `PACKAGE.md` covers the full `cargo test -p uv --no-run`. Both runners pin Git abbreviation in their private clone and check the uv version description.

The [full-package protocol](complete-package-protocol.json) and [separate comparison without #270](standalone-package-protocol.json) were published before the respective timing runs. The reproduction archive covers both comparisons.

A separate 12-pair comparison will measure the complete #270 and #275 compiler stack against bare Ohm −20 source. Its two arms independently start from the same real uv edit. [Prospective plan](full-stack-protocol.md) · [Machine-readable protocol](full-stack-protocol.json)

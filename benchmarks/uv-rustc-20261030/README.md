# Ohm rustc on the first build after editing uv

On x86-64 Linux, recognizing two register-only assembly templates in rustc sped up the first build of uv’s production binaries after an edit to `uvx` by **4.235×**. The same compiler change sped up the first full test build after removing a uv integration test by **3.183×**. Both comparisons used Ohm −20 with Rust #270 as the control. All 12 pairs in each comparison exceeded 2×.

| Build after the edit | Control median | Candidate median | Median paired speedup (96.14% interval) |
| --- | ---: | ---: | ---: |
| `cargo build -p uv --bins` | 3.578 s | 0.845 s | 4.235× (3.884–4.712×) |
| `cargo test -p uv --no-run` | 9.973 s | 3.233 s | 3.183× (2.988–3.330×) |
| `cargo test -p uv --test tool --no-run` | 4.757 s | 2.712 s | 1.771× (1.708–1.843×) |

All three commands used `--locked --offline -j8` on x86-64 Linux.

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

To reproduce this comparison on x86-64 Linux, unpack the [full-stack rerun kit](rerun-full-stack.zip) and follow `FULL-STACK.md`. Supply the P and CZD SDKs, a uv clone and the offline Cargo cache. The kit compares bare Ohm −20 against both compiler patches together. It checks the first edited build in 12 new pairs.

## Shipped releases

The shipped Linux toolchains ran each of the same two edits from its own initially empty target directory. Each cell is one ordinary Cargo invocation. The 12-pair experiments above used source-matched −20 compilers.

| Shipped SDK | Unchanged production build | First build after launcher edit | Unchanged full test build | First test build after test edit |
| --- | ---: | ---: | ---: | ---: |
| Ohm −18 | 0.608 s | 1.671 s | 0.627 s | 2.037 s |
| Ohm −20 | 3.946 s | 3.734 s | 9.849 s | 9.710 s |

After the launcher edit, Cargo printed one package name on −18 and 76 on −20. The invocation timestamps changed for one and eight build units, respectively. Within each release, the launcher edit changed the complete `uvx` executable and left the `uv` executable byte-identical. Forwarded argument bytes, exit status and version outputs agreed across releases. The test edit produced matching inventories for all 15 test harnesses and matching CLI version outputs.

Ohm added the LLVM backend’s assembly classifier between −18 and −20. The matched compiler experiments measure a change to that classifier. [Compiler change](https://github.com/astral-experiments/ohm-rust/commit/960c75a231a4bed61cb9fcfac744ea37161ea23d)

Replay either downloaded archive with `python3 -ISB <archive>`. [Production build clocks and verifier](ohm-18-20-uvx-production-bins.zip) · [Full test build clocks and verifier](ohm-18-20-uv-release-context.zip)

## Production settings edit

Both compilers completed `cargo check --locked --offline -j8 -p uv` after an edit to `ToolListSettings`. The change dirtied the uv library and its two binaries on each compiler. Each check launched three rustc processes and zero linkers. The separate timing experiment stopped before collecting pairs because the two warm metadata files had different bytes. The trace packet includes the commands, process records and an independent replay. [Check trace and replay](production-check-trace.zip)

On the same edit, `cargo build -p uv` ran eight rustc processes on the control and three on the candidate. Each ran two linkers, and both resulting binaries matched byte-for-byte. The ordinary build had also stopped before collecting timing pairs because the initial library archives differed. [Build trace and independent replay](production-build-trace.zip)

## Production launcher edit

The edit changes how `uvx` forwards arguments to `uv tool run`. It changes one Rust source file in a temporary uv checkout at `c22e6b7`. Each compiler restored an independent pre-edit target, ran the normal build once and then timed the first `cargo build --locked --offline -j8 -p uv --bins` after applying the edit. The command builds both production programs. [Original uv change](https://github.com/astral-sh/uv/pull/22742)

The median build went from **3.578 s to 0.845 s**. The 12 paired speedups ranged from 3.508× to 5.057×, with a median of **4.235×** and a 96.14% exact median interval of 3.884–4.712×. The six control-first pairs had a median speedup of 4.396× and the six candidate-first pairs 4.206×. All 12 exceeded 2×. The two-sided sign test against 2× gave p = 0.00048828125 and the Holm-adjusted p across the 13 registered comparisons was 0.00634765625. The separate 3.786× pilot was excluded.

In a separate traced build, the control recompiled five dependencies (`zeroize`, `num-bigint`, `num-bigint-dig`, `rsa` and `secret-service`), then compiled and linked both binaries. The candidate compiled and linked only `uvx`. The produced `uv` and `uvx` files matched byte-for-byte between compilers before and after the edit. Within each compiler, only `uvx` changed. The command-line checks covered forwarded argument bytes and exit behavior, including empty arguments and non-UTF-8 input.

[Original clocks and verifier](production-uvx-observations.zip) · [Per-pair CSV](production-uvx-pairs.csv) · [Compiler trace](production-uvx-trace.json) · [Whole-file checks](production-uvx-whole-elf.json) · [Fresh-run instructions and compiler checks](rerun-production-uvx.zip)

To replay these 12 pairs, extract the production build kit and run the command below from its directory with the downloaded observations.

```sh
python3 -ISB production_score_after_48597.py /path/to/production-uvx-observations.zip \
  --outer e5a71756f357aa1d2ed49690abd935a09e7ac899cf1718f5b4d02604b9cebc26 \
  --packet-sha256 bcffde0aed9a5d35b4f16b141bc965fb83f0671bd5d59ad039d518127168ab5f
```

## Bare Ohm −20 and both compiler patches

A separate 12-pair comparison measured both Rust patches together against the bare Ohm −20 compiler source. Both compilers were rebuilt with the same settings. The first full uv test build after removing the same integration test went from **9.957 s to 3.304 s**. The median paired speedup was **3.026×** (96.14% exact interval 2.770–3.592×). The 12 speedups ranged from 2.609× to 4.052×. The control-first median was 2.824× and the candidate-first median was 3.375×.

All 12 pairs exceeded 2×. The two-sided sign test against 2× gave p = 0.00048828125. After Holm adjustment across all 14 registered comparisons the p-value was 0.0068359375. Both previously confirmed comparisons also have adjusted p = 0.0068359375 in this family.

A separate trace showed 23 rustc processes and 17 links on bare −20, versus one rustc process and one link with both changes. All 15 test lists and both CLI version outputs agreed across compilers. The edit reduced the package inventory from 3,298 to 3,297 tests. Across all 24 timed outputs, 16 of 17 programs matched byte-for-byte. The two allowed images of the remaining `pip_install` test differed at one byte of a section header outside every load segment and at the associated 32-byte GNU build ID. Every other byte matched.

The earlier combined attempt stopped after the control warm-up. It contributed zero edited pairs and p = 1. The completed comparison used that verified unedited control history and a fresh independent candidate history. It had no pilot or excluded timed pairs. [First attempt](full-stack-first-attempt.zip) · [Published decision rule](https://github.com/astral-experiments/ohm-cargo/blob/bac6e783130f95c0ac78b3255f468a0fddbcc4fb/benchmarks/uv-rustc-20261030/full-stack-after-uvx-protocol.md)

[Observations and independent verifier](full-stack-after-uvx-observations.zip) · [12 paired clocks](full-stack-after-uvx-pairs.csv) · [Full executable verification](full-stack-after-uvx-elf-replay.json) · [Fresh-run kit](full-stack-after-uvx-rerun.zip)

To replay the recorded comparison with Python, run the following in a directory containing the observations.

```sh
unzip -p full-stack-after-uvx-observations.zip verify.py > verify-fourteen.py
python3 -ISB verify-fourteen.py full-stack-after-uvx-observations.zip \
  --outer 0b464d05ebe19989694c08b2cd5775b5227dc23dd111750246617d25309bcb62
```

## Private diagnostic on shipped Ohm −18

Changing a diagnostic in the body of `uv-normalize`’s `InvalidNameError::fmt` changed the message printed by a clean caller. The crate’s metadata bytes and private hash changed. Its public hash stayed fixed. The first ordinary workspace `cargo check --locked --offline -j4` took 0.993 s. In an independently restored copy, a process trace recorded one rustc invocation, for `uv_normalize`, despite 35 Cargo progress messages. Both workspaces recorded a changed invocation stamp for that crate alone. Extract the [raw commands, metadata, traces and independent verifier](uv-normalize-private-check.zip) and run `python3 -ISB verify.py`.

## Combined compiler changes after the storage stop

The first run built and verified all 17 programs on bare Ohm −20. It stopped before compiling with the candidate because the memory-backed filesystem had insufficient space under the registered reserve. It contributed zero edited pairs and retains p = 1.

The next comparison reuses its verified, unedited control checkpoint. It will warm the candidate independently, then run twelve new pairs in a separately balanced order. The fourteen-comparison correction includes the stopped run. [Workload and decision rules](full-stack-after-uvx-protocol.md) · [Preregistered inputs and order](full-stack-after-uvx-protocol.json)

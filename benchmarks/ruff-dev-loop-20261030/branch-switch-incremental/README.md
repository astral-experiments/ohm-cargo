# Building after switching back to a Ruff branch

Ruff #28335 changed the size of an AST expression from 64 to 56 bytes. It touched the parser, AST, formatter and several downstream crates. The build loop switches between the real parent and feature branches in one Git checkout and builds the parser after each switch. Each compiler gets a new target directory and a separate empty Cargo build directory at the same absolute paths. The primary elapsed and instruction cohorts put the checkout, target and Cargo build directory on a private Linux tmpfs. [Historical Ruff change](https://github.com/astral-sh/ruff/pull/28335)

The comparison uses optimized x86-64 Linux stage 1 compilers built from the proposed Ohm distribution’s Rust revision and the branch-aware compiler. Cargo, the standard library, the rustc executable and the bundled Wild binary are shared byte for byte. The compiler driver is the single changed SDK file. Both compilers use the same bootstrap metadata stamp. The tracked source and physical tool hashes identify the builds. The Linux distribution applies PGO and BOLT separately. [Compiler build and configuration](compiler-build)

## Whole-command results

Each row is a complete ordinary Cargo invocation on a return to a previously built branch. Every workflow has 12 new installation pairs with six in each order. The elapsed interval starts with Cargo and ends when it exits. Git time, child CPU, independently compiled consumers, test execution and instrumentation are recorded separately. Both branches and all pairs are included.

| Workflow | Return | Parent median | Candidate median | Median paired speedup | Simultaneous 95% interval |
| --- | --- | ---: | ---: | ---: | ---: |
| `cargo build` | A | 8.960 s | 2.648 s | 3.39× | 3.23–3.49× |
| `cargo build` | B | 9.029 s | 2.710 s | 3.33× | 3.18–3.44× |
| `cargo test --no-run` | A | 11.643 s | 3.498 s | 3.32× | 3.20–3.56× |
| `cargo test --no-run` | B | 11.653 s | 3.427 s | 3.35× | 3.23–3.52× |
| `cargo check` | A | 7.146 s | 2.090 s | 3.44× | 3.30–3.64× |
| `cargo check` | B | 7.175 s | 2.093 s | 3.42× | 3.33–3.51× |

The intervals use order statistics on the within-pair ratios, with Bonferroni coverage for the two preselected return directions in each workflow. The no-effect test enumerates all 924 allowed balanced orders on the log ratios. The projection includes the sign test against 2× and the timings with Git added. Timing data from traced commands and the two-pair exploratory screens are excluded.

| Control | Empty A, parent / candidate | First B, parent / candidate | Unchanged B, parent / candidate | Extra retained on return A / B |
| --- | ---: | ---: | ---: | ---: |
| `cargo build` | 36.195 / 36.025 s | 8.941 / 8.826 s | 0.187 / 0.210 s | 92 / 124 MiB |
| `cargo test --no-run` | 67.792 / 67.615 s | 11.534 / 11.412 s | 0.212 / 0.211 s | 101 / 137 MiB |
| `cargo check` | 27.191 / 27.409 s | 7.138 / 7.007 s | 0.175 / 0.173 s | 58 / 70 MiB |

Storage counts allocated filesystem blocks for the two crates’ finalized incremental sessions, deduplicated by inode. Other target and build-directory files are outside that total. The compiler can retain one previous checkout alongside the latest session. Our serial builds on a single branch kept one session. An active lock or tied creation timestamps can preserve extra directories during collection.

## Compiler instructions and native work

Both complete Rust compiler processes are counted with Callgrind after the kernel selects the genuine compiler launched by Cargo. Cargo, rustup and the downstream validation programs run outside the counter. The counter preserves the compiler argument vector, environment, working directory and jobserver descriptors. Its final instruction count must agree with the sum of all self costs and with the independent Valgrind log.

One completed admission per compiler and return direction consumed 62.17B → 6.88B instructions on A and 62.44B → 7.00B on B. Both admissions recovered exactly 300,000 additional guest instructions on each measured coordinate of the small calibration program. These observations identify the reduced compiler work. The separate eight-pair instruction cohort is registered in this directory.

In the native build controls the two full rustcs created 89 distinct codegen objects on the parent and zero on the candidate in each direction. The test build created 90 and one, respectively, and ran the same single stock Wild link. Kernel traces count successful create-and-write opens and genuine compiler or linker executions. Each build consumer parsed valid Python, rejected invalid syntax, printed the expected version-specific AST size, and matched an independent empty-build executable exactly. Both test executables matched their empty references byte for byte and listed the same 245 tests. Three specified parser and lexer tests ran after each measured command. The metadata check compiled two downstream size assertions, accepting the correct size and requiring E0308 for the opposite size. Raw metadata can vary across independent builds even with the parent compiler.

## Correctness

With Ohm defaults disabled, an earlier prototype reused a stale assembler byte and accepted missing or malformed assembler input. The fixed compiler prefers an older checkout only when rustc rechecks external native inputs. The checked-in rustc regression passes on the parent and fixed compiler and fails on the rejected prototype. Both the fixed and rejected projections contain the original 120 Cargo build verdicts, native read records, complete executable digests, a ten-command standalone run, and an executable reproducer. The two modes cover nested assembler file reads and the default-mode controls cover tracked Rust byte inclusion and a static archive declared by a build script.

Two concurrent compiler processes also exercised the same incremental crate directory. A successful participant retained its working session and lock when the peer failed with E0308 or ran garbage collection past the ten-second age threshold. Three independent clean executables matched the overlapping run results byte for byte. A deliberately held shared lock temporarily preserved a third finalized checkout. The next serial collection returned to two after the lock was released. [Concurrent-session replay](concurrent-sessions)

## Reproduce locally

Use a Linux x86-64 host with Git, rustup shims, Python 3.11 or newer, and two complete Ohm SDKs from the parent and candidate revisions recorded in `sources.json`. Both SDKs need the same Cargo, rustc launcher and standard library. The replay copies the parent SDK to a private directory and swaps its compiler driver for each arm. It creates a real Ruff checkout, verifies its two commits, starts each arm with empty Cargo outputs, and validates every produced binary or metadata consumer. A Rust type error and the following recovery run provide negative controls. Test execution is outside Cargo’s measured interval.

```sh
python3 -IB verify.py
run_dir=$(mktemp -d)
python3 -IB replay.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --workflow build --pairs 12 --out "$run_dir/replay-build"
python3 -IB replay.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --workflow test-no-run --pairs 12 --out "$run_dir/replay-test"
python3 -IB replay.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --workflow check --pairs 12 --out "$run_dir/replay-check"
```

Each output path must be new. Supply `--offline` to use an existing populated Cargo registry cache and `--pack <ruff.pack>` to use a local copy of both Git trees. Each arm records Cargo’s raw JSON, process timings and verdicts under the output directory. The cold references are retained separately. The compressed measurement files carry the paired observations plus SHA-256 commitments to the original streams. The complete kernel traces and Callgrind outputs were independently reopened to produce these projections.

## A branch that advances while checked out elsewhere

The candidate selected the earlier branch session even after that branch acquired a new parser implementation. Reverting Ruff’s real unary-pattern validation made the unchanged upstream regression test fail. Restoring the implementation made it pass again. The parser compiled and the integration executable linked once on each change. Both full test executables matched their respective empty builds byte for byte. [Changed-branch workload and replay](moved-branch)

## Formatter test build

Returning to either branch also rebuilt the formatter test binary. In a separate two-pair screen, the ordinary four-compiler command fell from 22.20–23.20 s to 5.33–5.52 s. Each direction created one codegen object instead of 310 and ran one stock Wild link. Both executables matched their respective empty builds. This screen is separate from the 12-pair parser results above. [Formatter screen, workload and replay](formatter-screen)

To repeat the complete compiler instruction comparison, install a C compiler and Valgrind with its Callgrind tool on x86-64 Linux. The host must allow a process to trace its own children. Each arm preserves its complete per-process profiles, captured argument vectors, jobserver descriptors and native outputs. The summary reports summed rustc instructions.

```sh
python3 -IB replay.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --workflow build --compiler-instructions --pairs 8 --out "$run_dir/replay-instructions"
```

Two fresh pairs exercised that command. The parent executed 9.034 and 9.033 times as many instructions as the candidate on A, and 8.923 and 8.926 times as many on B. These functional replay pairs were kept separate from the registered eight-pair cohort.

## Formatter test build

Twelve independent pairs measured 22.14 → 5.29 s on return to the parent branch and 22.31 → 5.32 s on return to the feature branch. Paired speedups were 4.17× (simultaneous interval 3.97–4.42×) and 4.18× (4.07–4.30×). All pairs exceeded 2× in both directions. Each observed return still ran four rustcs and one real Wild link. It created one codegen object instead of 310. The final incremental files grew from 300 to 545 MiB. Both complete test executables matched their clean builds. [Formatter measurements, storage and replay](formatter-confirmation)

## Complete Cargo build directory sizes

In two independent ext4 pairs, the complete target and build directories grew from 288 to 380 MiB on return to the parent branch (+32%) and from 258 to 382 MiB on return to the feature branch (+48%). Both compilers used 257 MiB for the first build. Most bytes exclusive to the older branch were in the dependency graph and query cache. [Breakdown, physical-size counter and all 24 visits](storage)

## Block-backed build confirmation

Twelve new pairs repeated the whole build command with both the checkout and all Cargo outputs on ext4. The OS page cache was active throughout. Each direction cleared 2× in all 12 pairs. [Block device, records and offline verification](block-device)

| Return | Parent median | Candidate median | Median paired speedup | 96.14% interval for that direction | Median paired CPU ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 8.859 s | 2.695 s | 3.25× | 3.13–3.39× | 8.19× |
| B | 8.802 s | 2.756 s | 3.20× | 3.04–3.31× | 8.06× |

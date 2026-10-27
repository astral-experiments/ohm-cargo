# Ruff native rebuilds after the mixed-literal parser edit

Reversing Ruff’s change to the error for a t-string adjacent to a byte literal recompiled the parser and changed the diagnostic emitted by the `ruff` executable. The corrected Ohm compiler saved 32 whole rustc invocations on a workspace build and 87 when building the workspace tests. The native linker still ran 8 and 67 times respectively. [Ruff change](https://github.com/astral-sh/ruff/commit/3ea20f6161cbf59cb56595dfb634ec24bfa82f0b) · [Compiler PR](https://github.com/astral-sh/ohm-rust/pull/233)

| Command after the edit | Parent median | Corrected median | Full rustcs | Link-only rustcs | Paired elapsed reduction, bootstrap 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo build` | 19.21 s | 5.60 s | 35 → 3 | 0 → 6 | 70.85% (69.77–71.95%) |
| `cargo test --no-run` | 25.58 s | 8.24 s | 93 → 6 | 0 → 62 | 69.66% (68.00–71.34%) |

The candidate won all 12 randomized pairs for each command. The two-sided randomization test considered all 924 balanced orderings per endpoint. Both endpoints have Holm-adjusted p = 0.004329. Each pair measured a new Cargo process after applying the complete source edit. Each arm had its own build and target directories bound at the same absolute paths. Both used the same Cargo, rustc frontend and linker. The timed commands used eight Cargo jobs on CPUs 0–23 and ran without tracing. [Registered plan](https://github.com/astral-sh/ohm-cargo/tree/2896af5e8e75fd2108ff8b42f2675691761a8729/benchmarks/ruff-dev-loop-20261027/corrected-compiler-plan) · [Compiler binaries, PGO and BOLT inputs](https://github.com/astral-sh/ohm-cargo/tree/12619936bebbdc17fc1ca716cea7ea6545a01b1c/benchmarks/ruff-dev-loop-20261027/corrected-compiler-subject)

The first and last independent `execve` traces for each arm agreed on every full and link-only crate. All 501 build units or 619 test-build units were fresh on every immediate repetition, including after restoring the original source. The `ruff` executable reported the expected diagnostic in each state. The complete target graphs, the 15 or 110 workspace ELF output paths, and the restored Git index passed the independent audit. The experiment invoked no test binaries.

The parent source is `8ce2f21e25c06e7f884ca7b5c4e7898180791ae4`. Timing began at `66815c41574c8c597fa06af78a38c4c40ca30a84`. The later PR head `378b7a8202a270aac0a47610e99527125ec432ca` updates one regression test and retains precisely the same compiler Git tree `9e52c043880793c40fedf3eb137a231479d9adba`. [Source and compiler verification](https://github.com/astral-sh/ohm-cargo/blob/e6829719f7fe87ff1fe6ff5dadc20e22592ead6e/benchmarks/ruff-dev-loop-20261027/corrected-compiler-columns/pr-head.json)

## Reproduce one edit

Use a disposable clean worktree of Ruff at `93526150df078af7dd8fc4226cdcc469539d2001` and a matching `ohm` toolchain installed for each compiler. Supply a different pair of target and build directories for the other compiler. Make the pinned dependencies available before the offline commands.

```sh
python3 rerun-edit.py "$ruff_worktree" build --target "$ruff_target" --shared-build "$ohm_build_dir"
python3 rerun-edit.py "$ruff_worktree" test --target "$ruff_target" --shared-build "$ohm_build_dir"
```

The script checks the pin, complete patch digest, original and edited diagnostic, freshness, and restoration of tracked bytes, modes, modification times and index. The archived protocol additionally controls CPU affinity and arm order. [Protocol and measured worker](https://github.com/astral-sh/ohm-cargo/tree/9690aa73075839d49480fae773cc3b85d147d9a4/benchmarks/ruff-dev-loop-20261027/corrected-compiler-plan)

## Recompute the results

Use Python 3.11 or later from this directory. The `*-receipts.tar.gz` archives contain every timed observation, both traced repetitions, and the following freshness checks in each arm. The `*-execs.tar.gz` archives contain the complete Cargo artifact JSON and the original successful rustc and Wild `execve` lines from the two independent traces. `qualification-raw.json` records the full unfiltered trace archive digests and the verified reductions.

```sh
tar -xzf build-receipts.tar.gz
tar -xzf test-receipts.tar.gz
run=results-revision-native-66815c41574c
python3 analyze-native.py "$run-build" "$run-test"
python3 audit-revision.py \
    051b9d3f5861f984faa0f8c1d2ab9b5c28e483a05c728051de837291c83fd518 \
    3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2 \
    "$run-build" "$run-test"
```

## Independent warm and clean builds

For each compiler, all 15 workspace build products matched a clean rebuild byte for byte. In each test build, 109 of 110 products matched byte for byte. The remaining test executable differed in its GNU build ID and in the entry-size field of its `.rodata` section header. The section bytes, including machine code and read-only data, matched in all 110 products. The four Ruff CLI probes and the compiler diagnostics agreed.

Between the two independent clean compilers, 11 of 15 build outputs and 105 of 110 test outputs matched byte for byte. Some debug information and build IDs changed. The proc macro also has the versioned Rust metadata section. Its only changed dynamic or static symbol was the size of that metadata, from 17,592 to 17,609 bytes. Every other allocated section's contents, apart from the GNU build ID, matched.

Extract `warm-cold-receipts.tar.gz` into a directory and run `python3 analyze-reference.py DIR` and `python3 verify-reference-sections.py DIR`. The recorded reports are `warm-cold.json`, `elf-sections.json` and `macro-symbols.json`.

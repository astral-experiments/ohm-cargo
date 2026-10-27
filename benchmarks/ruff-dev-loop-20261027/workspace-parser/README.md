# Ruff workspace parser edit

Changing which diagnostic Ruff emits for adjacent t-string and bytes literals invalidated 35 native Rust compiles on the parent during `cargo build` and 93 during `cargo test --no-run`. The original #233 head ran 3 and 6 full compiles respectively. It still ran all 8 build links and all 67 test-build links. The compiler draft was subsequently blocked on a source-file fingerprint regression. These measurements identify that exact head. [Compiler draft and current status](https://github.com/astral-sh/ohm-rust/pull/233)

| Endpoint | Parent median | Original #233 head | Full rustcs | Link-only rustcs | Paired elapsed reduction with 95% interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo build` | 18.67 s | 5.45 s | 35 → 3 | 0 → 6 | 71.6% (70.3–72.9%) |
| `cargo test --no-run` | 25.27 s | 7.84 s | 93 → 6 | 0 → 62 | 70.6% (68.7–72.5%) |

Each endpoint had 12 balanced, randomized pairs on a dedicated Linux x86-64 machine with eight Cargo jobs on 24 pinned cores. Each arm had its own warm incremental target at the same absolute path. The timed command had no instrumentation. Independent traces before and after the timing series counted rustc and Wild executions. Each edited command was followed by a fully fresh build of all 501 or 619 Cargo units. Both exact randomization tests give a two-sided Holm-adjusted p-value of 0.00433. See `statistics.json`, the raw `*-pairs.csv`, the `*-qualification.json` traces, and the compressed per-run receipts in this directory.

Ruff was pinned to `93526150df078af7dd8fc4226cdcc469539d2001`. The workload reverses the entire upstream commit, including parser fixtures and snapshots. The original program reports “Cannot mix t-string literals with string or bytes literals” for `t'first' b'second'`. The edited program reports “Bytes literal cannot be mixed with non-bytes literals”. [Upstream Ruff edit](https://github.com/astral-sh/ruff/commit/3ea20f6161cbf59cb56595dfb634ec24bfa82f0b)

## Reproduce one edit

The replay needs a dedicated, clean Ruff worktree, a working matching Ohm toolchain under the name `ohm`, Python 3.11 or later, 64-bit Linux, and the Rust dependencies cached for the pinned Ruff revision. From an existing Ruff Cargo workspace, supply absolute paths for your own worktree, target, shared build directory, and this benchmark directory.

```sh
pin=93526150df078af7dd8fc4226cdcc469539d2001
cargo +ohm worktree add --target-dir "$ruff_target" -b ohm-parser-replay "$ruff_worktree" "$pin"
(cd "$ruff_worktree" && cargo +ohm fetch --locked)
python3 "$benchmark_dir/rerun-edit.py" "$ruff_worktree" build \
    --target "$ruff_target" --shared-build "$ohm_shared"
python3 "$benchmark_dir/rerun-edit.py" "$ruff_worktree" test \
    --target "$ruff_target" --shared-build "$ohm_shared"
```

The script warms the original graph, checks its Ruff diagnostic, applies the source edit, times one ordinary Cargo invocation, checks the graph is fully fresh on immediate repetition, and verifies that the changed binary reports the expected diagnostic. It restores tracked bytes, file modes, modification times, and verifies that the Git index is unchanged. It then rebuilds and checks the original behavior. The `test` endpoint only compiles test programs. Dependency acquisition happens before timing.

To compare toolchains, run the replay under each separately installed `RUSTUP_HOME`, with a distinct stable `CARGO_TARGET_DIR` for each worktree and build state for that compiler. Repeating one smoke run gives a process and behavior check. The registered comparison additionally balanced arm ordering and used identical absolute target and source paths. Its exact compiler inputs, schedules, machine affinity and script are in `workspace-plan.json`, `build-plan.json`, `test-plan.json` and `paired-native.py`.

The measured parent is `8ce2f21e25c06e7f884ca7b5c4e7898180791ae4`. The originally measured candidate is `8d8897ff9a15b50de615420827da6c0752dd9121`. The identical Cargo binary SHA-256 in both arms is `13396fe1c6886f41155ac24f507210c7a5f655e5b3279a28f45bf3a5e6bcaf08`. `workspace-plan.json` also pins the native stage-2 PGO/BOLT driver binaries. [Measured compiler change](https://github.com/astral-sh/ohm-rust/commit/8d8897ff9a15b50de615420827da6c0752dd9121)

## Independent builds and executable behavior

For the original measured head, both arms repeated the complete build and test build on the edited source from an empty target and an empty build directory. The cold-versus-cold comparison found identical machine code and allocated data in all 15 build outputs and all 110 test-build outputs, apart from build-ID notes. Whole-file SHA-256 matched for 11 of 15 build outputs and 105 of 110 test-build outputs. The other cold files differed in non-allocated DWARF, embedded compiler metadata, or the build ID. Running Ruff on four inputs produced identical exit codes and complete diagnostics on every edited build.

Within each compiler, all 15 warm build outputs matched their cold counterparts byte for byte. For the test-build outputs the count was 109 of 110 on each compiler. The parent's wasm API test and the candidate's semantic test showed a warm-versus-cold `.rodata` difference. Eighty-four of 102 executable paths use a compiler-specific Cargo directory component. Their complete target identities, basenames, and all 110 comparable ELF keys agree. The raw paths and all section-level differences are preserved in `original-cold-comparison.json` and `original-cold-receipts.tar.gz`. The separate `original-portable-smoke.json` run exercised the replay script on the matched parent and confirmed both the restored diagnostic and fully fresh build.

# Omit embedded metadata from internal workspace libraries

## Assessment

The prototype saves disk for a stable set of selected packages, but **should
not be enabled broadly in its current form**. The Ruff parser workflow used
2.44–2.66% less physical space. Selecting an internal dependency as an additional
root, then returning to the original roots, introduced two recompilations and
left more physical data than the baseline. Avoiding those export transitions
would be necessary before this meets a general no-performance-regression goal.

## Implementation

Set `CARGO_EXPERIMENTAL_WORKSPACE_NO_EMBED_METADATA=1` to extend Ohm's existing
metadata policy to workspace `lib`/`rlib` dependencies. Those units retain the
separately emitted `.rmeta` file and omit the duplicate metadata in the `.rlib`.
Selected root libraries still embed metadata so standalone consumers can use
their exported archives. Other local path packages and mixed/dynamic crate
types retain their existing behavior. The existing global opt-out remains
effective.

The existing fingerprint hashes the actual per-unit policy. Switching the
flag or making an internal library a root therefore rebuilds it with the
required archive format. This is correct, but root-role changes also invalidate
downstream units. The prototype does not attempt to synthesize an exported
archive from the separately stored metadata.

## Correctness

All six `no_embed_metadata` tests pass against packaged Ohm 1.98.0-9, including
flag toggles, no-op freshness, exported root libraries, root promotion, dynamic
libraries, and standalone `rustc` consumers. The expanded test explicitly
checks that the promoted library contains usable metadata without a companion
`.rmeta` file or dependency search path. Formatting and `git diff --check`
pass. See [validation provenance](results/validation.json) and compressed logs.

## Real-workload APFS screen

The same optimized candidate Cargo binary ran off/on/on/off on four fresh,
dedicated APFS sparse volumes, using the packaged Ohm 1.98.0-9 compiler,
four jobs, opt-level 1, line-table debug information, and explicit registry/local
macro and native-tool trust. Downloads were prefetched; timed builds were offline.

Ruff starts at `1edf9fe2cab23e34c383419b8c7830324c428a58`. The workflow builds
`ruff_python_parser`, repeats the build, runs tests twice, checks, and runs
Clippy with all targets. It then applies the real parser fix
`0ecff877901a0377ad966ffab528488ce872b50e` and reruns tests. Test invocations
pass 812 tests before the edit and 813 after it in every arm.

| Stage | Pair 1 off / on | Pair 2 off / on | Physical reduction |
| --- | ---: | ---: | ---: |
| Initial build | 251.83 / 244.39 MiB | 252.14 / 244.32 MiB | 2.95–3.10% |
| Build/test/check/Clippy | 708.27 / 690.97 MiB | 709.49 / 690.62 MiB | 2.44–2.66% |
| After real source edit | 718.38 / 700.70 MiB | 718.50 / 700.14 MiB | 2.46–2.56% |
| Final, including separate AST build | 855.45 / 836.49 MiB | 854.96 / 836.15 MiB | 2.20–2.22% |

The final two commands select `ruff_python_ast` alone with `get-size,serde`,
then return to parser tests. Selecting AST alone changes dependency feature
unification in both arms, so this is an additional workflow check, **not an
isolated measurement of root promotion**. The separate experiment below keeps
the parser graph selected throughout.

Physical figures are dedicated-volume allocation growth after the source
checkout, measured with `ATTR_VOL_SPACEUSED` after filesystem flush and three
identical samples. They include private and shared build/incremental state;
toolchains and the download cache are external. Per-file inode totals are
labeled clone-unaware and are never used as physical allocation measurements.

The complete main workflow took 43.70 / 42.03 seconds in pair 1 and
42.15 / 41.29 seconds in pair 2. Unrelated development workloads were active,
so the favorable 2.03–3.81% wall-time changes are observational, not an isolated
no-regression result. No-op build commands remained fresh.

## Root-role transition with the same feature graph

Each arm then uses a fresh private target and shared build directory on its
own volume, at the edited Ruff revision. It runs:

```sh
cargo build -p ruff_python_parser
cargo build -p ruff_python_parser -p ruff_python_ast
cargo build -p ruff_python_parser
cargo build -p ruff_python_parser
```

The baseline stays fresh for both root changes. The prototype recompiles AST
and the parser when AST becomes a root, then recompiles both again when AST
becomes internal. The final no-op is fresh in all arms. These compile events
establish a performance regression for changing roots independently of timing
noise. The retained exported archive and incremental history also erase the
initial disk saving in this sequence.

| Pair | Two root changes, off / on | Final physical size, off / on | Physical growth |
| --- | ---: | ---: | ---: |
| 1 | 0.192 / 4.244 s | 251.40 / 260.80 MiB | +3.74% |
| 2 | 0.223 / 4.364 s | 251.77 / 260.70 MiB | +3.55% |

These allocations subtract the volume state immediately before the fresh
target experiment, so the earlier main workflow is excluded. They include
the remaining root export after switching back. Timings have the same external
contention limitation as the main screen.

## Reproduction and evidence

[Raw receipts and derived results](results/apfs) record each command, binary
and compiler hashes, environment, CPU/wall usage, allocation samples, source
revisions, and detach results. Each arm includes its main `receipt.json`,
`role-transition.json`, and compressed command logs. Sparse images remain
available locally and all four volumes were detached normally.

```sh
python3 benches/workspace-metadata/run_apfs.py \
  --cargo /path/to/optimized/cargo --ruff /path/to/ruff \
  --root /private/tmp/codex-cargo-targets/ruff/isolated/workspace-metadata \
  --evidence /path/to/results --jobs 4
python3 benches/workspace-metadata/role_transition.py --results /path/to/results
python3 benches/workspace-metadata/summarize.py /path/to/results
```

The runners refuse to replace existing arms or transition targets. This is a
real parser/AST workload screen, not a full Ruff/uv workspace or Linux study.
The measured code commit and baseline are pinned in the validation receipt;
the subsequent evidence commit changes no production or test code.

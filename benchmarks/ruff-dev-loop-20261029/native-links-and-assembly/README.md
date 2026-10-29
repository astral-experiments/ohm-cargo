# Ruff assembly reuse and native link checks

On unchanged `ruff_python_ast` builds, the parent compiled `compact_str`, `zmij`, and the root crate. The candidate ran zero compilers. The libtest command still compiled and linked its harness on every unchanged visit. Rechecking the collected `execve` arguments found zero link-only rustc invocations in both arms of these package runs. [Cargo change](https://github.com/astral-sh/ohm-cargo/pull/291) · [Rust change](https://github.com/astral-sh/ohm-rust/pull/266)

| Command | Unchanged visits per arm | Full rustc, parent → candidate | Stock Wild, parent → candidate |
| --- | ---: | ---: | ---: |
| `cargo build -p ruff_python_ast` | 48 | 144 → 0 | 0 → 0 |
| `cargo test -p ruff_python_ast --lib --no-run` | 48 | 144 → 48 | 48 → 48 |

For each command we ran eight independent paired installations, four parent-first and four candidate-first. Each installation used separate, initially empty target and shared build directories. It visited the old source, the edited source, and the restored source, with two unchanged commands in each state. The experimental unit was the installation pair. All eight differences agreed for each command. The observed allocation and its reverse were the only two of 70 allocations as extreme as the observed full-compiler difference.

The build edit changed the Python-version reader from `3.14 3.14 3.10` to `3.15 3.15 3.11`. The test edit corrected four failing cases in the same 54-test inventory. Edited products matched the independently empty build in each installation, and an invalid Rust edit produced E0425. Tests ran separately from the commands counted here. A focused `ty_server` run and full-workspace measurements have different graphs. [Ruff revision](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Build edit](https://github.com/astral-sh/ruff/commit/ef23c9c39eb3029bab0139c3ea7ae6d95c4131e0) · [Test edit](https://github.com/astral-sh/ruff/commit/dc2f0a86fd9c4f256a6809370e29bfe2631ebd8d)

`runs.json.gz` contains all paired compiler and linker rosters, the schedule, source and binary identities, per-installation verdicts, and SHA-256 commitments to the original compressed native traces and Cargo output. `link-only.json` counts successful compiler invocations that received `-Zlink-only`. The frozen scorer’s complete result reconstructs to SHA-256 `841294469dcec3eff10199d2d3d40cf9d11fae96ea543d74c1a3b929d25b9bfe`. Verify the published data with Python 3.11 or later.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py
```

To rerun the compile and link census on Linux x86-64, prepare two rustup-linked SDKs with the same `ad005f99d0b51fd62b5c237bc13b31b371a1686e` compiler and bundled Wild. Build both Cargo binaries with the `ohm-defaults` feature. Use Cargo `7277e6cdaba44c43294a07c0661fc8e69fd8e3e7` for `ohm-before` and `84af87848a5a952ba61ae6a2cc5b22da24130200` for `ohm-after`. The measured SDKs were source builds without distribution PGO or BOLT. Install `strace` and populate the offline registry cache for the pinned Ruff workspace.

Run this in the evidence directory, with `RUFF` pointing to a clean checkout at the recorded revision. Each `--out` must be new and outside that checkout. The replay creates a disposable Cargo worktree and retains the trace for each command.

```sh
for mode in build test; do
  for sdk in ohm-before ohm-after; do
    python3 -IB replay.py --ruff "$RUFF" --mode "$mode" \
      --toolchain "$sdk" --out "$PWD/replay-$mode-$sdk"
  done
done
```

An independent Linux host ran the published script on the patched toolchain from two empty installations. All 18 Cargo commands succeeded. Six unchanged builds ran zero full compilers and zero Wild links. Six unchanged test builds each ran one full compiler and one Wild link. Editing and restoring the source recompiled the root each time. The restored libtest listed 54 tests with the four expected historical failures. The individual command counts and binary identities are in [independent-replay.json](./independent-replay.json).

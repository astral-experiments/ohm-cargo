# Full rustc launches for a historical Ruff edit with libm

We compared matching W and F Rust builds on the genuine Ruff CRLF edit with its wasm API consumer and source-file library. Eight adjacent pairs used sixteen independently empty target and shared directories. Each install ran the same seven ordinary Cargo commands and checked actual linux kernel exec events. The registered decision was made on the physical full rustc count for the edit.

The decision passed. The median change was -1 full rustc process per edit and the sum of the eight F minus W differences was -8. The two-sided randomization test gave 2/70 (0.02857). Four of the eight pairs were randomly assigned to run W first, with all 70 possible balanced orders equally likely. Keeping the chronological observations in each pair fixed, the test counted assignments whose absolute sum was at least as large as the observed sum.

| Pair | Order | W full rustc | F full rustc | W / F link-only | W / F stock Wild |
|---:|---|---:|---:|---:|---:|
| 1 | WF | 32 | 31 | 0 / 0 | 5 / 5 |
| 2 | WF | 32 | 31 | 0 / 0 | 5 / 5 |
| 3 | FW | 32 | 31 | 0 / 0 | 5 / 5 |
| 4 | WF | 32 | 31 | 0 / 0 | 5 / 5 |
| 5 | FW | 32 | 31 | 0 / 0 | 5 / 5 |
| 6 | FW | 32 | 31 | 0 / 0 | 5 / 5 |
| 7 | FW | 32 | 31 | 0 / 0 | 5 / 5 |
| 8 | WF | 32 | 31 | 0 / 0 | 5 / 5 |

The complete native job rosters, original per-invocation hashes and consumer outputs are in `native.json.gz`. The table below retains every registered phase, including invalid input. Ranges denote actual variation across the eight fresh installs per arm.

| Phase | W full rustc | F full rustc | W Wild | F Wild |
|---|---:|---:|---:|---:|
| original | 337 | 337 | 63 | 63 |
| repeat-original | 7 | 6 | 4 | 4 |
| edited | 32 | 31 | 5 | 5 |
| repeat-edited-1 | 7 | 6 | 4 | 4 |
| repeat-edited-2 | 7 | 6 | 4 | 4 |
| invalid | 4 | 4 | 1 | 1 |
| restored | 32 | 31 | 5 | 5 |

## Behavior and native fallbacks

The same source states yielded the same full test executable, API executable and independently linked reader as the earlier independently empty edited builds. The existing CRLF test passed on the corrected implementation and failed on the historical one. The external reader returned `1 1 1 0` and `1 2 1 1` respectively after opening the real get-size/serde library selected by the Ruff wasm API. Both compilers rejected the deliberately missing function with E0425 at the same file and source span, and recovered the original passing behavior.

After the first W and F ordinary histories completed, we put a generated library in the existing higher-priority psm path on that arm’s private workspace. The actual executable and shared-object link each opened it with stock Wild. The API process exited 83 under the valid replacement and so did a separate process that loaded the actual shared library. When forced to link, both products agreed with the ordinary valid case. Malformed data failed the normal and forced builds with Cargo 101. Removing the new file restored the original API program and shared library, both tested to exit zero, and the external reader returned the original answer. Both source arms retained the authenticated system GCC script. Separate binary and source controls exercise the assembler, archive, dynamic search and arithmetic result.

The sixteen earlier screening visits are kept apart from the 112 ordinary calls in these pairs. This endpoint counts full compiler processes. Neither study measured elapsed time or instructions, and the result applies to the specified package selection and compiler builds. The actual source-built compilers shared 2,452 of 2,453 SDK entries, including rustc itself, all 53 standard-library members, LLVM, the same Cargo and stock Wild. [Ruff change](https://github.com/astral-sh/ruff/commit/88d851449d2345e11da991794f3e9bfbbd666719) · [Ruff base](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001) · [Rust W](https://github.com/astral-sh/ohm-rust/commit/ad005f99d0b51fd62b5c237bc13b31b371a1686e) · [Rust F](https://github.com/astral-sh/ohm-rust/commit/3fd8c55774bf1208ff9ebb8ec0eae727c1a2daf9) · [Cargo](https://github.com/astral-sh/ohm-cargo/commit/84af87848a5a952ba61ae6a2cc5b22da24130200)

The separate compiler qualification bound twelve earlier native, assembler, bundled-library and CRLF fixture results. The checked-in `ohm-checked-dep-info` run-make test executed 18 real compilations, `ohm-relink-assembler-inputs` executed seven, and the UTF-8 subspan regression executed three. The first fixture launcher failed its SDK lookup before any compiler ran. The subsequent source-bound run passed. [Compiler guard receipts](compiler-guards.json)

## Verify and rerun

```sh
python3 -IB verify-crlf.py --self-test
python3 -IB replay-crlf-complete.py --help
python3 -IB replay-crlf-complete.py \
  --ruff "$RUFF_GIT" --registry "$CARGO_HOME/registry" \
  --control-sdk "$OHM_PARENT_SDK" --candidate-sdk "$OHM_CANDIDATE_SDK" \
  --cargo "$OHM_COMMON_CARGO" --work "$SCRATCH/ruff-crlf-rerun" \
  --cpus 0,1,2,3 --pairs 8 --with-providers
```

Use an existing Linux x86-64 checkout of Ruff with the pinned commit, Python 3.11+, Git, rustup with proxies, strace, GCC, two complete same-layout Ohm SDKs, the common Cargo built with Ohm defaults, and an offline Cargo registry containing all 498 locked archives and its sparse index. Select four CPUs allowed on the host and an absent, trusted scratch path with at least 42 GiB free for one paired history or 112 GiB for eight with native providers. At the default limits the launcher also requires over 12 GiB available RAM. The source donor is checked before and after each visit. The rerun retains generated states, raw syscall streams, consumer results and a local receipt. It runs an independent edited empty target for each arm. The supplied alternate launcher was checked for argument parsing and syntax. The actual recorded experiment used the registered private mount launcher. The --with-providers option also runs the ordinary, forced, malformed and removal cases in the first completed private history on each arm. It preserves the two native outputs before each forced rerun and checks that the original system library script is unchanged. Omit this option for a source-and-count-only replication.

# Combined Cargo hotfixes on native Linux and macOS

The candidate at `b76dc8006155d48a8cd7d6c5543acb9c18e2ce4b`, tree `c8d0e89c4226add0ae40b6604025f5e7b04489f5`, passed all eight ordinary Cargo CI jobs. The two full jobs compared the checkout and tree with the expected hashes. The QA workflows retained the original package commands, matrix targets, pinned installers and test expectations. The full Linux job used a 48 GiB executable tmpfs for the target and both scratch paths. The macOS job observed APFS at the target and at the path reported by Rust 1.99’s `std::env::temp_dir()`. [Combined source](https://github.com/astral-experiments/ohm-cargo/commit/b76dc8006155d48a8cd7d6c5543acb9c18e2ce4b) · [Native Linux job](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784/job/124383016552) · [Native macOS job](https://github.com/astral-experiments/ohm-cargo/actions/runs/41150034552/job/124384130271)

| Standard `cargo +1.99.0 test -p cargo` | Linux | macOS |
| --- | ---: | ---: |
| Library | 413 | 404 |
| CLI | 5 | 5 |
| Integration | 4,405 | 4,386 |
| Doc tests | 3 | 3 |
| Total passed | 4,826 | 4,798 |
| Suite-declared ignores | 433 | 430 |
| Failed or filtered | 0 | 0 |
| Additional pinned Ohm cases | 15 | 8 |

Both native jobs passed the repaired-crate regression and both GC coordination tests. Linux also passed the shared and private mount-boundary tests and the pinned-parent replacement case. Both verified the two compiled profile test names under Ohm `-9`; the inherited `profiles::` selector still selected zero. The complete stable integration inventory matched the testsuite’s separate `--list` on each platform, including the two tests to which libtest appends `- should panic` in its verdict display. [Linux source and fixture receipt](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784) · [macOS source and fixture receipt](https://github.com/astral-experiments/ohm-cargo/actions/runs/41150034552)

Linux and macOS Clippy, Rustfmt, workspace, resolver and schema passed. Workspace reported 116 top-level passes and three ignores, plus seven deliberately filtered invocations of its child-process helper. Resolver passed 93 tests, and schema passed 17. [Workspace](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784/job/124383016445) · [Resolver](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784/job/124383016579) · [Schema](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784/job/124383016605)

Two earlier macOS workers stopped in the QA storage observer before invoking Cargo. The first assumed a shell `TMPDIR` was set. The second passed a non-seekable pipe to `plistlib.load`. The completed job queried the installed Rust standard library for the path and decoded the diskutil plist bytes using `plistlib.loads`. The receipt keeps both errors, job IDs and log hashes. [Unset TMPDIR](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149697784/job/124383016497) · [Non-seekable plist](https://github.com/astral-experiments/ohm-cargo/actions/runs/41149865493/job/124383570348)

## Verify or replay

The offline verification checks every archived test name and verdict, all pinned gate names, the mounted-path controls, and both full-job receipts.

```sh
python3 -IB qa/combined-cargo-native/verify.py
```

The QA ref contains the successful Linux and macOS steps together. Before publication, its macOS steps were compared with the completed native macOS job. Its Linux steps and all other jobs were compared with the first run. Dispatching the ref checks out the original product SHA on fresh workers.

```sh
repo=astral-experiments/ohm-cargo
branch=charlie/qa-combined-hotfixes-native-20261031
test "$(gh-auto api "repos/$repo/contents/.github/workflows/ci.yml?ref=$branch" --jq .sha)" = f045d5413d98e525491ce7f87971b2c9cd62ac9e &&
  gh-auto workflow run ci.yml --repo "$repo" --ref "$branch"
```

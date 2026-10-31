# Cargo #305 full Linux qualification

The complete Linux Cargo command passed on `7b29b877b14874055e794e22d19cae2f35cfcab1`, followed by 15 individually identified Ohm tests. Both the unit fixtures and Cargo's compiled integration scratch used a job-private 48 GiB executable tmpfs. The completed target used 16 GiB. The QA workflow checked out the product commit, kept its seven install and test steps, and added environment verification and a supplemental two-test gate. [Product PR](https://github.com/astral-experiments/ohm-cargo/pull/305) · [Final run](https://github.com/astral-experiments/ohm-cargo/actions/runs/41147382852/job/124375551129) · [Frozen workflow](https://github.com/astral-experiments/ohm-cargo/blob/aaa2e8d49f0973b06d630eb499ce55cef2220fd1/.github/workflows/ci.yml)

| Stable Cargo 1.99.0 suite | Passed | Ignored by suite |
| --- | ---: | ---: |
| Library | 410 | 0 |
| CLI | 5 | 0 |
| Bench fixtures | 0 | 9 |
| Integration | 4,405 | 423 |
| Doc tests | 3 | 1 |
| Total | 4,823 | 433 |

`cargo +1.99.0 test -p cargo` reported zero failures and zero filtered tests. Ohm `-16` then ran five shared-registry cases. Ohm `-9` ran six worktree cases, two linker and rustflags cases, and the two debuginfo cases. The inherited CI selector `profiles::ohm_default_debuginfo` matched zero tests. The supplemental gate executed both cases by their compiled `profile_settings::` names, required one pass per invocation, and archived each transcript. The Git copies omit the trailing blank line. The receipt includes the original stdout hashes. [Original selector](https://github.com/astral-experiments/ohm-cargo/blob/7b29b877b14874055e794e22d19cae2f35cfcab1/.github/workflows/ci.yml#L148) · [Actual fixture definitions](https://github.com/astral-experiments/ohm-cargo/blob/7b29b877b14874055e794e22d19cae2f35cfcab1/tests/testsuite/profile_settings.rs#L881-L925)

The earlier standard-hosted runs recorded Actions-worker ENOSPC. A large Namespace run with only the unit fixtures on native storage passed all 410 library tests, then saw 22 GC integration failures on overlay. Moving the complete Cargo target and both fixture paths to native storage passed all 4,405 integration tests on two fresh jobs. The receipt includes the earlier failures and the hash of each reopened ZIP. [First disk failure](https://github.com/astral-experiments/ohm-cargo/actions/runs/41144372208/job/124365881138) · [Second disk failure](https://github.com/astral-experiments/ohm-cargo/actions/runs/41144758002/job/124367166370) · [Mixed-filesystem run](https://github.com/astral-experiments/ohm-cargo/actions/runs/41146447980/job/124372563394) · [First full native pass](https://github.com/astral-experiments/ohm-cargo/actions/runs/41146980155/job/124374260868)

The workflow survey at 23:57 UTC on October 30, 2026 covered all 167 open Cargo PR heads. Among them 122 used the stale selector with `mod profile_settings` and 45 had no explicit selector for these tests. The current default, the 1.99 branch, and runner PR #296 did not define the two Ohm fixtures or the pinned integration step. The TSV records the source and Git blob IDs at each surveyed head. [Runner PR](https://github.com/astral-experiments/ohm-cargo/pull/296)

## Replay

From this QA checkout, inspect the archived test inventory and verify the file hashes.

```sh
python3 -IB qa/cargo-305-linux/verify.py
```

To rerun on a fresh worker, verify the workflow content, then dispatch the QA ref. Its checkout step pins the exact product source.

```sh
branch=charlie/qa-cargo-305-full-native-20261030
repo=astral-experiments/ohm-cargo
test "$(gh-auto api "repos/$repo/contents/.github/workflows/ci.yml?ref=$branch" --jq .sha)" = 4d8ea76fc1ed244b98524658c66226c690072184 &&
  gh-auto workflow run ci.yml --repo "$repo" --ref "$branch"
```

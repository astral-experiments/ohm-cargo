# Returning to a branch that advanced

While Ruff’s feature branch was checked out, its previously built parent advanced to a private commit that reverted the 20 lines of parser logic added in Ruff #28233. Both compilers rebuilt the integration test using the ordinary `cargo +ohm test -p ruff_python_parser --test fixtures --no-run` command. The user-visible result of the edit was that Ruff accepted `case -1**2`. Its original regression test detected the change. Fast-forwarding the same branch again to restore the rule made the test pass. The test fixture and the rest of the historical Ruff tree stayed identical. [Ruff parser change](https://github.com/astral-sh/ruff/pull/28233)

The kernel traces identify which saved dependency graph each rustc copied. The parent selected the most recent session from the feature branch. The candidate selected the previously built session for the returning branch on both advances. Both compilers rebuilt the parser and ran exactly one stock Wild link on each advance. The test executable and the standalone parser consumer matched their respective independently empty builds byte for byte. The command listed 557 Ruff integration cases, and the selected case ran separately from the build.

`source.json` identifies the real Ruff commits, the two derived private commits and their complete trees. The compressed projection records commands’ terminal verdicts, stream digests, session identifiers, both empty ELF digests, and per-process trace commitments. The independent reader reopened 1,132 kernel traces and executed both immutable consumer programs.

```sh
python3 -IB verify.py
python3 -IB probe.py --parent-sdk "$PARENT_SDK" --candidate-sdk "$CANDIDATE_SDK" \
  --pack "$RUFF_PACK" --out "$(mktemp -d)/branch-advance"
```

The original full replay requires the two exact Linux SDKs in the parent evidence directory, a prepopulated Cargo registry and the Git pack containing both historical Ruff trees. It operates on a new, private checkout and requires strace.

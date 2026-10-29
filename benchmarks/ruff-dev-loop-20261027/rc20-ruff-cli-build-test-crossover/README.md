# Ruff builds two observably different CLI binaries after an argument-file edit

The Ruff integration-test binary depends on a second build of the CLI. Its compiled-in rule set differs from the one installed by an ordinary build. On the same source, the ordinary CLI rejects `ruff rule RUF950` with exit 2. The integration-selected CLI documents the rule and exits 0. Reusing either complete executable for the other command would change an actual user-visible result.

The two commands were `cargo +ohm build -p ruff --bin ruff` and `cargo +ohm test -p ruff --test integration_test --no-run`, with locked offline inputs and Cargo JSON enabled. Both used the same canonical source, target and separate shared build directory. We selected Ruff 93526150df and reversed only the production hunk of its historical argument-file handling change. The integration tests and snapshots stayed at the pinned revision. [Ruff change 7d7237c6](https://github.com/astral-sh/ruff/commit/7d7237c6606fa621485cf3cb982f107ce0f48db3)

| Commands | Cargo artifacts per command | Full rustc runs | Stock native links |
| --- | ---: | ---: | ---: |
| First build after replacing the earlier Cargo, 1 command | 373, 372 fresh | 1 | 1 |
| First integration selection from that warm ordinary build, 1 command | 388, 364 fresh | 24 | 4 |
| Four source transitions, visited by both selectors, 8 commands | 373 or 388, only the CLI dirty | 1 each | 1 each |
| Unchanged selections, 12 commands | All 373 or 388 fresh | 0 | 0 |

Both selector orders occurred on both reversal and restoration. Each unchanged crossover restored the matching executable at the shared public pathname. The native counts come from successful kernel execs of real source-compiling rustc processes and the enrolled stock Wild. GCC and collect2 also ran once per native link. The test oracle's subprocesses were collected separately. The 22 Cargo commands produced 8,371 typed artifact observations. No elapsed times were collected as performance results.

| Public CLI | Original source SHA-256 prefix / bytes | Reversed source SHA-256 prefix / bytes | Missing response file, original → reversed |
| --- | --- | --- | --- |
| Ordinary | `8b1a5a8891f9` / 151,043,112 | `654c387f4603` / 151,042,424 | exit 2 → panic, exit 101 |
| Integration-selected | `cf926a8dde39` / 151,154,904 | `bef2a496a2f4` / 151,154,248 | exit 2 → panic, exit 101 |

Both CLI families processed a valid response file and formatted stdin as expected. Each of the eleven test selections produced the same integration harness and the same listing of 97 tests. We ran `missing_argfile_reports_error` and `check_input_from_argfile` against the installed CLI after every test selection. The first passed on the pinned source and failed on its reversal. The second passed in all eleven cases. Successful child execs and reopened executable hashes identify the actual CLI used by each test. The other 95 tests were inventoried.

### Why both builds matter

Cargo attaches an ordinary Build-mode binary dependency to an integration target and provides its path through `CARGO_BIN_EXE_ruff`. The Ruff binary itself reports an empty feature list in both graphs. Its normal linter dependency enables `clap,default`, while the integration selection additionally enables `test-rules`. Its dev dependency on `colored` also enables `no-color`. These are effective feature differences in Cargo's own artifact stream. Ruff's linter makes the RUF950 rule selector conditional on its test rules. [Cargo unit dependency](https://github.com/astral-sh/ohm-cargo/blob/2fe90823d8eadc95de56c2cde8d41e0082aac0eb/src/compiler/unit_dependencies.rs#L443) · [Cargo executable binding](https://github.com/astral-sh/ohm-cargo/blob/2fe90823d8eadc95de56c2cde8d41e0082aac0eb/src/compiler/artifact.rs#L20) · [Ruff package manifest](https://github.com/astral-sh/ruff/blob/93526150df078af7dd8fc4226cdcc469539d2001/crates/ruff/Cargo.toml) · [Ruff lint codes](https://github.com/astral-sh/ruff/blob/93526150df078af7dd8fc4226cdcc469539d2001/crates/ruff_linter/src/codes.rs)

The terminal root compiler invocations carry distinct Rust metadata identities, `782083eccc4b187f` and `ef49c64f5fcc8e79`. Sixteen physical rlib/rmeta files named in those invocations cover two variants each of `colored`, `ruff_linter`, `ruff` and `ruff_workspace`; all sixteen have distinct whole-file SHA-256 values. At restored source, both CLI object sets contained 22 files totaling 294,952 bytes, with no whole-object SHA-256 in common. The two 127,635-byte link recipes differed too. These measurements do not quantify finer internal reuse by rustc.

### Scope and verification

The matched combined Cargo is 2fe90823d8, paired with the official Linux -19 compiler and original packaged Wild. The ordinary lower came from an earlier 8dc33c9cc Cargo study. We restored its authenticated source in a private copy-on-write view before the first command. The untouched lower source, executable, original receipt and candidate image passed byte and file-identity checks after the series. The initial Cargo change and first dev-graph population are separate rows above. No independent empty combined-target build was needed to falsify cross-selector reuse. The test-selected rule response differs even with identical source and entirely fresh artifacts.

The campaign already covered this edit for the ordinary build alone, and a different build-only study switched between the Ruff and ty CLIs. We surveyed 237 published PR heads and 293 named branches, then read the eleven nearby Cargo patches identified in `subjects.json`. The existing test-mode registry reuse and unused-input relink changes address different dependency relations. This experiment covers only the named workspace CLI and integration target.

Run `python3 -IB verify.py --self-test` in this directory. It validates all 22 commands, the 396 distinct public artifact records, 2,224 per-PID raw commitments, all four CLI identities, the listed and exercised tests, and both object sets. In a disposable Ruff checkout at the stated revision, the selector commands above can reproduce the feature distinction without changing source. Run `"$CARGO_TARGET_DIR/debug/ruff" rule RUF950` immediately after each selector, then switch back. To reproduce the edit, apply `ruff-argument-errors.patch` in that private checkout, run both selectors and their missing-argfile test, reverse the patch and repeat the selectors in the opposite order. Exact argv, dependency identities, output hashes and original raw stream digests are in `commands.json.gz`. Full unredacted local evidence was preserved separately.

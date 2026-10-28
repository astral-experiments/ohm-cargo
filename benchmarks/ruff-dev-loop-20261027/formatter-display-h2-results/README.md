# Ruff formatter diagnostic edit on Ohm -17

This is a native link-discovery run on x86-64 Linux. At Ruff `93526150df078af7dd8fc4226cdcc469539d2001`, one file from the 32-file historical commit `2b1d3c60faafcedc79423661884331eb8834fab7` changes two formatter diagnostics between `Ruff` and `Rome`. Each edit kept the source width. Each arm started from empty private target and build directories and used the published `ohm-1.99.0-17` SDK, four Cargo jobs, and the unmodified Ruff tree mounted read-only under the experimental source view. A separately compiled caller printed both expected diagnostics on every phase. [Historical Ruff commit](https://github.com/astral-sh/ruff/commit/2b1d3c60faafcedc79423661884331eb8834fab7)

| Command | Cargo units | Full rustc on edit | Link-only rustc on edit | Wild links on edit | Executables with changed bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cargo build -p ruff --bin ruff` | 373 | 1 | 1 | 1 | 1 |
| `cargo test --no-run -p ruff_python_formatter` | 218 | 1 | 4 | 4 | 3 |

The inverse edit gave the same counts. All units reported fresh on each subsequent unchanged command, with zero compiler or linker jobs. The full compile on each edit was `ruff_formatter`. The CLI formatted a sample and the formatter library test executable listed its tests identically throughout.

The binary test harness `ruff_python_formatter-81814697f8234e3f` kept the same SHA-256 `ce80372dd5924bba1bf4639ac1b8d8e92f809540d614ca98fb54fa20f56d783d` in both directions. Its actual Wild command contained 135 Rust archives, including the changed formatter archive. That makes it a candidate for further analysis. These runs contain no performance comparison or proposed link-skip rule.

The test arm's cold command had 219 successful full compiler executions and one failed `fixtures` execution with exactly the same argv as its later successful execution. The cold CLI arm also issued 61 system-linker configure probes, including eight failures. These are separate from the 67 successful CLI Wild links. The archive keeps all seven phases of both commands and the three earlier harness stops with their registration identities. [CLI registration](https://github.com/astral-sh/ohm-cargo/tree/dab9d2b21876fe4c8d8ac6a8482c85ad3559701c/benchmarks/ruff-dev-loop-20261027/formatter-display-h2-plan-v2) · [Test registration and full reproduction script](https://github.com/astral-sh/ohm-cargo/tree/bb3b2ca6854a09f5746900ed20e1aa94b2b1c5ba/benchmarks/ruff-dev-loop-20261027/formatter-display-h2-physical-attempts)

Run `python3 -B verify.py` to reconcile the successful Cargo exits, unit inventories, physical compiler and linker arguments, independent caller diagnostics, and all workspace product changes. `inventory.json.gz` binds each original record to its portable copy. Only the local registry cache directory name was replaced with its content-addressed alias. Full compiler and linker traces contain no environment values. The 14 commands were traced, so this packet reports work counts and artifact identity only.

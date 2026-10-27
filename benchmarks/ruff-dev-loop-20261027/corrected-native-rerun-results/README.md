# Ruff native edit replays with the corrected Cargo span reader

The public edit reproducer ran on the release builds of rustc #233 `27029b4b` and Cargo #254 `d38fdd02`, at Ruff `93526150df078af7dd8fc4226cdcc469539d2001` on Linux x86-64. The command used eight Cargo jobs and all workspace default members. Each edit was traced once and restored. A repeated command on unchanged source audited the entire workspace for freshness. The earlier twelve-pair timing study used the initial companion Cargo. This run checks its physical process counts on the corrected Cargo and collects no edit timings. [Registered protocol and portable reproducer](https://github.com/astral-sh/ohm-cargo/tree/582fd25ce7b1471c4921bc053cabf4123f6b7df1/benchmarks/ruff-dev-loop-20261027/corrected-native-rerun-v2) · [Original paired measurements](https://github.com/astral-sh/ohm-cargo/tree/2f07518331735487c84aaeadab58ce98d7c5a71b/benchmarks/ruff-dev-loop-20261027/native-qualified-results)

| Historical Ruff edit | Command | Full rustc | Link-only rustc | Actual Wild processes | Fresh units on the next command |
| --- | --- | ---: | ---: | ---: | ---: |
| Private linter doc correction | `cargo build` | 2 | 2 | 3 | 501/501 |
| Private linter doc correction | `cargo test --no-run` | 4 | 16 | 19 | 619/619 |
| Parser diagnostic | `cargo build` | 3 | 6 | 8 | 501/501 |
| Parser diagnostic | `cargo test --no-run` | 6 | 62 | 67 | 619/619 |

On the parser edit, the built Ruff changed its diagnostic on a mixed t-string and bytes literal and returned to its original diagnostic on restoration. The RUF008 control reported its two expected source locations in every state. The harness checked the actual built Ruff executable, successful command status, full freshness, restored source bytes and the worktree index. Every real linker process was the installed Wild entrypoint. Both `api` integration harnesses, `ruff_wasm` and `ty_wasm` still required full compilation on the parser test build. The remaining two full invocations built `ruff_python_parser` for different units.

Run `python3 verify.py` to check the subjects, helper, process counts and artifact counts. Each event in `receipts.json` records the image basename and a SHA-256 digest of its successful `execve` line. The exporter classifies actual crate compilations by arguments and checks the resolved Wild entrypoint. Raw process arguments stay on the measurement host. [Rerun helper and both historical patches](https://github.com/astral-sh/ohm-cargo/tree/582fd25ce7b1471c4921bc053cabf4123f6b7df1/benchmarks/ruff-dev-loop-20261027/corrected-native-rerun-v2)

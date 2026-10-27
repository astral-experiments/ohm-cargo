# Cached derive hygiene on the release-matched compiler

We ran the same no-op derive and native caller fixture that reproduces four E0460 failures on the published Linux -15 toolchain. The candidate restores the procedural macro server’s definition, call and mixed span contexts on a successful expansion cache hit. A second macro formats a span and an ordinary Rust client prints the result. The fixture uses two local crates and never parses a token string. [Published -15 reproduction](https://github.com/astral-sh/ohm-cargo/tree/a847c60344bbe106f823ee24f8bf8a95699374f6/benchmarks/ruff-dev-loop-20261027/shipped-15-proc-macro-hygiene)

| Second macro reads | -15 warm | -15 clean | Candidate warm and clean | Candidate callers accepted |
| --- | --- | --- | --- | ---: |
| Call site | `#6` | `#9` | `8:#9 bytes(373748..373780)` | 4/4 |
| Mixed site | `#7` | `#10` | `8:#10 bytes(373749..373781)` | 4/4 |
| Root input token | `#0` | `#0` | `8:#0 bytes(373776..373786)` | 4/4 |
| Call site with experimental defaults disabled | `#9` | `#9` | `8:#9 bytes(373748..373780)` | 4/4 |

Every candidate row produced byte-identical raw Rust metadata across its two build histories and agreed with the published compiler’s clean native output. Each row used three full Cargo commands, two independently compiled Rust bridges, four conventional caller compilations and four native executions. Both the retained and the emptied incremental history built the same edited source in the same logical workspace. The sixteen native programs and eight bridge archives have separate SHA-256 commitments. No elapsed times were measured.

Run `python3 -B verify.py` to check all Cargo receipts, source inputs, raw metadata, compiler diagnostics, products and native stdout. The compiler driver SHA-256 is `36d1fd142355c3ad9e0ce006c1e92b7e511cba70c431b09eb1e335f572d27d05`. The separate tracked-file fixture exercises a cache miss discovered after parsing and verifies that the new asset is read. [Tracked-file controls on this compiler](https://github.com/astral-sh/ohm-cargo/tree/8a66ec65e1bc8bb1ac727d47158ff8b700affdbd/benchmarks/ruff-dev-loop-20261027/proc-macro-changed-file-replay3)

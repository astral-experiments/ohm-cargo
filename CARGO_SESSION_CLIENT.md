# Direct session client path

Literal `cargo session check`, `status`, and `stop` invocations accept a small
argument parser for `--socket PATH`, `--socket=PATH`, and `--json`. Other forms,
including aliases, global options, help, duplicate options, and malformed values,
retain the full Cargo CLI parser and its existing diagnostics.

The direct path still creates the normal `GlobalContext`, reads applicable Cargo
configuration (including ancestor and Cargo-home files), warns about aliases that
shadow the builtin `session` command, and configures the same terminal renderer.
Logger, completion, fix-proxy, and jobserver startup retain their existing order.
The client exchange, raw-byte launch identity, protocol bounds, socket naming,
output, and exit handling are shared with the full CLI path. Socket ownership and
mode checks remain in the server.

This targets construction and parsing of Cargo's complete CLI. Executable
loading and Cargo configuration initialization are still included in each call.

## Measured comparison

Linux x86_64 release binaries, 100 alternating pairs after real edits to the leaf
of a 101-crate path workspace, with independent build outputs and the same
compiler for both binaries:

| Compiler | Parent check | Direct check | Parent status | Direct status | Median paired client overhead saved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ohm 1.98.0-2 | 119.88 ms | 116.23 ms | 10.34 ms | 8.56 ms | 1.57 ms |
| Stable Rust 1.97.1 | 107.19 ms | 105.94 ms | 9.91 ms | 8.25 ms | 1.70 ms |

Client overhead is each check's client wall time minus its reported server time.
Server medians were 108.06 to 106.31 ms for Ohm and 95.97 to 96.64 ms for stable;
they show the variance in the end-to-end result. The code changes client parsing.
Both sessions retained one preparation over 101 checks, and every measured edit
updated the leaf dep-info artifact. Startup and cold checks are excluded and
recorded separately. Another 100 alternating status pairs isolate short calls.

The complete [Ohm samples](benches/session/results/client-ohm-linux-x86_64.json)
and [stable samples](benches/session/results/client-stable-linux-x86_64.json)
include binary SHA-256 hashes, compiler versions, all timings, and session
counters. Reproduce with `benches/session_compare.py --before PARENT_CARGO
--after CLIENT_CARGO --crates 100 --rounds 100`, selecting the compiler with
`RUSTUP_TOOLCHAIN` or `--rustc`.

Validation passed: the release build, all 20 `ohm_session` and direct-client
integration tests, and formatting. The focused commands cover `ohm_session_client::` and `ohm_session::` integration
tests plus the session protocol/transport/output unit tests. The direct-client
regressions compare direct and aliased requests under inherited configuration,
including non-UTF-8 cwd/environment/socket bytes, JSON and terminal output, and
success/failure exit codes. They also cover config errors, alias warnings, global
options, malformed arguments, help, and missing-server diagnostics.

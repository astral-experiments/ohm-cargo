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

This targets only the cost of constructing and parsing Cargo's complete CLI.
It does not remove executable loading or Cargo configuration initialization.
Measure both short `session status` requests and end-to-end warm `session check`
requests against the same server configuration and workspace before claiming a
performance improvement. Existing client profiles put the CLI construction cost
near 1.4 ms, so the expected improvement is modest and requires measurement.

Focused validation: run `ohm_session_client::` and `ohm_session::` integration
tests plus the session protocol/transport/output unit tests. The direct-client
regressions compare direct and aliased requests under inherited configuration,
including non-UTF-8 cwd/environment/socket bytes, JSON and terminal output, and
success/failure exit codes. They also cover config errors, alias warnings, global
options, malformed arguments, help, and missing-server diagnostics.

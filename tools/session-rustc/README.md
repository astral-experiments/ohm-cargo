# Experimental persistent rustc worker

The worker embeds `rustc_driver` and creates a fresh compiler session for each request in one process. It requires a matching `rustc-dev` component; it never launches another rustc process to perform a request.

## Build and use

```sh
export RUSTC=/absolute/toolchain/bin/rustc
python3 tools/session-rustc/build.py \
  --rustc "$RUSTC" \
  --rustc-dev /directory/containing/matching/rmeta/files \
  --output /absolute/path/session-rustc
/absolute/path/to/new/cargo session serve --lib --compiler-worker /absolute/path/session-rustc
```

Run session clients with the same `RUSTC` and environment as the server.

Omit `--rustc-dev` when that component is installed in the selected toolchain. The build script checks the installed and development driver hashes, links the existing driver/LLVM, and embeds the selected compiler identity. Installing or registering toolchains is outside the script's scope. Ohm needs development metadata from its exact compiler build; metadata from an official Rust release does not match an Ohm driver.

## Supported scope

The initial implementation supports Linux, one selected host check root, metadata output, and a reusable prepared Cargo plan. Procedural-macro units, wrappers, response files, unstable compiler flags, custom LLVM options, loader injection (including build-script `rustc-env` values), and commands carrying request-scoped inherited files use ordinary rustc. Cargo still owns freshness, diagnostics, job scheduling, build-script execution and locks.

A preparation owns one worker and a stable jobserver shared with its fresh BuildRunners. The complete compiler argv, effective environment and working directory are fixed for a worker. A changed invocation retires it. Compiler/toolchain identity and the worker executable are checked before reuse; startup verifies hashes and the verbose compiler version before dispatch. The driver file must also match an executable mapping in the worker, which detects a different driver selected by the dynamic loader. The worker supplies the selected compiler's sysroot explicitly, since its own executable lives elsewhere.

rustc has process-global backend, LLVM, jobserver, thread-mode and diagnostic state. Exact invocation keys keep those settings fixed. rustc also deliberately keeps native libraries loaded. After every request, the Linux worker compares executable file mappings against startup and retires if additional native code was loaded. This also covers an unexpected proc macro found through an implicit dependency search. A fresh compiler session alone cannot reset macro static variables.

Each result contains separate exact stdout/stderr lengths, bounded to 8 MiB in total. Cargo drains the whole result before passing its lines to the normal compiler-output callbacks. Output uses private unlinked files; those files may grow during compilation, while response materialization is bounded. The worker inherits only the persistent jobserver/control handles, and releases no request build locks into its idle lifetime.

Unsupported commands or a failed identity handshake use ordinary execution before any compiler request is sent. After dispatch, a crash, truncated response or broken connection fails the current check and retires the worker. No second compilation is attempted for an ambiguous result; the next user check can recover. Dropping the preparation kills and reaps its worker.

Session JSON exposes `compiler_worker.pid`, `starts`, `requests` and `fallback_reason`. The PID is present only while a worker is retained; retirement clears it while preserving the counters. A no-op check leaves the request count unchanged because Cargo's fingerprints skip rustc.

## Validation

```sh
python3 tools/session-rustc/test.py \
  --cargo /absolute/path/to/this/cargo \
  --rustc /absolute/toolchain/bin/rustc \
  --rustc-dev /directory/containing/matching/rmeta/files \
  --scratch /directory/with/free/space
```

The test creates an unregistered private toolchain using a copy of rustc and read-only installed libraries. It checks the same worker PID across real source edits, included-file edits, path-dependency API and metadata changes, error recovery, output boundaries, idle lock release, worker/compiler replacement, an active-worker crash with next-request recovery, code-generation output fallback, build-script loader injection, a driver substituted through `LD_LIBRARY_PATH`, a stateful macro's ordinary-execution fallback, and worker retirement after an implicitly discovered macro loads native code. It does not modify installed toolchains.

### Validation environment (2026-09-06)

The real-driver probes and Cargo integration test used the existing stock `1.98.0-x86_64-unknown-linux-gnu` toolchain with its exact matching `rustc-dev` metadata:

```text
rustc 1.98.0 (88d9e12ae 2026-08-18)
commit-hash: 88d9e12ae178fab0fb5cc050a94da85685d449ea
host: x86_64-unknown-linux-gnu
LLVM version: 22.1.8
```

| Artifact | SHA-256 |
| --- | --- |
| Stock `bin/rustc` | `3690cc576ede140504698405d5d8fa3826aaadbe71699c6c4ed0a565d6f493e2` |
| `librustc_driver-28a98848f7a7c026.so` | `56047570f302ba09b1abf3b2996bd1d76560c06f3c95c0fcfa7dc3decd2faa2c` |
| Standalone worker used for driver-mapping and macro-retirement probes | `6795ee33c51df78084e9854ef11c7986588d4a09ad2ae78c56bf2c2845d221cb` |

The worker embeds the selected compiler's absolute paths, so its hash identifies this exact validation binary. The integration test separately builds a worker for its private compiler copy.

The installed Ohm compiler (`1.98.0-dev`, commit `e03456bd2`, 2026-08-21) has a driver library but lacks matching `rustc-dev` metadata. It was not used for persistent-worker validation. Borrowing the stock release's metadata cannot support that Ohm driver; its own matching development component is required. Validation links the installed compiler and LLVM libraries.

## Measurements

Thirty alternating parent/current pairs after real leaf edits in a 101-crate
Linux x86_64 workspace used the same stock Rust 1.98.0 compiler on both sides.
The separate aggregate comparison used the original prepared-session binary as
its baseline. These are client and server medians; startup and cold preparation
are excluded.

| Comparison | Before client | Worker client | Before server | Worker server | Client speedup |
| --- | ---: | ---: | ---: | ---: | ---: |
| Retained-freshness parent to worker | 118.80 ms | 84.48 ms | 106.08 ms | 74.18 ms | 1.406x |
| Original session to complete stack | 109.20 ms | 79.21 ms | 96.75 ms | 69.72 ms | 1.378x |

Both comparisons kept one preparation across 31 checks, with one compiler worker
PID, one start, 31 requests, and no fallback. Every measured edit changed the leaf
dep-info output. The harness rejects a worker restart or ordinary-execution
fallback instead of reporting it as worker performance. No outliers were removed;
the individual samples show substantial host noise, so the two comparisons should
not be combined arithmetically.

The additional 2x target was not reached. These measurements establish reuse and
a gain for the stock compiler; they do not establish the gain for Ohm. Matching
Ohm development metadata is proposed in
[astral-sh/ohm#108](https://github.com/astral-sh/ohm/pull/108).

The measured Cargo implementation is `be94dab`, based on retained freshness at
`b31f140`. Shared Cargo build-script outputs can retain an earlier embedded commit
string, so use the recorded SHA-256 values to identify the actual measured
executables. The standalone worker is the binary identified above.

The release build, 26 session unit tests, 41 session integration tests, and three
session protocol tests pass. The real-driver integration suite also checks the
combined dependency metadata/error/recovery case described above.

Reproduce the paired measurement with:

```sh
python3 benches/session_compare.py \
  --before /absolute/parent/cargo --after /absolute/worker/cargo \
  --rustc /absolute/toolchain/bin/rustc \
  --after-worker /absolute/path/session-rustc --crates 100 --rounds 30
```

[Parent comparison data](../../benches/session/results/worker-stock-1.98-linux-x86_64.json)
and [complete-stack data](../../benches/session/results/stack-stock-1.98-linux-x86_64.json)
include every sample, compiler/worker/executable identity, and session counter.

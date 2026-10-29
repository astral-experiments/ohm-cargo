# Default Cargo fallback for untracked assembler inputs

On Linux x86-64, the default Cargo in each official Ohm 1.99.0-17, -18 and -19 SDK reused integration-test code containing byte 17 after that byte changed to 29. The ordinary Rust dependency edit reached the program. Its own return changed from 6 to 10 while the assembled byte stayed at 17. An independently empty build returned 29 and 10. After a forced full compile, removing the assembler input and restoring the Rust dependency still produced a successful cached build with byte 29. A separate empty build failed in the assembler on the missing file.

## Integration tests

The six release cases each tested one unmodified SDK with its own defaults on or off. Four additional cases tested the same-stamp development parent and candidate, each with a used Rust dependency undergoing a private edit and an unused dependency undergoing a public edit. These ten cases each ran nine commands. Every case started empty, repeated unchanged, changed both the Rust dependency and the native input, ran an independent empty build, forced a full build with byte 29, restored the Rust source with its native input missing, tried another independent empty build with the missing input, forced the same missing build and finally restored byte 17. The checked-in replay script preserves those nine phases.

| Cargo subject | Edited integration test | Missing input on restored Rust source |
| --- | --- | --- |
| Official -17, -18 and -19, defaults on | Link-only, no open, native 17 | Link-only, no open, Cargo 0, native 29 |
| Official -17, -18 and -19, defaults off | Full rustc, reads 29 | Full rustc, receives ENOENT, Cargo 101 |
| Development parent, both dependency relations | Link-only, no open, native 17 | Link-only, no open, Cargo 0, native 29 |
| Development candidate, both relations | Full rustc, reads 29 | Full rustc, receives ENOENT, Cargo 101 |

All ten initial unchanged repeats retained a working executable and started zero unit compilers or native linkers. All ten independent edited builds and all ten forced nonincremental builds returned 29. All ten independent missing-file builds and all ten forced missing-file builds failed. The 80 available integration-target dep-info observations all contain the Rust reader source and omit the assembler payload. Every observed depfile digest and every successfully tested integration ELF digest could be confirmed from a physical retained copy.

## Cross-crate generic binary

A second fixture built an ordinary binary that forbids unsafe code in its own source. A dependency supplies generic inline assembly, which rustc instantiates in that binary. The application and generic library sources stay unchanged. A separate Rust dependency changes its value while the assembler input changes from 17 to 29 and is later removed. Both development Cargo images each ran seven commands on defaults and seven with explicit `-Zrelink-only=no`.

The default parent returned `9:17` on the dirty build and its immediate fresh repeat, versus `9:29` empty. On removal it produced `7:17` with Cargo exit 0, versus exit 101 empty. The default candidate returned `9:29` on both edit and repeat, then failed with the missing-input diagnostic. Both explicit full-compile controls matched the empty verdicts. Every restore printed `5:17`. These 28 commands have full Cargo JSON and verbose invocation logs. The runner recorded each executable’s direct output and SHA-256. Eighteen of its 21 execution observations could additionally be reopened from retained files.

## Subjects and scope

`subjects.json` binds all three official archive hashes, Cargo and rustc versions, compiler driver and native linker. The two development Cargo images use the same stamped version, rustc frontend and actual ca780121 compiler driver. The parent source is `2447f7f4eacb4fdf499899929f08d0de19abb4d0`. The included product patch and exact source hashes identify the candidate. Its Cargo SHA begins `749cde35`, compared with `78d19cdf` on the parent.

The changed default makes a dirty binary or integration target compile while the specialized cached path remains available by explicit opt-in. All 118 commands used `CARGO_INCREMENTAL=0`. The experiments concern dirty consumers, triggered by a real Rust edit. Their results do not establish detection when only an undeclared assembler input changes, explicit cached-codegen safety, incremental backend behavior or a performance change. Switching all Ohm defaults off on a released SDK can also change its native linker selection. The same-stamp development comparison keeps the compiler and native linker fixed.

## Verification and replay

Run from this directory.

```sh
sha256sum -c SHA256SUMS && python3 -IB verify.py && python3 -IB self-test.py
```

The verifier checks Cargo JSON verdicts, native output, source identities, every selected native process, read failures and originating compiler by rebuilding process ancestry from the strace streams. It distinguishes `ld.lld` dispatcher invocations from their executables by preserving every process record. The compressed stream store contains the full projected stdout, stderr and per-thread traces, including irrelevant syscalls and empty traces. Absolute private roots are replaced consistently. The ledgers keep each original file length and SHA-256 alongside its portable stream digest and the original-to-portable hash of each compiler, linker and payload-open line. Generic-bin compiler modes come from Cargo's verbose command lines. Their direct executable outputs come from the original runner's result records.

For a native rerun, provide a complete Linux x86-64 SDK and distinct new directories. The integration harness requires rustup proxies, strace, Python 3.11+ and its original 65 GiB free-space preflight.

```sh
python3 reproduce-integration.py "$SDK" "$NEW/test-used" --incremental 0 --relationship used-private
python3 reproduce-integration.py "$SDK" "$NEW/test-unused" --incremental 0 --relationship unused-public
python3 reproduce-integration.py "$SDK" "$NEW/test-off" --incremental 0 --relationship used-private --defaults-off
python3 reproduce-generic.py "$NEW/generic" "$SDK"
```

The supplemental checked-source proof is separate from the 118 commands. The identical Cargo test binary requested link-only for both the bin and integration target on the parent, tripping the new mode assertion, and passed on the candidate. Six more unwrapped official -19 commands used the literal Rust sources in `regression.rs`. The default run issued two stale link-only requests after the change and the new integration assertion caught the old byte. With explicit `-Zrelink-only=no`, both targets reopened the changed input, the bin printed `22:66`, and deleting the file gave two ENOENT events and an assembler diagnostic. The still-existing `22:66` binary after that failed compile is the incumbent. The supplemental ledger retains the separate Cargo build-finished flag and the overall test process exit.

```sh
python3 reproduce-checked-sources.py "$NEW/checked-default" "$SDK" regression.rs
python3 reproduce-checked-sources.py "$NEW/checked-full" "$SDK" regression.rs -Zrelink-only=no
```

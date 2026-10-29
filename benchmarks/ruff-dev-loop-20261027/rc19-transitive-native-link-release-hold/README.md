# Released Cargo can keep a test binary linked to an obsolete native provider

On the published x86-64 Linux Ohm toolchains **1.99.0-17, -18 and -19**, an ordinary test build kept executing the original program and printed **17** after a separate Cargo build generated the preferred archive returning **29**. Replacing that archive with malformed bytes also produced a successful test build and a program that printed 17. Each incorrect outcome repeated on the next unchanged command. Production-profile Cargo at #280 with source-built Rust from the -19 revision reproduced both failures. [Cargo issue #202](https://github.com/astral-sh/ohm-cargo/issues/202)

The three-crate fixture has the Rust dependency chain `app → middle → provider`. The provider's build script declares `rerun-if-changed=state` and two ordered `rustc-link-search=native` directories under its own `OUT_DIR`. The integration test calls a C function from `#[link(name = "choice", kind = "static")]`. It prints the value returned by the linked machine code. Its own Rust source stays unchanged.

The initial build uses the fallback archive. An ordinary `cargo build -p provider --lib` then creates the preferred archive. Its build script and C compiler/archiver actually ran, and the Rust provider actually compiled. Next, an ordinary implementation edit changes `app::value` from `middle::base() + 1` to `middle::base() + 2`. The function signature is unchanged. `cargo test -p app --test probe --no-run` compiles the app library and reports the integration-test artifact with `fresh=false`. The process trace shows **zero probe rustcs and zero native linkers targeting the probe**. Cargo's subsequent unchanged command reports it fresh. The valid and malformed stages both use exactly the same literal provider `OUT_DIR` and ordered search paths in the preparing and testing commands.

| Build history | Preferred archive returns 29, then unchanged | Malformed preferred archive, then unchanged | Original provider restored |
| --- | --- | --- | --- |
| Provider staged, then app function edited, defaults on, all three releases and #280 QA | 17, 17 | success 17, success 17 | 17 |
| Same source and commands, defaults off, released -17 and #280 QA | 29, 29 | link failure, link failure | 17 |
| Build script and app edit in the same invocation, #280 QA with defaults on or off | 29, 29 | link failure, link failure | 17 |
| Stage `app --lib` before the app edit, #280 QA defaults on | 29, 29 | link failure, link failure | 17 |
| Stage only the provider change and leave app source untouched, #280 QA with defaults on or off | 29, 29 | link failure, link failure | 17 |

The complete executed ELF stayed identical to its own original throughout each failing staged history. The official -17 ELF begins `3f8554b04d91`, -18 `14dadbedd07c`, -19 `f39f638d4669` and QA `de418e8aa21d`. Independently empty QA builds of the exact valid sources returned 29, with ELF `2d82c3c78e55`. Both independently empty malformed cases returned Cargo 101 and named the preferred `early/libchoice.a` in the real linker error. The retained same-size 1,376-byte archives contain distinct code. The verifier resolves the genuine ELF symbol `choice` inside each archive and decodes its return instruction. The malformed input is 22 bytes.

The prebuilt-archive controls place the two search directories in the provider package. With the app implementation edit, all three released defaults and QA kept returning 17 through the valid and malformed stages. QA defaults off relinked and detected both. Changing only those external files without a tracked build-script input or an app source edit left both QA modes at 17. This last case has a different tracking contract from the declared build-script fixture.

## Replay

Use an installed Linux SDK containing Cargo and rustc, a rustup proxy at `~/.cargo/bin/cargo`, `strace`, GCC, and `ar`. Supply a new path for the private fixture. Each line is a complete, independent invocation.

```sh
python3 -IB reproduce.py --stage-producer provider /path/to/ohm-sdk ./warm-staged
python3 -IB reproduce.py --stage-producer provider --defaults-off /path/to/ohm-sdk ./warm-staged-off
python3 -IB reproduce.py --cold-state valid /path/to/ohm-sdk ./clean-valid
python3 -IB reproduce.py --cold-state malformed /path/to/ohm-sdk ./clean-malformed
```

## Evidence and scope

The bundle contains 22 fresh fixture roots, 130 terminal test-build invocations and 27 staging builds. All 112 successfully built programs were run. Eighteen test builds returned a genuine link error. Parsing the syscall traces gives 1,196 successful `execve` calls, 55 actual build-script runs, 58 invocations of `ar` within Cargo, and 60 terminal linker invocations whose actual `-o` named a probe. Some failed commands tried linking twice. Each attempt is counted. Default runs selected the packaged Wild through `wild-ld/ld.bfd`. QA defaults off used GNU `/usr/bin/ld`. Released -17 defaults off dispatched through `gcc-ld/ld.lld` into `rust-lld`. The dispatcher and its real linker are recorded separately.

`streams.tar.gz` retains every available Cargo stdout/stderr, raw process trace and executed test stdout/stderr with local path prefixes replaced. It also retains the original result records, workspace lockfiles and all three distinct native archive payloads. `custody.json.gz` pairs each original digest and size with its portable digest and size, including the SDK component hashes, phase source hashes through the retained records, raw path identities and final ELF reopens. Per-phase executable digests were recorded when the programs ran. Some later phases overwrote earlier executables. The bundle carries their hashes and native stdout, plus complete machine code for the input archives.

`verdicts.json.gz` derives compiler work, actual linker output targets, native search order, Cargo JSON `build-finished`, diagnostics and program values independently of the original summaries. The v1 summaries misclassified the packaged linker and build-script process. For example, the default initial test physically ran one build script and two Wild jobs, then a valid edit ran one build script and a probe Wild job. The old summaries recorded zero and false. On the native-only valid steps the original nominal source operand was 2, while the captured source hashes establish that it remained 1. The portable replay records the actual operand. Cold references used the QA pair. This is a local Linux correctness qualification.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --mutation-test
```

The verifier reparses every projected process trace and Cargo stream, joins successful programs to the reported native executable, reconstructs source variants, checks all 27 stage/test path joins and rejects six altered evidence cases. The original acquisition roots remain separately retained.

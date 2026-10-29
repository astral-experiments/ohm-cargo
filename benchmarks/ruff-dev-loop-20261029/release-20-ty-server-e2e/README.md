# Ruff’s ty_server e2e build on the proposed Ohm 1.99.0-20 sources

An ordinary build of the edited integration test produced the same 212,524,936-byte ELF as an independently empty build. Both listed the same 200 tests and passed the inlay-hint test and two notebook tests. The earlier library in the native search path changed the program’s exit status to 83. A malformed library failed the link. Removing either replacement restored the original executable.

| Change | What the build or executable did |
| --- | --- |
| Real Ruff inlay-hint edit | Linked the edited e2e executable. An independent Cargo home, target and shared build directory produced identical bytes. |
| Invalid Rust edit | Cargo exited 101 with E0308 at line 22. The e2e linker did not run. |
| Earlier valid `libgcc_s.so`, unchanged Rust | Ordinary and forced links both produced a program that exited 83. |
| Malformed `libgcc_s.so`, unchanged Rust | Ordinary and forced links both reached the stock e2e linker and failed. |
| Native provider removed | Both recovery runs restored the original executable and test inventory. |

The tested Linux x86-64 subjects were a source-built Rust compiler at ad005f99d0b5, Cargo at 7277e6cdaba4 and the existing released Wild. The hosted Linux and macOS distribution build and installed-package smoke tests are separate. [Rust change](https://github.com/astral-sh/ohm-rust/pull/266) · [Release manifest](https://github.com/astral-sh/ohm/pull/206)

The original Ruff checkout was 93526150df078af7dd8fc4226cdcc469539d2001. In a private checkout, reverse the inlay-hints file from the historical Ruff change. Use distinct empty Cargo target and shared build directories for the cold control. The fixture records the historical patch and test cases. [Historical change](https://github.com/astral-sh/ruff/commit/1b9310471b7d1178633e58ee63808522609db887) · [Original test fixture](https://github.com/astral-sh/ohm-cargo/tree/1d9c6ad6bf85bae5af3447063add7ac67f78140c/benchmarks/ruff-dev-loop-20261027/rc19-ty-e2e-historical-root-edit)

```sh
git diff 1b9310471b7d1178633e58ee63808522609db887^ 1b9310471b7d1178633e58ee63808522609db887 -- crates/ty_server/tests/e2e/inlay_hints.rs | git apply --reverse -
cargo +ohm test --locked --offline --no-run -j4 -p ty_server --test e2e --message-format=json
```

The receipt contains all 15 observed Cargo outcomes, physical compiler and Wild counts, program verdicts, artifact hashes, and digests of the original output and traces. Run the verifier from this directory to check these comparisons.

```sh
python3 -IB verify.py
```

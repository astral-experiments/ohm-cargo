# Linux source qualification for Ohm 1.99.0-20

The release draft pins Rust `05efba7a06f5bb71d1efb4b86805800f8b810779` and Cargo `7277e6cdaba44c43294a07c0661fc8e69fd8e3e7`. The tested optimized stage1 compiler used that source, the same standard libraries as its parent, and the stock Linux Wild shipped by Ohm. The release workflow builds, optimizes and smoke-tests the final Linux and macOS distributions separately. [Release draft](https://github.com/astral-sh/ohm/pull/206)

### Ruff edits and native libraries

A historical edit to Ruff's inlay hints test changed the complete `ty_server` e2e executable. Its 214,113,280 bytes matched a second build that started with an empty target, build directory and registry source extraction. Restoring the original source reproduced the original executable. All ten ordinary successful visits returned the same 200 test names, and three affected or adjacent tests passed on each. An invalid Rust edit returned Cargo 101 with E0308 at line 22 before linking the e2e executable.

Introducing a native library earlier on the search path changed the executable's exit from 0 to 83. Forcing the link produced identical bytes. Both an ordinary and a forced build rejected a malformed replacement with Cargo 101. Removing it restored the original executable. The two ordinary unchanged visits still linked the e2e executable once apiece. The native readback reconciled 30,186 per-thread trace files, all 15 Cargo JSON streams, and four retained executables.

### Compiler and training

Five compiler regression suites passed with 38 real compiler invocations. They covered checked dependency information, assembler inputs, a UTF-8 proc-macro span, separate linking, and overwriting newly compiled or restored link objects. [Compiler fix](https://github.com/astral-sh/ohm-rust/pull/268)

The Linux distribution's actual rustc-perf collector prepared 306 dependency crates in each run. With the release's training-only Cargo override, all four Debug and four Opt scenarios completed the selected `cargo-0.87.1` library and produced nonempty native archives. A deliberately invalid library failed its real compiler and the collector. After restoring the source, Cargo reused 301 dependency archives and produced a 356,342,712-byte executable. Running it against a downstream manifest returned version `0.1.7`, then `0.2.9` after a genuine edit. The verifier reopened the repaired executable and library archive, checked their identities and traced the final linker to the resulting file.

### Repeat the checks

Run the following in this directory to verify the published measurements and nine deliberately corrupted controls.

```sh
python3 -IB verify.py --self-test
```

With the candidate installed as the `ohm` toolchain on x86-64 Linux, rerun the 15 Cargo visits using a local Ruff clone containing both `93526150df078af7dd8fc4226cdcc469539d2001` and `1b9310471b7d1178633e58ee63808522609db887`. The registry argument is a prepared offline Cargo registry containing its index and crate archives. The work directory must be new. The script requires Python 3.11 or later, Git, rustup, strace and a native C compiler.

```sh
python3 -IB rerun-ty-server.py --ruff "$RUFF" --registry "$REGISTRY" --work "$NEW_WORK"
```

Run the release collector command once with `PROFILE=Debug` and again with `PROFILE=Opt` from its rustc-perf checkout at `0a054b0ead56e41a4584bfab6fdc1a5fad2aedc3`. Supply the physical Rust and Cargo executables and choose a separate fresh output directory for each profile.

```sh
target/debug/collector profile_local eprintln "$RUSTC" --id OhmReleaseFallback \
  --cargo "$CARGO" --profiles "$PROFILE" --scenarios All --exact-match cargo-0.87.1 \
  --jobs 4 --out-dir "$OUT" --cargo-config unstable.ohm-defaults=false
```

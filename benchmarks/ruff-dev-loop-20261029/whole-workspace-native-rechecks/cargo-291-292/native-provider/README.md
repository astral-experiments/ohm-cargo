# A historical Ruff edit and native providers with Cargo #292

On the same Linux machine, matched builds of Cargo #291 and #292 each ran thirteen focused commands and seven complete workspace commands with the same compiler, linker and Ruff source. The first six-command comparison counts all fifty registered test targets. This follow-up checks what those targets actually do when a native library appears earlier in their linker search path.

Across the forty follow-up commands, the verifier reopened 103,988 per-thread kernel records, compared Cargo’s typed inventory and replayed the recorded program bodies from sealed Linux file descriptors. It authenticated 103 distinct complete ELF files. Raw stdout, stderr, argv and native artifact commitments are retained. The packet includes every physical Cargo, rustc, GCC, collect2 and stock Wild launch with its input digest. The cohort measured work and behavior; it contains no wall or instruction samples.

The first independent executable recheck used an empty working directory. A generated mdtest harness returned 101 because it discovers its test names by reading fixtures relative to its package. A controlled replay on the same sealed ELF reproduced that failure in the empty directory and returned the original listing in the real package directory. The final readback opened the pinned fixture tree read-only at the recorded source path and supplied each target’s own Cargo manifest directory. The first updated readback stopped before any execution because its package path shadowed a Python variable used to count relative helper calls. Correcting that variable left the acceptance rules unchanged. All verifier attempts and original hashes are retained. [Ruff harness](https://github.com/astral-sh/ruff/blob/93526150df078af7dd8fc4226cdcc469539d2001/crates/ruff_mdtest/tests/mdtest.rs)

## Whole workspace

Each arm issued the ordinary command `cargo +ohm test --workspace --no-run --locked --offline -j4 --message-format=json` after the previously measured repeats. The study installed a valid GNU linker script only in the private psm build output. Its object uses a Linux initialization function that exits 83. When forced, we preserved and removed the three selected private harness outputs for e2e, generate_inline_tests and ty_python_semantic before invoking the same command. The stock GCC script and both good source copies were authenticated at the end.

| Native state | Cargo exit | #291 full / cached / Wild | #292 full / cached / Wild | Tracked Wild links on #291 / #292 |
|---|---:|---:|---:|---:|
| 01-native-valid | 0 | 107 / 0 / 103 | 91 / 16 / 103 | 50 / 50 |
| 02-remove | 0 | 107 / 0 / 103 | 91 / 16 / 103 | 50 / 50 |
| 03-forced-valid | 0 | 107 / 0 / 103 | 91 / 16 / 103 | 50 / 50 |
| 04-malformed | 101 | 12 / 0 / 8 | 9 / 4 / 9 | 1 / 1 |
| 05-remove | 0 | 107 / 0 / 103 | 103 / 4 / 103 | 50 / 50 |
| 06-forced-malformed | 101 | 12 / 0 / 8 | 9 / 2 / 7 | 1 / 1 |
| 07-final-remove | 0 | 107 / 0 / 103 | 105 / 2 / 103 | 50 / 50 |

| Malformed whole-workspace visit | Actual Cargo diagnostic targets |
|---|---|
| K/04-malformed | ruff_mdtest (test "mdtest"), ty_wasm (lib), ruff_wasm (lib), ruff_dev (bin "ruff_dev" test) |
| K/06-forced-malformed | ty_wasm (lib), ruff_wasm (lib), ruff_mdtest (test "mdtest"), ruff_dev (bin "ruff_dev" test) |
| U/04-malformed | ruff_mdtest (test "mdtest"), ruff_wasm (lib), ty_wasm (lib), ruff_dev (bin "ruff_dev" test) |
| U/06-forced-malformed | ruff (bin "ruff"), ruff_wasm (lib), ty_wasm (lib), ruff_mdtest (test "mdtest") |

For each arm, all fifty executables produced by the valid provider actually returned 83, and the individually forced visit returned the very same fifty full ELF hashes. The malformed script made both normal and forced builds return Cargo 101. Failures may stop concurrent jobs at different points. Those partial counts remain in the table and raw projection. On removal, all fifty exact native listings returned, and the three separate genuine recovery visits agreed on all fifty full products. The two Cargo versions also agreed byte for byte on each corresponding successful product.

## Focused test and independently empty references

A separate `cargo +ohm test --locked --offline --no-run -j4 -p ty_server --test e2e --message-format=json` history reverses the one-file inlay-hints change in the pinned checkout, then checks both implementations, an invalid Rust statement, and recovery. The modified expected source location points to the genuine builtins definition while the corrected expectation points to the local Python class. The complete e2e listing contains 200 tests. Both notebook checks and inlay_hints::default_inlay_hints passed in every applicable visit, including each independently empty edited build. The same-generation typed reader loaded ruff_python_parser and ruff_db. [Ruff change](https://github.com/astral-sh/ruff/commit/1b9310471b7d1178633e58ee63808522609db887)

| Focused product | Whole ELF SHA-256 |
|---|---|
| Original and restored | `09884ef6b815aa9d88c5e121e7fb5d733c412e5a195e3c7de5fbbd1d7e6b674e` |
| Historical edit and independently empty | `2b13e02670cdcd694f5d154c3bdb83ab04bd47a7bab56dd03cc8a32909f5f28a` |
| Valid native provider | `25c1b1bb629669e3353d5a70bf6a505fb75e0f1a5998ed29f28f46e2d380c780` |

The historical edit launched four full rustcs, no link-only rustcs and two genuine Wild processes on each arm. Each independently empty reference ran 303 full rustcs and 48 Wilds. Cargo reported identical E0308 at line 22 on the invalid source. Both normal and forced malformed native links failed with Cargo 101. Both ordinary and forced valid providers exited 83, and removing them restored the original program. Stock Wild’s open trace saw the added script and object on the actual target. Both Cargo versions passed 48 focused test executions in total. The full test stdout differed in eleven of twenty-four corresponding transcript pairs solely in libtest’s printed duration. Each stdout and original stderr digest is retained, along with the full assertion text.

## Verify and rerun

```sh
python3 -IB verify-native.py --self-test
python3 -IB replay-focus.py --help
python3 -IB replay-whole.py --help
```

Use a normal Linux x86-64 user, Git, rustup with rustc and Cargo proxies, Python 3.11+, GCC using the GNU libgcc_s.so script, strace, zstd, four available CPUs, a Ruff checkout and a complete locked sparse Cargo registry. Use matching Ohm development Cargos built from the two source pins with the ohm-defaults feature and genuine source revisions in cargo -Vv. Supply the complete matched Rust SDK with LLVM, rust-src, std and stock Wild. The run areas and each parent must be trusted by Cargo. Select CPU numbers valid on your system and absent, separate work directories. The focus command expects more than 26 GiB free disk and 12 GiB available RAM at its default floors. The whole command expects more than 56 GiB disk and 12 GiB available RAM. The original study enforced higher admission floors (120 GiB disk and 48 GiB available RAM).

```sh
python3 -IB replay-focus.py --ruff "$RUFF_GIT" --registry "$CARGO_HOME/registry" \
  --sdk "$OHM_SDK" --cargo "$CARGO_291" --work "$SCRATCH/focus-291" --cpus 0,1,2,3
python3 -IB replay-focus.py --ruff "$RUFF_GIT" --registry "$CARGO_HOME/registry" \
  --sdk "$OHM_SDK" --cargo "$CARGO_292" --work "$SCRATCH/focus-292" --cpus 0,1,2,3
python3 -IB replay-whole.py --ruff "$RUFF_GIT" --registry "$CARGO_HOME/registry" \
  --sdk "$OHM_SDK" --control "$CARGO_291" --candidate "$CARGO_292" \
  --work "$SCRATCH/whole-native-provider" --cpus 0,1,2,3
```

The alternate launchers retain their generated private states, actual exec traces, diagnostics and reader results. We checked their CLIs, parser and input selection separately. The forty observations above came from the registered private mount controller. Its six earlier whole-workspace visits form the separate primary evidence. These source-built development products have no signed release claim. [Cargo #291](https://github.com/astral-sh/ohm-cargo/commit/84af87848a5a952ba61ae6a2cc5b22da24130200) · [Cargo #292](https://github.com/astral-sh/ohm-cargo/commit/98d431a99779ccfbcfe42dfa74dd541de3a92d05) · [Rust W](https://github.com/astral-sh/ohm-rust/commit/ad005f99d0b51fd62b5c237bc13b31b371a1686e) · [Ruff checkout](https://github.com/astral-sh/ruff/tree/93526150df078af7dd8fc4226cdcc469539d2001)

# Recovering already stale executables with the same Cargo version

Eight independently trained states cover an integration test and an ordinary binary, an updated or missing assembler input, and two modes for the replacement Cargo. Both cargos report exactly the version in `cargo-version.txt`. The installation stayed at the same literal location. Only the Cargo executable was replaced. The recorded source, assembler input, compiler, manifests, environment, and published native output retained their device, inode, size, timestamps and SHA-256 across that operation.

The original executable was built using Cargo source `2447f7f4`. The replacement was built from the same source plus the patch in `cargo-source.json`. Both are debug Cargo builds. The compiler was the same optimized stage1 Rust `ca780121` with its 53 matched target library files and the stock Wild linker throughout. These Linux x86-64 cases use `CARGO_INCREMENTAL=0`. The replacement was exercised in its normal default configuration and with explicit `-Zrelink-only=no`. Explicit `-Zrelink-only=yes` and compiler incremental reuse are outside this result.

## Observable results

The old Cargo built a program reporting 17. The real Rust edit triggered cached codegen and a real Wild link, but the assembler never reopened the payload. The native result remained 17 after replacing the payload with 29 and after removing it. An independently empty build reported 29 or failed to compile the missing input. The ordinary binary also proved that it consumed the changed Rust function, with its separate Rust result changing from 6 to 10. Reinstalling the original Cargo at the same path left the wrong executable fresh.

After upgrading Cargo, only the affected native reader compiled on the first unchanged command. All four valid cases reported 29 and matched the independent empty executable byte for byte. All four missing cases returned Cargo 101 immediately and again on the next invocation. Reintroducing the payload repaired all four. In both modes all eight subsequent genuine edits reassembled, reported 41, and matched their independently empty executables. Subsequent successful exact repeats, library-only builds, and settled all-target checks did no compiler or linker work.

The separate two-package workspace had 12 typed products and 11 pre-existing cached executable manifests, covering binaries, integration tests, benches, examples and a library test harness. After replacing Cargo, it ran precisely 11 full rustc processes and 11 stock Wild processes for those 11 manifests. All 12 products were fresh on the next whole native command. Both all-target checks and the ordinary library build also stayed fresh.

The initial broader verifier stopped at strict byte equality. Ten of the eleven native outputs matched. The sole differing example harness had 1,073,672 bytes. A separate diagnostic replayed the original literal Rust arguments with its retained link-input file and the two retained objects, varying the stock linker width. Width 1 reproduced the exact new SHA-256, and widths 2, 3 and 4 reproduced the exact old SHA-256. Both full files agreed outside the 32-byte GNU build ID and the section-header entry size for `.rodata` (1 versus 0). Every replay listed zero tests and executed successfully. The original Cargo commands did not record Wild's worker count. The failed comparison and subsequent no-op are separate observations. Whole binaries contain private source paths and are retained outside the portable packet.

The first pilot misclassified an unsuffixed binary output in its Wild trace. The original traceback and component hashes are retained. All eight accepted states were trained from scratch under the corrected classifier, independently of that pilot.

## Reproduce

Run the following in this packet to verify all 144 primary command records, the 12 broader workspace command records, and the four diagnostic native links.

```sh
python3 -IB verify.py
```

A custodian can additionally pass `--raw ROOT` to authenticate the original stdout, stderr, per-process traces, and actual executed program outputs, and `--elf-pair OLD NEW` to reread both complete native files and check every byte. Each command's exported record is directly verifiable against its raw receipt digest. Diagnostic messages use a workspace alias in the portable copy and retain their original text digests.

For a fresh execution, supply the same compiler SDK and the two source-bound cargos, use a previously absent study directory on an ordinarily owned root, and run each stage on the same fixed CPUs. Substitute the binary digest and case arguments for the desired row.

```sh
taskset -c 8-11 python3 -IB migration.py train "$case_dir" "$sdk" "$old_cargo" --sha256 "$old_sha" --kind bin --poison valid --new-flag default
taskset -c 8-11 python3 -IB migration.py upgrade "$case_dir" "$sdk" "$new_cargo" --sha256 "$new_sha" --kind bin --poison valid --new-flag default
```

Use `test` for the integration test, `missing` for the missing input, and `explicit-no` to exercise the explicit disabling option on the new Cargo. Each combination needs its own empty directory and the Rustup Cargo proxy on PATH. The worker records actual tool execution and kernel file opens under strace. No timings were collected.

# Combined Cargo mode-fingerprint, assembler and generated-file checks

The combined Linux Cargo rebuilt the unchanged binary on both relink-mode switches and diagnosed an invalid build the first time it was selected. Its default integration-test build reopened an assembler input after a genuine Rust dependency change, produced an executable matching an independent empty build, rejected the missing input, and safely updated all five tested generated Cargo files. Two limits matter for release attribution.

* Official Ohm **1.99.0-18 is affected** by the mode-fingerprint defect. Both default → no and explicit yes → no returned Cargo 0, ran the old program printing 17 and repeated that false success with no consumer rustc. Moving only the 16-byte consumer fingerprint made the next build report the same macro error as an independent empty build. The earlier same-path qualification separately establishes this on official -19.
* **Explicit `-Zrelink-only=yes` still reuses stale machine code with this combined Cargo.** The Rust dependency edit was observed, but the link-only test reader did not reopen the assembler input. It returned native 17 instead of 29. With the input missing, it still linked successfully and returned the previous 29. Independent empty and forced-full builds both failed on the missing input. Each link-only row ran the stock Wild linker. The default and explicit cases both used `CARGO_INCREMENTAL=0`.

| Fixture | Cargo commands | What the original native runs established |
| --- | ---: | --- |
| Combined, two executable values | 14 | Default → no gave 17→29, no → default gave 29→17. Each changed-mode invocation ran one full binary compiler and one stock linker. The switched ELF exactly matched the opposite independently empty build. Each immediately unchanged repeat was fresh. |
| Combined, compile-error mode switches | 15 | From both default and explicit yes, the first no-mode invocation and its repeat genuinely compiled the unchanged consumer and returned Cargo 101. Empty builds had the identical diagnostic and primary span. Restores printed 17 and then settled fresh. |
| Official -18, compile-error mode switches | 17 | Each old warm history falsely succeeded twice. The two one-fingerprint evictions, two independent empty no-mode commands, and real restorations separated Cargo freshness from compiler semantics. |
| Combined, default integration assembler | 9 | The used library's private edit changed the Rust result 6→10 while the assembler byte changed 17→29. The trained and empty edited ELFs were byte-identical. Removing the byte and restoring the Rust source produced Cargo 101 and a traced reader ENOENT. Restoring the byte produced the original 17/6 ELF. |
| Combined, explicit-yes integration assembler | 9 | On the same edit, trained 17/10 differed from empty 29/10. After removal, trained 29/6 differed from the empty compiler failure. Forced compilation restored the empty verdict in both cases. |
| Combined, protected generated writers | 17 | Public-API hash and workspace resolve records each passed three phases. Message provenance and the check-graph hint each passed four. The relink manifest passed three. All five wrote the generated entry while preserving an unrelated owned sentinel's bytes and inode. The four probes that requested an unchanged repeat observed fresh artifacts. |

The proc macro is re-exported through an ordinary facade library. The actual compiler flag changes its expansion to a different integer, or to `compile_error!("link recipe was not requested")` in the diagnostic fixture. All rejected macro builds point to `consumer/src/main.rs:1:28`. The assembler fixture uses an untouched registered test containing `global_asm!` with `.incbin`. The test executable reads the resulting symbol and prints both the native byte and the Rust dependency’s value. Its dep-info omits the assembler payload. These cases pair a real Rust dependency edit with the changed assembly input.

The generated-writer probes are byte-for-byte the previously registered public-API, resolve, provenance, check-hint and relink-manifest protocols. The three phase-sensitive probes installed their sentinel symlink upon a genuine inotify deletion. All files were in new caller-owned directories. The build and check probes ran with ordinary user privileges. An initial remote launcher had an unterminated Python string and stopped before any source extraction or Cargo invocation. Correcting that launcher left all registered probe bytes identical.

## Source and verification

The combined PGO Cargo came from `2fe90823d8eadc95de56c2cde8d41e0082aac0eb`, tree `99f8de907ed0bfe7ccab4b22cbebd74b25bb010d`, binary `967f5f1db2938847fac22d78dc222054cbb143a5fabcffcad0bd15f8929b47e9` (43,361,392 bytes). It used the compiler and native linker from the signed -19 Linux distribution, archive `ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812`. The shipped -18 control used its own authenticated, already-installed -18 Cargo, rustc, driver and original native linker. Its archive is `629abab6a87c84bb4d910549ca96a31e437e3dc9de3039fedcbb7b50d198a5e8`. Source, build, runtime, input and original raw-stream commitments are in [subjects.json](subjects.json). [Combined Cargo source](https://github.com/astral-sh/ohm-cargo/commit/2fe90823d8eadc95de56c2cde8d41e0082aac0eb)

The 46 macro-fixture commands retained 1,522 per-process syscall files and 262 successful exec calls. The 18 assembler commands retained another 741 trace files, 32 reader/library compiler execs, 12 native linker execs and 15 actual payload lookup events. Cold scheduling can issue multiple compiler invocations, including duplicates with identical argv. The per-command rows preserve those events. The 17 generated-writer commands used ordinary Cargo JSON, native program output where applicable, actual inotify witnesses, and a separate reopen of the sentinels. This packet contains no timing estimates.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

To execute the cases with the exact enrolled binaries, supply a fresh private directory, an SDK containing the combined Cargo alongside the official -19 frontend and libraries, and the official -18 SDK. The runner checks all tool hashes and requires the Linux rustup proxies and strace. It uses the benchmark machine’s 24 GiB plus 600 MiB capacity guard. The explicit assembler arm differs from the default arm by the one Cargo argument in [assembler-yes.patch](assembler-yes.patch).

```sh
python3 -IB replay.py NEW_DIRECTORY COMBINED_WITH_19_SDK OFFICIAL_18_SDK
```

The `--only` selector accepts `values`, `diagnostics`, `assembler`, or `writers` for a focused rerun.

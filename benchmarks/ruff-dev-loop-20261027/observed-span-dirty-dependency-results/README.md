# Defer the observer checksum scan when an upstream compiler job is already dirty

One byte in a private documentation line changes the native result in two procedural-macro span readers. This seven-package workspace exercises the first complete build after that edit and the unchanged build immediately preceding it. Both Cargo binaries use the same release-PGO/BOLT compiler. The earlier Cargo stores a checksummed receipt for the reader’s binary and source inputs. The candidate defers scanning that receipt when a dependency is already dirty and checks the dependency’s current output first when deciding whether the reader must recompile. A reuse decision still verifies every recorded input.

| Full native build | Earlier receipt median | Candidate median | Median paired reduction | Favorable pairs | Paired median interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| First build after the edit | 519.54 ms | 417.36 ms | 19.83% | 12/12 | 17.58% to 20.98% |
| Already trained, unchanged | 99.01 ms | 100.72 ms | −2.08% | 4/12 | −5.03% to +2.47% |

The edit was the registered primary. Its one-sided exact randomization test gave 1/400, or 0.0025. Each edit direction had six pairs and three runs starting with each arm. The unchanged negative control narrowly missed the prespecified −5% lower bound. Its timing is inconclusive for noninferiority at that margin. Both results retain all measured commands. A Python import failed before any store, Cargo command or sample in the first launcher preflight. [Frozen registration](https://github.com/astral-sh/ohm-cargo/blob/635015127c5db7e73f9d011bb814058469d41941/benchmarks/ruff-dev-loop-20261027/observed-span-dirty-dependency/screen4-registration.json)

Both arms ran four full rustcs, a link-only rustc and three final native linkers on each audited edit. Only the two actual observers collected binary dep-info. Both arms launched zero rustcs and linkers on unchanged replays. The ordinary sibling's output stayed constant, and both readers printed the changed position. All three executable hashes matched their independent empty-build references for all 48 timed commands and 48 separately traced repetitions. The 654 successful process executions across the 66 untimed gates and replays are recorded individually. Two additional unfinished, unidentified syscall records had no returned status.

The exact-binary file-read diagnostic ran separately from the timed pairs. On both edit directions the earlier Cargo read 140,324,731 SDK bytes and 1,510,661 other library bytes, while the candidate read zero SDK bytes and 32,710 other library bytes. Each edit still required 88,319,067 SDK bytes from the intermediate reader’s rustc and 98,902,551 from the terminal reader’s rustc to reconstruct their receipts. In the two fresh commands, both Cargo binaries read the same 98,902,551 SDK bytes and 517,323 other library bytes. These are observed Linux read/pread counts from those invocations. The count collector records only integer byte totals, executable class, library basename and input class.

Ruff’s separately audited default test build had one span reader, registry dependency `ron`. Its 11 locked transitive dependencies all came from the registry. Ordinary changes to Ruff’s own Rust source do not dirty that observed registry closure. This edit result therefore applies to the fixture that genuinely changes such an input. The earlier comparison with packaged Cargo also showed a real-edit cost from asking rustc to reconstruct the two strict receipts.

The exact Cargo changes are in `observer-edit-screen1.patch` against commit `b0a4df740b57589ecec3c83e30d5d326ab52a56d`. The release binary is `98bcf7ae65f677af0e6af1f31cc725741525112ea51a2245c8b0aa7d3d426115`. The baseline is `a99a694c680f474bef2ae17de20533890dc536606021db93aaf531e3ef40919a`. A separate packaged Cargo at `d577be8eb1db7a3a4e4a82246d64644aaf3e0bff` produced both golden builds. `subject.json` includes the full compiler and Cargo digests. The safety records cover corrupted, truncated, legacy and inherited receipts, opaque wrappers, backdated writes, simultaneous reader-local errors, a same-mtime symlink replacement, separately completed producers, an indirect warm bridge, check and test-build modes, and compiler and Cargo upgrades.

Run `sha256sum -c SHA256SUMS` and `python3 -B verify.py` here to verify the frozen observations and recompute statistics. The native study requires Linux, bubblewrap, strace, four reserved cores, the exact matching toolchain and a Rustup proxy with an Ohm alias. The fixture and both incremental Cargo changes are included. `STATE/sysroot` contains the SDK and `STATE/rustup` resolves `+ohm` to that SDK. The physical working directory must be new. The package has no registry dependencies.

```sh
PREVIOUS_CARGO=/absolute/cargo-with-observer-receipts \
  python3 -B screen4-study.py --mode score --cpus 0-3 \
    --work /dev/shm/ohm-observed-edit-replay --state /absolute/STATE \
    --driver /absolute/librustc_driver.so --parent /absolute/cargo-golden \
    --candidate /absolute/cargo-with-dirty-dependency-guard
```

Use `trace-screen4.py` with the same argument list and a new working directory to collect the six separate file-read diagnostics. The input data and associated repository are access-controlled.

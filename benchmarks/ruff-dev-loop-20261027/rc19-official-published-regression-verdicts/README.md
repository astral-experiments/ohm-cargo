# Published Ohm 1.99.0-19 Linux regression verdicts

The published Linux distribution accepted an invalid, unchanged application after an upstream edit, then accepted it again on the next check. An independently empty check reported E0034 at `client/src/main.rs:3:30`. A separate pipeline recovery fixture reported E0460 on its first reverted build. Both cases used the Cargo and Rust binaries from the downloadable release. [Ohm 1.99.0-19 release](https://github.com/astral-sh/ohm/releases/tag/ohm-1.99.0-19)

## Invalid method call under two publication orders

The original program calls `Token.priority()` with one matching trait implementation. The edit adds a second implementation upstream and changes the private body of the middle reexporting crate. The application source stays byte-identical. The edited dependency's public API hash changes while the middle crate's public hash remains the same.

| Actual Cargo check | Published -19, provider held | Published -19, provider first | Fixed Cargo QA, either order |
| --- | --- | --- | --- |
| Original / unchanged original | Pass / pass | Pass / pass | Pass / pass |
| Edited | **False pass** | E0034 | E0034 |
| Next unchanged edited | **False pass**, all four fresh | E0034 | E0034 |
| Independently empty edited | E0034 | E0034 | E0034 |
| Restored / unchanged restored | Pass / pass | Pass / pass | Pass / pass |

Each column for the published package represents seven actual `cargo +ohm check --workspace --locked --offline -j4` commands in its own workspace. The timing controller holds and releases an existing metadata timestamp operation on the provider or reexporter during the edited call. The other six commands in each order run without the controller. The controller's successful returns preserve the exact timestamp requested by Cargo. The raw control events and the corresponding fingerprint and metadata digests are retained. The two release orders emitted byte-identical rendered diagnostics wherever they rejected the invalid call. The fixed QA controls emitted the same diagnostic, including both candidate traits and the application span.

Cargo JSON labels the client artifact for the first falsely successful edit as non-fresh. The following unchanged invocation explicitly reports all four artifacts fresh. The release check fixture records Cargo's verdict and artifacts. Its two runs have no per-process tracing that would equate that artifact flag to a rustc launch.

## First revert after a failed producer

The checked-in Cargo test's wrapper forwards real compiler invocations, synchronizes the producer after metadata publication, waits for its dependent library to commit its 16-byte short fingerprint, then deliberately fails the producer. The runner checks the producer fingerprint is empty before reverting the source.

| Native behavior after restoring the source | Published -19 | Fixed Cargo QA |
| --- | --- | --- |
| First reverted build | Runs dependency library and application binary. Rustc reports E0460. | Runs dependency library, application library and application binary. Succeeds. |
| Recovery | Next unchanged build recompiles the application library and binary. Program prints 1. | First reverted build's program prints 1. |

The original and final released programs both ran and printed `1`. The retained final 436,648-byte application ELF has SHA-256 `0dfe4722bb9ea05666b511d5282a0ca6cf4eb869904c206850e6eebcdf8a94c8`. The portable records include the literal syscall line digests for each actual compiler role, full stdout/stderr commitments and the fixture wrapper ELF digest. These observations describe the checked-in synchronized failure.

## Release and comparator identities

The official 359,628,600-byte Linux archive has SHA-256 `ef21d83519bc376479811a7e01fa5ac8915ac0a500c6859bc22a1e0b4913d812`. It matches the authenticated GitHub release asset digest, the published SHA256SUMS and the per-archive checksum file. Each of the five installed ELFs was read directly from the compressed archive, its independent unpacked tree and its final installation. The release manifest pins Cargo `235f9228651b` and Rust `eef2f3425c1c`. The installed Cargo ELF starts `789c2f116732`, rustc `5694abe50767`, rustc_driver `f772b49abec1`, rustdoc `a368ad0fdc5a`, and Wild `0d6335808b64`. Full SHA-256 values, ELF sizes, archive member names, published source revisions, and native Cargo/rustc versions are in `official.json`.

The independently acquired fixed comparator uses production-profile Cargo `34dad66fd2ac` (ELF `a9c1b18bbb02`) with a source-built optimized stage1 Rust from the same `eef2f3425c1c` revision. Its frontend and driver differ in bytes from the published archive. Its unchanged Wild matches the release's Wild. The original QA manifest `54f63217c50e2c77349e932aff33e7c0f620dedf31d2b386e6eaf12aa13d41ef` binds its complete outcome and underlying raw-file ledger. [Cargo #279](https://github.com/astral-sh/ohm-cargo/pull/279) · [Cargo #280](https://github.com/astral-sh/ohm-cargo/pull/280)

## Reproduction

```sh
sha256sum -c --quiet SHA256SUMS
python3 -IB verify.py --selftest
python3 -IB trait/reproduce.py /path/to/installed-19 /new/private/provider-late provider-late --expect stale
python3 -IB trait/reproduce.py /path/to/installed-19 /new/private/provider-first provider-first --expect correct
python3 -IB revert/reproduce.py /new/private/reverted --rustup-home /private/rustup --mode default
```

The private rustup home for the last command must link its `ohm` alias to the installed Linux SDK. The fixture and controller sources are exact copies of the previous registered experiments. Compressed Cargo streams are complete apart from replacing the private run-directory prefix with `@RELEASE_REPLAY@`. The packet retains both the original and normalized digests and the substitution counts. Original binaries, distribution archive and raw traces stay in the acquisition store, including binaries that embed private absolute build paths. To reread all primary evidence and both comparison inputs, run `reconstruct.py --help` for its five directory arguments, then invoke it with `--compare`.

# Workspace resolution across trailing Cargo profile changes

The candidate reused the workspace resolution on five manifest transitions where the parent missed. Both Cargo images still recompiled or reran the same code, produced the same four complete executables, printed the same values, and emitted the same warnings and errors. The original 38-command run and a separate 38-command execution of the supplied replay reached the same native result at every stage.

The experiment used a two-crate local fixture. The main package’s build script explicitly rereads the raw Cargo.toml, watches it with `rerun-if-changed`, and exports the value of a comment as `RAW_PROFILE_VALUE`. The binary prints that value and its actual `cfg!(debug_assertions)`. A second package is available by path and is initially absent from the lockfile. A multiline string containing a fake profile header precedes the real trailing profiles. [Executable source, fixture and replay](replay.py).

The control is private release-profile PGO Cargo `2fe90823d8eadc95de56c2cde8d41e0082aac0eb`. The candidate is `97e5acfb7b8eefde1ce07d703fc4849d6d36e37c`, whose immediate Git parent differs from the control only in a Cargo test. Both images report the same full source-version stamp and used the same PGO profile, 239 independently checked external compiler inputs and 335 native link files. The implementation obtains the real root `profile` table from the parsed document, then separately parses the remaining text and accepts the shorter fingerprint only for a suffix consisting entirely of profiles. The fixture exercises resolution reuse separately from profile application and build-script invalidation. [Exact implementation and tests](candidate.patch) · [Product, compiler and stock Wild hashes](subjects.json).

## Native results

Each row ran on the parent and the candidate in both the original run and the independent replay. “Full” means rustc compiled the build script and the main executable, the build script ran, and both links went through GCC, collect2 and stock Wild. “Main” means the build script ran, rustc compiled the main executable, and stock Wild linked it. “None” means no source compile, build-script execution or native link. Cargo’s cache result refers only to the dependency resolution.

| Stage | Parent / candidate cache | Native work per arm | Observed result |
| --- | --- | --- | --- |
| 01, original seed | miss / miss | Full | `true 17` |
| 02, unchanged | hit / hit | None | `true 17` |
| 03, change unused profile | miss / hit | Main | `true 17` |
| 04, restore unused profile | miss / hit | Main | `true 17` |
| 05, turn off dev debug assertions | miss / hit | Full | `false 17`, changed executable |
| 06, change only raw comment value | miss / hit | Main | `false 29`, changed executable |
| 07, unchanged | hit / hit | None | Same edited executable |
| 08, independently empty target, shared directory and Cargo home | miss / miss | Full | Byte-identical edited executable, `false 29` |
| 09, request nonexistent profile | hit / hit | None | Cargo 101, undefined profile |
| 10, unmatched package override | miss / hit | Main | Identical warning and `false 29` |
| 11 and 12, add path dependency after or before profiles | miss / miss | None | Both Cargo 101, identical `--locked` error and help |
| 13, duplicate profile header | miss / miss | None | Cargo 101 at Cargo.toml line 26, column 10 |
| 14, invalid optimization level | miss / miss | None | Cargo 101 at Cargo.toml line 24, column 13 |
| 15, request missing feature after a fake header in a multiline string | miss / miss | None | Cargo 101, undeclared feature |
| 16, actually declare that feature | miss / miss | Full | Feature set contains `new`, `false 29` |
| 17, malformed lockfile | miss / miss | None | Cargo 101, unclosed array at line 1, column 12 |
| 18, restore original manifest and lockfile | miss / miss | Full | Original executable, `true 17` |
| 19, unchanged recovery | hit / hit | None | Original executable, `true 17` |

On each arm, per run, actual kernel execs showed nine main compiles, five build-script compiles, eight other rustc processes, nine build-script executions and 14 each of GCC, collect2 and stock Wild. They also showed 19 Rustup Cargo proxy and 19 selected Cargo execs. All seven expected errors occurred before compiler or linker work. The kernel parser joins split and resumed execs by PID. All 444 successful execs in these two captures occupied complete lines. Setup calls for `cargo -Vv` and `generate-lockfile` preceded the 19 recorded build stages on each arm.

The public projection retains the actual Cargo JSON text, diagnostics, marker values, roles, source digests and raw stream hashes. The only path redaction in the streams is the private arena prefix. Exact user-facing stderr compared equal across arms and runs after removing only Cargo’s timestamped resolver debug records and its reported elapsed time. Full error bodies, spans, help and warnings remain. Successful JSON differed within each run only in the build-script filename and its `out_dir`. Those fields contain a different physical `v2-…` per Cargo image. The verifier allows one fixed literal namespace per arm only in those two typed fields and preserves their suffixes. The public data includes the raw namespace strings. The workspace ID also changed with the independent replay’s absolute path. [Raw file digests](raw-file-index.json.gz) · [Projected native evidence](evidence.json.gz).

The original driver saved the observed marker text, hashes of the manifest, lockfile and ELF, and the printed runtime value. The replay additionally retained the actual manifest, lockfile, marker bytes, executable stdout bytes and four physical ELF files. It reused the same literal work path across its two arms and started each with an empty target and shared store. For stage 08 it moved away both stores and the Cargo home before the compile. The warm and clean edited ELF in all four arms was SHA-256 `d435949a102e29c1cda271e85af819969264db3ccf19b057088b5a6c9bd23cb3`, 434,152 bytes. The original and recovered ELF was `0c039b2901d9fba755d31ee3a6e080426cf37e21608f06286f336daa0e9602ee`.

## Verify or replay

From this directory with Python 3.11 or newer, verify the recorded results with

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py --self-test
```

To repeat the actual qualification, use Linux x86-64 with strace, rustup proxies and the three supplied input paths. Use two new absolute directories with enough free space for the fixture. Choose the free-space reserve for the local host. The replay retains both finished private workspaces, the original and clean stores within each, all raw stream/trace files and the distinct actual ELF bytes. The independent observer allows only the enrolled Cargo, compiler driver and Wild. During packaging the following sequence was executed with both authentic release-profile PGO Cargos and an independently read copy of the raw results.

```sh
CTRL=/path/to/control/cargo
CAND=/path/to/candidate/cargo
SDK=/path/to/qualified/ohm/sdk
WORK=/path/to/new-work
OUT=/path/to/new-evidence
: "${MIN_FREE_GIB:?set the required free-space reserve on your selected filesystems}"
python3 -IB replay.py --control "$CTRL" --candidate "$CAND" --sdk "$SDK" \
  --work "$WORK" --out "$OUT" --reserve-gib "$MIN_FREE_GIB"
python3 -IB verify.py --self-test --replay "$OUT" --sdk "$SDK"
```

The replay invokes `cargo +ohm build -p profile_probe --locked --offline --message-format=json` with optional arguments only for the specified profile/feature checks. It enables resolver debug logging to distinguish hits from misses. No correctness claim here depends on the duration of those instrumented commands. The optional raw verifier reopens the output files, source inputs, marker and executable bodies. Nine adversarial modifications check the refusal paths, including a changed span, lost native link, wrong clean ELF, wrong stdout, hidden dependency, unrelated target name, corrupted marker, truncated error and altered raw input.

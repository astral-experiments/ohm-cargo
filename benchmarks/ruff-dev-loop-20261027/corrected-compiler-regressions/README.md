# Independent Rlib and downstream caller validation

The compiler under test is the release-matched Linux stage-2 PGO/BOLT compiler, commit `3a9e8ee19f74e4d0860da3ed60f9bb663332ec19`, with driver SHA-256 `3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2`. This Linux x86-64 run used the actual published Ohm 1.99.0-14 Cargo, SHA-256 `9be48c4b02669047975662348a3f134d0abcd247d70d13c55ab024f806320590`, and the matching Rust frontend and standard library. The process namespace binds the selected driver read-only onto the frontend’s resolved library path. `subject.json` and `subject/toolchain.json` record the exact executable digests. `release-build-source-sha256.json` records the original retained release source hash and the candidate source hash for each overlaid compiler file.

PR #233 head `66815c41574c8c597fa06af78a38c4c40ca30a84` adjusts formatting and one filename in the run-make test fixture after the compiler build. Its entire Git `compiler` tree has the same object ID `9e52c043880793c40fedf3eb137a231479d9adba` as the compiled source. `pr-head.json` records both tree IDs and the affected test paths.

All 12 semantic cases passed in both the edited and restored states. Each of the 24 warm-versus-cold comparisons produced the same complete Cargo-built caller ELF, the same standalone caller ELF, and the same output from both programs. Each intentionally invalid standalone source produced both expected error codes and the same primary/secondary source spans, labels, and notes as its fully clean reference. The harness issued 84 ordinary Cargo build commands and 96 independent rustc compilations. The test graphs have only local crates and no registry dependencies.

| Cases | Compiler behavior being verified |
| --- | --- |
| File enablement, private associated type edit and their combination | A private sibling can move the public module’s serialized file ordinal. A separate type-only edit exercises a safe library cutoff. |
| Byte offset, newline and 256-column shift | A reexported definition can change byte location independently of its rendered line or column. |
| Extra private expansion | A public type keeps its stable macro expansion while the raw ordinal changes. |
| File-table shrink | Disabling nine private sibling files shrinks the source table beneath a previously published foreign span. |
| Foreign and local expansion shrink | A leaf or intermediate adds/removes a preceding private macro while a second library reexports both public types. |
| Foreign and local expansion disappearance | The public struct retains its stable declaration identity and its old expansion hash is physically absent. Cargo must rebuild the intermediates that reference it. |

`subject/physical-expansions.json` verifies the raw declaration and expansion tables from the clean original and modified producer artifacts. A stable expansion can move across raw indices. The accepted warm intermediate metadata can retain its earlier index hint. The direct standalone callers above validate its current meaning. Raw Rlib and metadata digests are recorded separately for every package.

The three supplied shrinking-table controls reproduce on the shipped unmodified release. After the change, both its incremental Cargo caller and an entirely fresh direct rustc caller against the retained libraries crash. Each form succeeds when the identical sources are compiled using a distinct empty target and shared build directory. The released-control directory retains those failures.

Two supplemental Cargo graphs test an ordinary bridge built with a genuine package-profile opt-out, `[profile.dev.package.review_bridge] rustflags = ["-Zpublic-api-hash=no"]`. The recorded incoming compiler flags show the producer continuing to produce a public hash. Its private edit moves a raw definition index while preserving that hash and Cargo fully rebuilds the source-available bridge. Each genuine caller edit and restoration matches the independent empty-target executable and output. `ordinary-bridge/observations.json` contains the 14 additional Cargo runs. To reproduce them, pass the same compiler and Cargo paths to `ordinary_bridge.py` and a separate empty output directory. The compiler-argument wrapper in each suite only records invocations.

The three-crate upgrade fixture primes the same absolute target and shared build directories with the previous #233 compiler, commit `8d8897ff9a15b50de615420827da6c0752dd9121` and driver SHA-256 `55e123a9e87f16a449d260ab65449eab743cd30ba356a7f10ffdd1fa6f8a2484`. It uses a Cargo profile that explicitly opts all units out of public hashing. Without changing source, Cargo, rustc frontend, compiler version, standard library or rustup paths, it substitutes the corrected driver at the same resolved name. Traced native Cargo builds compiled three units on the old compiler, zero on a repeat, three in a new context immediately after the upgrade and zero on the next repeat. The old and new libraries identify their different metadata writers. All executables printed `17`, and the upgraded executable matched a separate empty-target build byte for byte. The upgrade harness uses `strace` on ordinary Cargo commands with no compiler wrapper. `upgrade/observations.json` contains all five builds, their contexts and compiler invocations. Run `upgrade.py` with the same interface as `verify.py`, the old driver under `--old-driver`, and a new output directory to replay the upgrade.

## Reproduction

Run `python3 check_saved.py` in this directory to verify every included file and reconstruct the reported comparisons from the saved data.

Provide a matching rustup home with `toolchains/ohm` resolving to the test sysroot, the candidate compiler driver and the shipped Cargo binary. Linux `bwrap` and `taskset` are required. Choose an allowed CPU list for the machine. The test uses a new output directory for each case and separate empty target/build directories for each clean reference.

```sh
python3 verify.py --sysroot "$TEST_SYSROOT" --rustup "$TEST_RUSTUP_HOME" \
  --cargo "$RELEASE_CARGO" --driver "$SUBJECT_DRIVER" --out "$OUT" --cpu 0-3
python3 report.py "$OUT" --must-pass
python3 expansion_tables.py "$OUT"
```

`subject/observations.json.gz` contains the raw program results and structured diagnostics. The compressed command archive holds every captured rustc argument vector, Cargo JSON message, ordinary terminal output and standalone run from all five warm stages and both clean references per case. The controls measure compiler correctness.

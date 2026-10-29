# Ruff native ready-order correctness

Two release-profile Cargo builds ran the same workspace test compilation on Linux, using Ruff `93526150df078af7dd8fc4226cdcc469539d2001` and the published Ohm 1.99.0-18 Rust compiler and Wild linker. Control A uses Cargo `235f9228651b`. Candidate B uses `4b0751af97bf`. The qualification retained six native runs per arm. Its registered comparisons and inventories contain no timing samples. [Registered protocol](https://github.com/astral-sh/ohm-cargo/tree/5fe1aa73f40406042785f97bf228460d2926b9c8/benchmarks/ruff-dev-loop-20261027/rc19-native-queue-plan)

Each arm built the original source, removed the end-of-cell clamp in `crates/ty_server/src/document/range.rs`, repeated the edited build, restored the clamp, and repeated the original build. A separate empty target and shared build directory then compiled the edited workspace. All six commands ran `cargo +ohm test --workspace --no-run --locked --offline -j8 --message-format=json`. The worker checked the working tree, the Cargo image and both native drivers before each native census.

| Phase in each arm | Cargo artifacts | Fresh | Full rustc | Link-only rustc | Actual Wild | Enrolled ELFs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original, edited repeat and final original repeat | 619 | 563 | 1 | 50 | 50 | 50 |
| Edit and restoration | 619 | 559 | 12 | 43 | 52 | 52 |
| Edited source from empty products | 619 | 0 | 623 | 0 | 188 | 52 |

Every run listed the same 200 `ty_server:e2e` tests. The two targeted selectors, `notebook::hover_past_end_of_cell` and `notebook::inlay_hints_range_past_end_of_cell`, passed with the clamp. Without it they exited 101 at the expected assertions. Both warm edited builds and their independently empty builds produced the complete e2e ELF `d76ef359714fc4339f053598978ec5464829f7d09adb24cdfd6defcae3fb56e8`. The original and restored e2e ELF was `be6b9375b66036f898876d7f55d745c7ea11d028f7b106c31a273c26e2cdcef7`. The individual test processes can produce differing stdout and stderr bytes. Each selector record retains its own hashes and exit status.

## Reproduce the comparisons

Run these commands from this directory on Linux with Python 3.11 or newer.

```sh
sha256sum --check --quiet SHA256SUMS
python3 -IB verify.py
python3 -IB negative-controls.py
```

The twelve phase files contain 612 observations of registered native products. Each records the output basename, a SHA-256 of its exact relative logical output pathname, size, SHA-256 of the complete ELF, GNU build ID, the section-header entry size of `.rodata`, and a SHA-256 over the complete ELF with those two fields zeroed. The two arms were compared at each of six corresponding phases. In each arm, both edited warm phases were compared to the clean edited run, and both restored original phases were compared to the original. Comparisons use the intersection of the original output paths from each phase, including all 52 registered products when both phases contain 52. Every differing raw digest remains in `comparisons.json`.

The original on-host admission file is included verbatim, and its fourteen comparison records are checked against the independent replay. The original reader, `elf.py`, takes a real ELF path. The verifier exercises it on a copy of an independent system ELF, changes the two admitted fields, and separately changes executable code. Raw benchmark binary payloads remain in the retained private stores. A reader of this packet can reproduce the recorded field-wise comparisons without downloading those stores and can use the same decoder on original files if available. `provenance.json` binds the original raw result, native execution, Cargo stdout and stderr, complete comparison certificate, and tool images to SHA-256. The product rosters, phase outputs and compiler-argument multisets are independent of process scheduling order. The stable native argument commitment retains all literal persistent arguments, the positions of the three temporary roles, and the observed temporary contents.

The cold-native supplement accounts for every successful Wild process, including unregistered helper DSOs and build-script executables. It matches the actual `-o` argument to its full recorded path, which distinguishes 46 outputs sharing the basename `build_script_build`. The hashes describe files held after the complete command. The phase summaries separately identify the 52 products covered by the prospective cross-arm ELF contract. The two clean builds saw 44 GCC and eight collect2 configure probes exit 1 each. Every Wild exited 0, and both full Cargo commands exited 0.

## Preparation history

The first attempt stopped before invoking Cargo because the root directory appeared owned by an unmapped user. The admitted namespaces ran as ordinary uid 1000, with a full uid map and root-owned top-level ancestors. A second mount layout exposed underlying empty directories at the two expected warmed-store paths. It produced a real 619-artifact cold build and failed the warm expectation. A third attempt to bind across mount namespaces returned `EINVAL` before invoking Cargo. The corrected layout entered the sealed donor's mount namespace, created a private mount tree, and verified the byte inventories, device and inode identities of the actual lower stores before launch.

An initial private source copy retained the source bytes and modification times but changed the order returned by directory enumeration. Equal-timestamp `Cargo.toml` and `build.rs` exchanged precedence in Cargo's implicit package watch. This changed the order of the real `zipped_typeshed.zip` from Ruff's build script. The 819 uncompressed names and payloads agreed as an unordered collection, but the first entry changed from `source_commit.txt` to `LICENSE`. This attempt produced 548 fresh artifacts and 58 native links. Matching all 64 relevant directory orders in the independent sources restored the original ZIP and the admitted 563-fresh plateau. The cold sources had their own 772 regular files, the same typed contents, and the same ordered directory entries. `setup.json` preserves the original rejection and source-check commitments.

An extra repeat of the published toolchain during preliminary donor preparation once produced a different complete e2e digest. The original, restored and final donor reads matched. The two independently enrolled Cargo builds and their observed qualified phase sequences are reported individually above.

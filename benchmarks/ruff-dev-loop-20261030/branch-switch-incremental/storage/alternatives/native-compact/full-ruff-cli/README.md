# Allocated storage for branch returns on the full Ruff CLI

One installation per option built the complete Ruff executable, beginning with empty Cargo target and build directories, then switching A → B → A → B and repeating B unchanged. Two further installations each built B from an independently empty graph. One eagerly sampled series accompanies each of the 12 real Cargo commands.

Both modes used the same source-built Linux compiler at `8ea2252344ba85e7406f4f04f979053e2bd191b1`, the same source-built Cargo at `2d44bd4a`, and the stock Wild binary with SHA-256 `0d6335808b647d499f3d74993b602e64ff0625206c809bf4913c487eea380cd5`. The option-off environment omitted rustflags. The option-on environment contained `CARGO_ENCODED_RUSTFLAGS=-Zohm-branch-cache=yes`. The complete per-installation 57-role inventories include device, inode, size, modification and change times, and SHA-256. Those values agree across both modes and independent clean installations.

After the unchanged final B, the opt-in retained 264.8 MiB more across both Cargo directories (+11.5%). The largest observed allocation over each complete five-command history was 2,837.7 MiB off and 3,123.5 MiB on. These are physical-storage observations from one same-host sequence per option. Separate performance studies measure speed.

### Settled target and build allocation

| Phase | Off MiB | On MiB | Difference MiB | Change |
|---|---:|---:|---:|---:|
| empty-A | 2,304.5 | 2,304.5 | -0.0 | -0.0% |
| first-B | 2,411.5 | 2,906.7 | 495.2 | +20.5% |
| return-A | 2,514.3 | 2,563.2 | 48.9 | +1.9% |
| return-B | 2,305.9 | 2,570.7 | 264.8 | +11.5% |
| unchanged-B | 2,305.9 | 2,570.7 | 264.8 | +11.5% |

### Settled allocation named only inside incremental directories

| Phase | Off MiB | On MiB | Difference MiB | Change |
|---|---:|---:|---:|---:|
| empty-A | 997.3 | 997.3 | -0.0 | -0.0% |
| first-B | 1,104.7 | 1,599.9 | 495.2 | +44.8% |
| return-A | 1,207.1 | 1,256.1 | 49.0 | +4.1% |
| return-B | 999.0 | 1,263.9 | 264.8 | +26.5% |
| unchanged-B | 999.0 | 1,263.9 | 264.8 | +26.5% |

The projection also gives the inclusive incremental total and the incremental inodes with at least one nonincremental alias. Each complete total charges a device/inode pair once even when several filesystem names refer to it. Two independent no-follow directory traversals had to match, including their path and inode ledger digest. The output superblock allocation also had to match the complete settled census before and after each command.

### Highest observed allocation during each Cargo command

| Phase | Off MiB | On MiB | Difference MiB | Change |
|---|---:|---:|---:|---:|
| empty-A | 2,304.5 | 2,304.5 | -0.0 | -0.0% |
| first-B | 2,690.7 | 3,123.5 | 432.8 | +16.1% |
| return-A | 2,837.7 | 3,098.8 | 261.1 | +9.2% |
| return-B | 2,674.0 | 3,123.4 | 449.5 | +16.8% |
| unchanged-B | 2,305.9 | 2,570.7 | 264.8 | +11.5% |

A dedicated 10 GiB tmpfs held only the target and build directories, preserving cross-directory hard links. A separate 6 GiB tmpfs held Cargo home, the source checkout, Git state, and temporary files. Compiler and linker inputs were read-only. The sampler called `fstatvfs` on the output device before launching Cargo, nominally every 10 ms until the traced process exited, and once immediately afterwards. Across all commands, median sample gaps ranged from 10.148 to 10.177 ms. The largest observed gap was 95.384 ms. A short-lived allocation between samples can exceed the reported maximum. Each named file in `samples/` contains monotonic relative nanoseconds and physically allocated bytes. Filesystems with different block or metadata accounting can yield different installed sizes.

### Native and binary controls

A is Ruff `b5dba861cc38e3f7fb4524c9ceba3e01a474ea13` and B is `7b13f01ba1569887a25670820764b24c206da8e5`, the 169-path change in #28335. Each command used the full 375-artifact graph in its historical source tree. The exact command was `cargo +ohm build -p ruff --bin ruff --locked --offline -j4 --message-format=json`. Cold commands performed 379 crate compiler invocations (including four real autocfg compiler probes), ran 37 build scripts and launched the stock linker 69 times. Each dirty switch ran 20 rustcs, one build script and one stock linker. Each unchanged B ran zero compilers or linkers.

Every visit ran the produced Ruff binary. It verified version 0.16.7 and the exact active Git commit, clean input, the real E711 diagnostic, corrected bytes from an unsafe fix, a clean recheck, and invalid syntax. A separately compiled native consumer linked the actual AST and parser and checked a valid and invalid source with `Expr=64` on A and `Expr=56` on B. Within each flag setting every same-source visit had to reproduce both full hashes and the exact successful/failing transcripts, including each independently empty B build. Raw native/source and archive identities remain in `observations.json`.

On A, The complete Ruff ELF differed across options and the predeclared debug-directory-only explanation did not establish byte equivalence. The offline record preserves the raw diagnostic SHA and both actual executable hashes. The standalone native consumer bytes matched across options.

On B, The complete Ruff ELF differed across options and the predeclared debug-directory-only explanation did not establish byte equivalence. The offline record preserves the raw diagnostic SHA and both actual executable hashes. The standalone native consumer bytes matched across options.

### Reopen the data

From this directory, run the following commands. The verifier re-reads every compressed sampler stream, recomputes all changes, and tests mutations of the native counts, artifacts, aliases, filesystem identity and maximum sample.

```sh
sha256sum -c SHA256SUMS
python3 -IB verify.py observations.json
```

For a new local observation, use `python3 -IB measure.py --help`. This smaller command runs a single ordinary Ruff build and the same two-pass storage census. Provide an already checked-out historical Ruff source, a compatible Ohm SDK and an exclusive Linux tmpfs with two ordinary-user-owned subdirectories named `products` and `shared`. Keep the observation directory and source on separate devices from the target/build tmpfs. Use the same paths for each visit, and independently empty both output directories between installations. The archived experiment also performed the per-thread native trace and CLI/reader controls described above. The standalone measurement entry point alone does not reproduce those controls.

### Independent cold references and the original artifact gate

The two alternating histories completed under the original registration. The independently empty B controls were admitted separately after HOME fell below the original 145 GiB entry condition. The histories, checkout paths, target/build 10 GiB output device, fixed tool inodes, memory and live filesystem guards remained in force. Each control used a separate 180 MiB receipt volume and streamed its complete archive onto durable storage. The original unscored controller recorded its actual HOME entry refusal and performed zero independent B work. The first off-control export encountered a read-only bind alias, and its first follow-up readback unnecessarily assumed at least 101 archive members. The second reader reopened the full affirmative index and all 51 actual members of the already-completed control, including the genuine native and provider receipts. It then admitted the sole remaining on-control using the same native worker and an explicitly writable, inode-checked export directory. Each mode executed exactly one independent cold B native build. Byte counts and failure commitments are in `separate_controls`.

The original predetermined cross-option full-binary gate rejected both branches. Raw on and off executables differ. The separately registered ELF and provider audit accepted only the one actual Cargo-emitted jemalloc build-directory component, in the same workspace namespace. It compared each independently settled archive and checked the executable without modifying it. The source-specific results below keep the original raw decision.

- Branch A yielded `d95086669c064830ea29ee00716452d7ec0f46f1a67a6bfd0c5cbf6d5ed087d4` off and `94410f889246772c4dee12b76ce9b9c39e65d7598a03dae308dee0f3a3b629b3` on. All raw bytes outside `.debug_info`, `.debug_macro`, `.debug_str`, `.note.gnu.build-id` matched, including every executable section. All four loadable segments matched with only the 32-byte build ID masked, and the same single registered path accounted for the complete decoded DWARF info (15,551,948 lines) and macro (68,285 lines).

- Branch B yielded `1225f6114456e0f4611236bf46f3f44db6925193c40e8a74591f191452f2d0f7` off and `71d98c7c8c2f9790baf78b3bf169bafcd659698341e1e95db870f699f7bbf1ad` on. All raw bytes outside `.debug_info`, `.debug_macro`, `.debug_str`, `.note.gnu.build-id` matched, including every executable section. All four loadable segments matched with only the 32-byte build ID masked, and the same single registered path accounted for the complete decoded DWARF info (15,528,403 lines) and macro (68,285 lines).

The archive reader opened the authentic `libjemalloc_pic.a`, Rust jemalloc library archives, and both metadata outputs from each empty B build. It decoded every GNU archive member, including symbols and long names.

- `jemalloc_pic.a` was raw different. The parser found 0 changed member names, 0 changed headers or pads, 62 other changed payloads, 0 objects with changed executable sections, and 0 objects with changed allocated sections. Full per-member hashes and any unresolved changes are in `provider-members.json.gz`.

- `tikv_jemalloc_sys.rlib` was raw different. The parser found 1 changed member names, 0 changed headers or pads, 65 other changed payloads, 0 objects with changed executable sections, and 0 objects with changed allocated sections. Full per-member hashes and any unresolved changes are in `provider-members.json.gz`.

- `tikv_jemalloc_sys.rmeta` was raw different. The parser found 0 changed member names, 0 changed headers or pads, 1 other changed payloads, 0 objects with changed executable sections, and 0 objects with changed allocated sections. Full per-member hashes and any unresolved changes are in `provider-members.json.gz`.

- `tikv_jemallocator.rlib` was raw different. The parser found 1 changed member names, 0 changed headers or pads, 3 other changed payloads, 0 objects with changed executable sections, and 0 objects with changed allocated sections. Full per-member hashes and any unresolved changes are in `provider-members.json.gz`.

- `tikv_jemallocator.rmeta` was raw different. The parser found 0 changed member names, 0 changed headers or pads, 1 other changed payloads, 0 objects with changed executable sections, and 0 objects with changed allocated sections. Full per-member hashes and any unresolved changes are in `provider-members.json.gz`.

### Which checkout was newest

The original option-on physical argv and incremental tables independently identify the same 20 producer units for each switch. The full compiler arguments, settled tables and terminal hashes are committed for every visit. The portable projection names each crate, metadata disambiguator, logical incremental directory and every prior/new session timestamp, checkout key, table name, allocation, file size and alias count used in this comparison.

The first A compiled each unit with no earlier finalized session and left raw tables. Across all 60 actual subsequent producer invocations, the immediately preceding observed finalized session belonged to the other checkout and each newly published session contained packed tables. The 8ea rule (any retained other checkout) and the newer source rule (the newest eligible session belongs to the other checkout) therefore select packing at the same 60 sites. On the final unchanged B the two stored checkouts remained and B was newest. Cargo launched no rustc, so neither rule executed. This inference covers only the actual alternating sequence and its measured 8ea output. The study did not run the newer compiler or measure that compiler's storage.

The seven CLI conditions can be exercised against a locally built executable with `python3 -IB cli-controls.py --binary PATH_TO_RUFF --repository RUFF_CHECKOUT --output NEW_DIRECTORY`. It writes all native stdout, stderr and hash commitments.

Run `python3 -IB verify-checkouts.py observations.json` to reopen this decision projection. It derives the Git label keys and session ordering independently from the retained directory names and checks raw versus compressed table names against all observed stages. The extractor `decisions.py` accepts an explicit evidence root for access to the privately retained original records. No private raw export is required to verify the public projection.

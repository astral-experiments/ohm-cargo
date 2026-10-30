# Retained object isolation and the cost of copying on a real Ruff build

The Rust repair isolated saved native inputs from writable incremental-codegen files. This packet measures actual copied bytes and separately tests what happens when existing targets contain a stale executable. The baseline was Ohm Rust `ad005f99d0b51fd62b5c237bc13b31b371a1686e`, the repair its direct child `05efba7a06f5bb71d1efb4b86805800f8b810779`. The 119 bootstrap compiler argument vectors, 53 standard libraries and actual rustc frontend matched. Both Ruff arms used release-source Cargo `7277e6cdaba44c43294a07c0661fc8e69fd8e3e7` and the same shipped Wild. No compiler or wall-time performance inference is made from these work counts.

### Ordinary Ruff

Ruff `93526150df078af7dd8fc4226cdcc469539d2001` was trained separately for each compiler. The production edit/restoration was taken from `11a6493c944a9b78ebc72fa0b792ab706eae093a` in `crates/ruff_db/src/system/memory_fs.rs`. Cargo ran `cargo +ohm test --lib --no-run --locked --offline -p ruff_db -j4 --message-format=json`. Three independently executed memory-filesystem tests and the exact 130-name inventory bound native behavior. The historical pre-edit source produced exits 101/0/0, the edit 0/0/0. The entire edited test ELF was identical between both compilers, the warmed output, the repaired output and an independently empty build. The complete restored original ELF was identical to cold.

| Cargo phase | Repaired compiler's physical saved-object copies | Bytes | Origin of those inputs |
| --- | ---: | ---: | --- |
| Empty original | 256 | 19,484,840 | 256 newly generated |
| Historical edit | 256 | 19,484,400 | 6 newly generated, 250 restored |
| Unchanged edited follow-up | 256 | 19,484,400 | 256 restored |
| Restore original | 256 | 19,484,840 | 6 newly generated, 250 restored |
| Invalid source | 0 | 0 | Cargo 101, compiled code never reached this writer |
| Repair | 256 | 19,484,400 | 256 restored |

Every successful copy was joined to a real Linux linkat direction, copy_file_range through EOF, final file length and same-thread rename from a unique temporary file. The parent had zero such copies. On unchanged, all 256 corresponding old files already had nlink=1 and equal logical-CGU lengths, but each destination used a different seven-character compiler-session suffix. No full destination pathname was present beforehand. The 2,552-byte allocator shim was outside the 256 copies. Previous individual object content hashes were not recorded; the object lengths, paths, native calls and complete consumer ELFs are available separately. A disposable FICLONE on the same ext4 target filesystem rejected both empty and equal-content destinations with ENOTSUP. Results are logical transferred bytes, not physical media traffic. The unchanged command here still executed 11 full compiler processes and two real Wilds in both arms. The edit used 11 full compilers under W and 12 under E, reversed on repair. This does not establish a causal scheduling difference.

### Upgrade and cache behavior

The compact fixture seeded a wrong existing binary using an authentic same-length object from a normal alternative Rust build. Its root source requested 17 and the edited dependency requested 11; the affected compiler produced 29/11 on a dirty build and its repeat. After a complete signed `1.99.0-19` → candidate E/release-Cargo upgrade, the first unchanged command rebuilt both units and linked once, producing 17/11 byte-for-byte equal to a new empty build. Both supported split configurations passed. A subsequent real source edit produced 17/13, and its fresh repeat executed zero compilers and zero linkers.

Replacing only the compiler driver at unchanged `rustc -vV` gave two different results. With `CARGO_BUILD_BUILD_DIR` selecting the store, both tested Cargo binaries rebuilt and repaired on first unchanged. With `[build].build-dir` in a config file, both returned the prior wrong binary on the true fresh command; no process opened the old compiler cache. A subsequent real dependency edit corrected it and matched independent empty. E’s independently trained targets kept correct results for four valid/malformed × in-place/rename mutations of their detached saved object.

Separately, 20 ordinary Cargo commands tested the physical incremental-file headers in both directions, 7→8 and 8→7, with identical native version stamps and paths. A true fresh command left the prior header untouched. On the subsequent genuine source edit, the compiler actually opened the prior dep-graph.bin and work-products.bin via traced kernel hardlinks, wrote the other on-disk version and produced the exact independently empty program. A real unresolved name produced E0425 and Cargo 101, and the first repaired build matched empty. These checks cover the original repair only. Format 9 is a distinct experiment.

### Verification and independent reproduction

Run `python3 -IB verify.py --self-test` to verify the manifest, 16 completed Ruff phases, six upgrade layouts, both complete 10-command header transitions and six intentional corruptions. `reopen-ruff.py ORIGINAL_SWITCH_STUDY NEW_RESULT_JSON` reads the retained raw per-thread kernel trace for every succeeded and failed phase and reclassifies every saved-object operation. The private raw study contains the original executables and system paths and is not embedded here. The public subset includes each raw stream and phase hash. `header-migration.py INPUTS.json` recreates the 20 real header tests from private user-supplied SDKs on x86-64 Linux with strace, Bubblewrap, Python 3.11+ and rustup. Copy paths in `header-inputs.example.json` to a fresh work root with 48 GiB free and choose two complete, physically authenticated SDKs with the given compiler, Cargo and stock linker checksums. The script checks the two actual driver files before launching, retains all native traces/ELFs, and exits on mismatched headers or source verdicts.

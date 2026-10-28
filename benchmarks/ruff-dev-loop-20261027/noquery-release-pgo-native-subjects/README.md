# First-observer Cargo executable admission

This register fixes the original production-profile Cargo executables and their build inputs before future Ruff timings. It admits three source variants for independent native qualification. A is the corrected release-candidate baseline, Q probes the compiler in an extra process, and N reads a checksummed input-list record emitted by the producer. Each study still requires its own prospective workload, schedule, native checks and timing grant.

| Variant | Cargo source | Original executable SHA-256 |
| --- | --- | --- |
| A | `a0c7d08c898d3fdff992f2f431dec57d2486add2` | `0ad5c2e226484334a5818c4702ccdf59a46732fc3cbe312b2f87411284b77ba2` |
| Q | `97c04e448a136e8fd39948a00b095e53adf9876c` | `03c851e44a863bb0d2cb8c9a98df1eef33310c8f3fbc77cdbb48aee516e68400` |
| N | `b538e17473c6ed001c04f7026f8fe73f737b0246` | `d67c68ee27b3529c52d66022bf273df8a119353f0856deeebd9ff63b24ffadde` |

All five final release builds used the same physical dependency generation, including the initial warm build and an independent last A. Ordinary Cargo compiled both Cargo product units on every attempt. Their rustc arguments, 159 Rust input files across 80 external crates, and 404 files in the requested native link directories matched by SHA-256. The CLI's own Cargo library was rebuilt for each variant. The first attempt used independently copied build stores. Even with matching Rust arguments its 3–4 different standalone dependency metadata digests precluded a timing comparison. Those three executables remain separately recorded.

The first complete-file baseline check failed. The seed, measured A candidate, and repeat A all have distinct full SHA-256 digests. Each pair differs in 142 LLVM-generated numeric suffixes in the nonloaded ELF symbol string table and in its 32-byte GNU build ID. All 69,183 symbol addresses, sizes and bindings match, including 89 statically global and 53 local affected names. None of the affected names is exported by the dynamic symbol table. Checking the entire executable with only numeric LLVM suffixes and the build ID descriptor masked gives the same digest in all three cases. All actual measured subjects remain the original unmodified executables. `full-symbol-changes.json.gz` contains all 426 individual entries across the three original comparisons, including full names, symbol ordinals, sections, addresses and size.

The supporting Rust frontend and driver were frozen before these checks. Four source-and-driver combinations passed 16 ordinary Cargo runs. The native reader changed from 17 to 29 after an equal-size rewrite at identical inode and nanosecond timestamp. Both independently edited native outputs agreed, the repeat launched zero compilers and only Q ran an extra capability process. New Cargo with the older compiler correctly retrained from an incomplete first observation. The raw fingerprint, depfile, actual process stream and native output for every command are in `pinned-native-records.tar.gz`.

Run `python3 -B verify.py` and `sha256sum --quiet -c SHA256SUMS` in this directory. The unchanged raw build gate is recorded with exit 1. `registration.json` defines the separately disclosed admission for a future study. No Ruff wall or instruction outcomes are in this packet.

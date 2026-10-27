# A cached Rust reexport can retain a foreign source-file index

The witness uses ordinary Rust rlibs and a glob reexport. The leaf has one private optional source file before its public module. A one-word change enables that file. On published Ohm 1.99.0-14, the leaf retains its previous public hash, Cargo skips the intermediate rlib, and a genuine source edit in the caller triggers an unstable `module_children` fingerprint. The identical sources compile successfully with an empty target and a distinct empty shared build directory.

`reproduce.py` runs the fixture from `original/` with an installed 1.99.0-14 toolchain selected as `+ohm`. It uses ordinary Cargo without a wrapper, extra rustc flags, a cache snapshot, or a custom linker. It checks the release version and preserves the compiler messages, reported freshness, and output of the resulting program. Run `python3 reproduce.py /tmp/ohm-fresh-output`. Our additional process-recording runs used four local cores with a wrapper that records every compilation and specifies the matching sysroot. They cover the exact shipped release and the immediate parent of #232. Its driver was built using the existing matched PGO/BOLT procedure. Both use the same shipped Cargo.

| Producer edit | Shipped R14 | #232 parent |
| --- | --- | --- |
| Enable one private file, keep the private Iterator item type | Intermediate reused. Real caller edit ICEs. Empty-target build succeeds. | Same |
| Change only the private Iterator item type from u8 to i8 | Intermediate rebuilt. Caller succeeds. | Same |
| Enable that file and change the private Iterator item type | Intermediate rebuilt. Caller succeeds. | Same |

Each arm records the priming compilation, real leaf edit, real caller edit, and both source restorations. The edited and restored caller each have a separate cold reference. In `observations.json`, a true value beside a rustc child means that invocation used link-only mode. Cargo can report an intermediate as dirty even when it skips its compiler. The wrapper child roster distinguishes these outcomes. `toolchains.json` gives complete executable hashes.

The file-only failure predates both drafts. Draft #233’s broader hash cutoff additionally exposes the combined file-and-private-type edit. These controls do not qualify the performance of a repair.

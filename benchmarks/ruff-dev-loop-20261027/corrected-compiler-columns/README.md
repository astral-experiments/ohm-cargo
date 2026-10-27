# #233 source-column collisions and metadata-prefix reuse

Each compiler built twelve original and moved inputs per output mode, giving 48 real rustc producer invocations. The baseline is the original #233 release-built driver. The fixed driver contains the source-location guard. The source tree shared by the fix and the two test-only follow-ups is recorded in `source.json`.

| Source moved 256 columns | Old metadata-only | New metadata-only | Old native | New native | Independent consumer |
| --- | --- | --- | --- | --- | --- |
| Tracked function | Equal | Equal | Equal | Changed | Native function pointer reports 1 then 257 |
| Private method | Equal | Equal | Equal | Changed | E0624 definition note reports 19 then 275 in both modes |
| Exported macro | Equal | Equal | Equal | Changed | Native procedural-macro token reports 76 then 332 |

All twelve compiler, source and output combinations logged this prefix sequence. A cold compile fully encoded metadata; changing only a private integer reused the prefix; moving the source and changing that integer fully re-encoded metadata; a further private-integer change reused the new prefix. Each `*.stderr` contains the compiler's artifact notification and the applicable INFO prefix event. The release compiler also reports that requested DEBUG traces are disabled. The prefix event is emitted at INFO on these binaries.

Inputs reproduce the definitions, movement, flags and downstream observers from the repository's run-make test at 66815c4. Each source category has its own initially empty incremental directory. The exported-macro case omits earlier unrelated item/expression-macro definitions from the full run-make test. The recorded parent/fixed hashes compare pre-edit and post-edit states within the same source path. The private method's diagnostic columns are independently present in raw rustc JSON. The two successful runnable consumers record their printed integer in each per-invocation `result.json`.

## Replay

Run `python3 -B verify.py` after unpacking. It verifies all per-file checksums, raw compiler notifications, prefix events, diagnostics and source provenance without a Rust installation.

For an independent native replay, obtain both source-built release14 drivers, their matching common frontend/sysroot, and the matching Ohm Cargo. The driver hashes and release recipe hashes are under `drivers`. Run the following from the extracted directory.

```sh
python3 -B scripts/make-arm.py /tmp/old-home COMMON_SYSROOT OLD_DRIVER_DIR OHM_CARGO
python3 -B scripts/make-arm.py /tmp/new-home COMMON_SYSROOT FIXED_DRIVER_DIR OHM_CARGO
python3 -B scripts/column-collisions.py /tmp/new-result fixture /tmp/old-home /tmp/new-home
```

The replay takes its producer flags from `fixture/rmake.rs` and invokes `rustc +ohm` through the two private toolchain descriptors. It defaults to CPUs 4–5 and 6–7. `OHM_REVIEW_PARENT_CPUS` and `OHM_REVIEW_FIXED_CPUS` can select available Linux cores. Absolute artifact hashes may depend on compiler, source layout and output paths. The oracle is the within-run hash, prefix and consumer relation.

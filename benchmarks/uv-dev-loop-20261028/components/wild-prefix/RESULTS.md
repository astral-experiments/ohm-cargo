# ELF section-placement results against Ohm Wild #45

The frozen v2 patch is `a75c1cf2d966ddd1217e33f8879070afe4a9e20ce94d01465a8df109ca69b65c`. The production linker SHA-256 is `901b68fc9ca30975d837d45dcf1bdf743a6130ecef5e23d6aef44558b09bd7e1`, including when rebuilt at the end with the test-only patch. The parent is `a77381c04eb7ad9258cdd0475642815a2a1da711`. The change retains a borrowed string-table slice, two machine words per parsed ELF input on this target.

## Actual edited test compilation

The median eight-block reduction was **3.8727%** in total Wild instructions over the five emitted linker invocations in each `cargo test --no-run --locked --offline -j4`. The block effects ranged from 3.7394% to 3.9559%. Exact two-sided sign p = 0.0078125. The balanced assignment permutation p = 0.0285714. The fixture completed 32 commands and 160 Wild invocations and counted the main thread and every worker, while retaining its native Cargo jobserver. The command used the exact shipped rustc and Cargo rebuilt from unmodified release source. The rebuilt Cargo differs in bytes from the packaged Cargo. The hashes of all executables are in `actual/executables-sha256.txt`.

The actual-command output rule reads “Complete all eight blocks without early stopping for effect. Require precisely five known linked units and exit 0 per invocation. Retain link outputs content-addressed and all SHA-256 digests. Report all parity discrepancies including any shared parent nondeterminism.” Both arms produced the same set of full-file SHA-256s for 10 of 10 edit/unit combinations and 2 combinations had multiple observed hashes. The only multi-digest target was the 184 MB uv test harness on each edit. Each pair of variants differed in exactly 33 bytes, its 32-byte GNU build ID at [896, 928) and the low byte of its section-header index 11 `.rodata.sh_entsize` at offset 184003848 (8 or 0). The per-arm counts and full SHA-256s are in `actual/digest-counts.tsv`. `actual/byte-differences.json` records every differing byte range between full-file variants. All 160 Wild subprocesses emitted empty stderr apart from the profiler's record. The existing uv-keyring warnings and summary were identical in all 32 Cargo commands. `actual/diagnostics.json` records their text and frequencies.

## Reserved input shapes

| Captured original | Median saving | Pair range | Complete file SHA-256 |
| --- | ---: | ---: | --- |
| uv | 3.3845% | 3.3785–3.3900% | `f6ddfa61e2424483c36976e5b33f8b8bf7b3a16ae944182eae6ad8f6e498df8b` |
| uv-c84366b26c530121 | 0.1872% | 0.1762–0.1993% | `b425d4bd6926a39f77ec15ac0886146159ee4d20f3a70af5eb124445fee69128` |

All twenty outputs on each reserved input matched the complete true parent-emitted file from the separate equivalent source edit as well as the single-thread canonical result. Each ten-pair sign test gave p = 0.001953125 and the restricted permutation gave p = 0.00793651. Both linker stdout and stderr were empty on every replay before the instrumentation record.

## Three-arm pilot and fallback costs

| Input | Change in v1 instructions | Change in v2 instructions |
| --- | ---: | ---: |
| partial | +0.9003% | +0.2156% |
| data | -0.1202% | -0.4632% |
| script | +0.2585% | +0.0001% |
| new_uv_harness | -4.7912% | -5.0886% |

Changes are the paired median percentages relative to #45, with six observations of each of the three binaries for each fixture. Partial is a real 188-member uv-client archive linked with `-r --whole-archive`. Data is a regex-syntax object with 1,822 sections. Script applies a small explicit remapping to that same object. The pilot and its original criteria are in `pilot/summary.json` and `gate.json`. Every pilot command reproduced the parent output and diagnostics.

## Attribution and correctness

The release-build Callgrind capture from the original uv executable counted 6,652,070,551 parent instructions and 6,425,439,774 v2 instructions, 3.4069% fewer. `attribution.json` groups call edges from section resolution. Direct ELF name calls fell from 1,303,861 to 341,224 and direct rule hash lookups fell from 1,314,592 to 351,955. The two edges together account for 179,394,797 of the 226,630,777 fewer retired instructions, 79.16%. The ELF shortcut returns regular TEXT or Discard, while init/fini priority reads occur exclusively in the disjoint SortedSection outcome. Accordingly, zero full-name reads for priority calculation arise from a section already classified by the shortcut. Cases that request a full name on the fallback path reuse the saved result.

All 184 libwild unit tests, 35 focused ELF integration cases and the Mach-O-feature compile passed. The 21 synthetic comparisons covered prefix boundaries, default and custom placement, orphan modes, partial linking, alignment, missing terminators, out-of-range offsets and diagnostics. The orphan integration group used `-fcf-protection=none` for its GCC test inputs on this host, because its GNU BFD reference otherwise rejects the host's implicit CET note on the #45 parent as well.

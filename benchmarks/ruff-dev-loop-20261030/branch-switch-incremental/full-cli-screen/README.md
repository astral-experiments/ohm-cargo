# Whole Ruff CLI branch-return screen

Two historical Ruff checkouts were built with the same Cargo, standard library, LLVM and stock Wild. Each timing installation started empty, built original A, switched to feature B, returned to A, returned to B and repeated B. Only the ordinary Cargo builds on the two return visits were timed.

| Pair and order | Return | Parent elapsed | Guarded elapsed | Elapsed ratio | Parent CPU | Guarded CPU | CPU ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 (QP) | A | 82.647 s | 17.322 s | 4.771× | 283.224 s | 24.357 s | 11.628× |
| 1 (QP) | B | 82.234 s | 17.570 s | 4.680× | 279.641 s | 24.455 s | 11.435× |
| 2 (PQ) | A | 80.519 s | 17.326 s | 4.647× | 279.678 s | 24.199 s | 11.557× |
| 2 (PQ) | B | 84.518 s | 16.449 s | 5.138× | 286.377 s | 23.812 s | 12.027× |

Ratios divide the parent by the guarded result within each chronological pair. CPU sums the child user and system times. Git checkout ran outside the Cargo clock and has its own record for every return in `screen.json`. Two pairs constitute an initial screen. The report gives all observations and no population interval.

## Native behavior

The command was `cargo +ohm build -p ruff --bin ruff --locked --offline -j4 --message-format=json`. Revision A was `b5dba861cc38e3f7fb4524c9ceba3e01a474ea13` and B was `7b13f01ba1569887a25670820764b24c206da8e5`. They differ across 169 paths in Ruff #28335. The compilers were parent `7e71d3150938ff8ed82aca03416439d7e5b87ef3` and guarded `6b7f424ece4bc978ead5546b73e1b31d5ccb1e70` with common Cargo `2d44bd4aa68b9ba32cacb5a384ecc18fa5e7553c`.

Four independent native controls comprised 14 commands. Every empty build reported 375 typed units, 379 physical rustcs, 37 native build scripts and 69 stock Wild links. Both guarded and parent returns reported the same 20 dirty units. Native tracing recorded 20 full rustcs, a build script and the GCC, collect2 and stock Wild chain. The linker’s output and the executed CLI were the same inode. The unchanged native controls ran zero compilers or linkers. The timed commands used direct, unwrapped Cargo and have their own typed rosters and exact complete output checks.

Each branch return reproduced its own compiler’s entire independently empty CLI, including debug information and the GNU build ID. The CLI reported the physical branch’s commit SHA and passed the clean case, E711 line-two diagnostic, real unsafe fix, clean recheck and syntax rejection. An independently linked consumer observed a 64-byte Expr on A and a 56-byte Expr on B, with a valid parse and an invalid parse on both.

Across compilers, every instruction byte matched on both branches and each ELF had four matching LOAD segments after masking the enrolled 32-byte GNU build ID. All 94,177,808 remaining unmasked bytes on A and 94,056,598 on B matched literally. Complete decoding checked 15,551,948 and 15,528,403 debug-info lines respectively and 68,285 macro lines for each executable. The accepted path substitution was the one complete jemalloc build directory reported by Cargo. The only changed nonloaded sections were .debug_info, .debug_macro and .debug_str.

## Enrollment and storage

The first two admissions copied the physical SDK onto each private working filesystem. Cargo’s compiler-installation namespace changed, including between independent installations of identical compiler bytes. Both raw-ELF gates stopped before any timed command. The fixed installations instead read the same physically authenticated SDK files on every visit. The later HOME-backed acquisition passed all 14 native controls, then waited below its 145-GiB HOME entry requirement after a single unmatched guarded installation. Both calls from that unmatched arm were excluded. The chronology, observed physical floor and full raw completion commitment are in `clock-plan.json`.

The scored cohort made four new installations on four fixed CPU cores, with a fresh 18-GiB Linux tmpfs at the same visible Cargo source, target and shared paths each time. Complete source, SDK and previous raw branch products were checked again before each slot. Both data volumes were read-only. Normal kernel file caching remained enabled. Cargo’s stdout and stderr were non-terminal seekable files on the private working filesystem. The harness waited for actual process exit and recorded elapsed and CPU before copying the complete streams to a distinct private runtime volume. The published timings apply to this configuration.

For the separate full-target storage measurement, the parent’s combined target and shared build directory occupied 2,418,098,176 bytes after the final unchanged A visit. The guarded compiler occupied 3,513,303,040 bytes after the same visit, 45.29% more. The entire difference occurred in incremental inodes. That measurement used one independently trained installation per compiler and supplies no timing observations.

## Verification

Run `python3 -IB verify.py` beside the packet files. The Python 3.11+ verifier checks the complete portable manifest, distinguishes prior admissions from the four timed installations, independently recomputes all paired ratios and runs corruption controls. `python3 -IB verify.py --native-only` checks the 14-command earlier native evidence separately. `python3 -IB check_binary.py /path/to/ruff --compiler P --branch A` verifies the recorded complete ELF hash and runs the seven real CLI behavior checks on a retained executable. Substitute Q or B to select another enrolled binary.

The native raw evidence and independently timed raw evidence were streamed to a separate durable filesystem. Both compressed files and every archived file’s mode, length and content checksum were reopened against independently computed source ledgers. Each capsule includes every retained complete CLI and reader. The archive identities, native and timing readbacks are in `escrow.json`.

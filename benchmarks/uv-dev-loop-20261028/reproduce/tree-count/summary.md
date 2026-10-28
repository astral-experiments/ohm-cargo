# Edited whole-workload instruction experiment

**No admitted whole-workload instruction comparison.** The first native-versus-counted check admission failed. Sampling stopped before any held-out pairs or build and test pilots.

| Edited default workspace check | Cargo processes | rustc invocations | Wild invocations |
| --- | ---: | --- | ---: |
| Native baseline, D00 | 1 | `uv` library, `uv` binary, `uvx` binary | 0 |
| Native candidate, D00 | 1 | `uv` library, `uv` binary, `uvx` binary | 0 |
| Counted candidate, D01 | 1 | `uv` library | 0 |

All three runs reported `Checking uv v0.12.0` and completed successfully. Native `strace` independently verified exactly three launches of the released rustc in each arm. The exact rustc arguments show that the next edit skipped both binary compilations. The first edit introduced the comparison and string literal. The next changed only the literal. The pilot did not separate the effect of that edit history from the effect of instrumentation. Its single unpaired count cannot quantify a speedup.

The nested counter calibration passed on CPUs 16–23. The three role deltas were 1,599,955, 1,600,045 and 3,200,000 instructions, exactly 6.4 million in total as predicted. A corresponding increase in excluded pre-exec work changed every reported role count by zero. The linker-like role used two threads. All three executables validated the same inherited descriptor.

The scope was the sum of the original Cargo, rustc and Wild PIDs and their threads, with `--no-fork` on each Wild invocation. Compiler launchers, `cc`, `collect2`, other forked work and the kernel fall outside that sum. Both uv arms used the same released compiler. The failure does not alter the separately collected Cargo instruction, linker instruction or full-command elapsed-time observations.

The protocol is in `README.md`, `original-protocol.sha256` and `results/check/protocol.json`. The calibration records and known deltas are in `calibration/`. The three raw role and command receipts, the two native successful-exec censuses and per-PID strace files are in `results/check/pilot-*`. `results/exclusions.json` records the rejection. The archived source was verified byte-for-byte against the original uv revision after the run and the visible target slot was left vacant.

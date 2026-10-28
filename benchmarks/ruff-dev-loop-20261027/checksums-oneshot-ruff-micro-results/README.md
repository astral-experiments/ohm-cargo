# Standalone BLAKE3 checksum screen

These 12 balanced pairs used a single optimized helper containing both original and changed implementations of `Checksum::compute`. Each fresh process ran four sweeps of the same 1,238 Ruff source files. CPU 14, the ELF, its dependencies and the real descriptor transcripts were bound before any instruction count. [Source and decision rule](https://github.com/astral-sh/ohm-cargo/tree/32c4f9da05956359fbd8d660c712c846fd8ff01f/benchmarks/ruff-dev-loop-20261027/checksums-oneshot-ruff-source-plan). [Host and native admission](https://github.com/astral-sh/ohm-cargo/commit/51c1278c3c78411fad79333fca95d29e0028fa0a).

| Measurement | Value |
| --- | ---: |
| Median original instructions per four-sweep command | 180,940,282.0 |
| Median changed instructions per four-sweep command | 176,460,103.0 |
| Paired median reduction | +2.476% |
| 96.14% distribution-free median interval | [+2.475, +2.476]% |
| Median instructions saved per sweep | 1,120,051.5 |
| Lower instruction count | 12/12 pairs |
| Exact one-sided balanced randomization p | 0.0010823 |
| Registered screen passed | False |

Positive savings indicate fewer instructions. The eligibility rule required all four thresholds. Every PID reached a terminal instruction record. Both ordinary post-series commands reproduced the native output and the worker revalidated the source contents, identities and host binding. The measurements cover the isolated four-sweep process. Whole Cargo build time and Cargo instruction cost are outside this dataset.

`python3 -B verify.py` decodes all raw PID/thread records and both native outputs and computes the paired test independently. The original runner and analyzer are included.

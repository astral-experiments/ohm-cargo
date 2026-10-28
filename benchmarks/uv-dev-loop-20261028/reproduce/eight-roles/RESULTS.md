# All eight Ohm changes on edited uv test compilation

`cargo test --no-run --locked --offline -j8` compiled an edit to uv's private install-source logic. The endpoint sums original Cargo, rustc and Wild PIDs and all their threads. Baseline and candidate Cargo were separately profile-trained. Both used the exact shipped rustc. The candidate combined the Cargo and standard-library changes with both Wild changes.

| Independent cohort | Median instruction reduction | 99.22% rank interval | Wins | Exact sign p | Balanced-order p |
| --- | ---: | ---: | ---: | ---: | ---: |
| initial | 2.1335% | 1.9086% to 2.1757% | 8/8 | 0.0078125 | 0.02857143 |
| replica | 2.1351% | 1.8868% to 2.1590% | 8/8 | 0.0078125 | 0.02857143 |

Both cohorts passed every registered performance and comparability gate.

| Cohort | Arm | Cargo median | rustc median | Wild median | Total median |
| --- | --- | ---: | ---: | ---: | ---: |
| initial | base | 1,520,106,068.0 | 14,504,672,722.0 | 12,172,773,891.5 | 28,196,855,757.0 |
| initial | candidate | 1,481,250,222.5 | 14,507,329,734.5 | 11,605,785,221.5 | 27,594,055,262.0 |
| replica | base | 1,519,678,067.5 | 14,505,273,037.5 | 12,173,235,370.0 | 28,199,424,236.0 |
| replica | candidate | 1,481,385,536.5 | 14,505,685,344.0 | 11,606,879,771.0 | 27,593,468,704.5 |

Role and total medians are calculated independently. Both cohort estimates use the median of the eight same-source paired reductions.

## Workload and artifacts

Initial verified four native/count admission cells and 16 measured commands. Every command recompiled only uv and emitted 72 test executables. Its process roster contained one Cargo, six rustc and five Wild PIDs. Every linked output matched its full-file SHA-256 across arms for the same source. The original fixture passed restoration.

Replica verified four native/count admission cells and 16 measured commands. Every command recompiled only uv and emitted 72 test executables. Its process roster contained one Cargo, six rustc and five Wild PIDs. Every linked output matched its full-file SHA-256 across arms for the same source. The original fixture passed restoration.

The independent cohorts shared the pinned source location, immutable archived seed and binary identities. Each used its own new Cargo home, target snapshots, schedule and same-length source edits. Both admissions held all work and source bytes constant across four native/instrumented cells. Every post-command file hash and every counted thread receipt is retained.

Only the known 32-byte GNU build ID and one .rodata section-header entry-size byte were eligible to vary in the large test harness. The invariant-byte SHA-256 and field value were checked for each observation.

The selected-process sum excludes kernel execution, cc, collect2, wrapper processes and pre-exec work in forked children. Both arms used Wild --no-fork with the Cargo jobserver. Tests never executed. See reproduce.md for replay and verify.py for standalone recalculation.

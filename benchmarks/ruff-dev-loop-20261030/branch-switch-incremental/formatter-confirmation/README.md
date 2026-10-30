# Ruff formatter branch-switch confirmation

The registered two-direction 2× wall-time criterion passed across twelve counterbalanced installation pairs. The command built the ruff_python_formatter library-test executable on both sides of [Ruff #28335](https://github.com/astral-sh/ruff/pull/28335). All 24 ordinary installations and four separate native/correctness controls are included.

| Return | Parent median | Guarded median | Median paired wall ratio | Simultaneous interval | Pairs above 2× | Balanced randomization | Two-sided sign test against 2× |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 22.143 s | 5.285 s | 4.173× | 3.967–4.420× | 12/12 | 2/924 = 0.002165 | 0.000488 |
| B | 22.311 s | 5.321 s | 4.179× | 4.073–4.297× | 12/12 | 2/924 = 0.002165 | 0.000488 |

The ratios pair nearby installations before taking their median. The intervals use the second and eleventh sorted ratios for each direction. Their marginal coverage is 99.365%, which gives simultaneous coverage of at least 98.73% for the two prespecified directions. The randomization test uses the signed chronological log differences for all six-parent-first assignments. The sign test evaluates the 2× threshold separately.

| Phase | Wall median P → Q (s) | Whole CPU median P → Q (s) | Paired CPU ratio | Physical incremental median P → Q (MiB) |
| --- | ---: | ---: | ---: | ---: |
| empty-A | 100.158 → 99.240 | 354.548 → 351.603 | 1.017× | 298.77 → 298.77 |
| first-B | 21.781 → 21.615 | 63.073 → 62.710 | 1.006× | 326.98 → 539.20 |
| return-A | 22.143 → 5.285 | 63.241 → 5.831 | 10.894× | 353.70 → 542.63 |
| return-B | 22.311 → 5.321 | 63.657 → 5.863 | 10.801× | 299.57 → 545.38 |
| unchanged-B | 0.285 → 0.292 | 0.251 → 0.254 | 1.011× | 299.57 → 545.38 |

| Switch | Git median P → Q (ms) | Median paired wall ratio including Git |
| --- | ---: | ---: |
| first-B | 707.61 → 633.94 | 1.016× |
| return-A | 140.35 → 140.30 | 4.089× |
| return-B | 152.27 → 139.01 | 4.089× |

Both compilers launched the same four full rustc processes for ruff_db, ruff_python_ast, ruff_python_parser and ruff_python_formatter on every traced return. Each used one GCC driver, one collect2 and one stock Wild. The replay captured actual successful object creation requests. Counts below are distinct, named .rcgu.o destinations as observed through successful writable open calls with O_CREAT.

| Source | Parent pre/post CGU paths | Guarded pre/post CGU paths |
| --- | ---: | ---: |
| A | 310 / 310 | 1 / 1 |
| B | 310 / 310 | 1 / 1 |

All 216 physical typed units agree across both versions, source branches and successful visits. The shorter package/feature key gives 204 distinct labels. The full Cargo profile and each emitted basename distinguish all 216 units. Each revision’s warm executable matched its independently empty executable byte for byte across both compilers. Four deliberately invalid formatter builds returned Cargo 101 with E0308 at the same file, line and column; all repaired builds succeeded. Twenty-eight complete clean suites each passed 51 tests and ignored two. There were 432 individual representative test passes and 144 successful/144 rejected external ABI assertions using the actual graph’s AST/parser libraries.

| Historical Ruff revision | Whole clean/warm ELF SHA-256 | Bytes |
| --- | --- | ---: |
| A | `f4adc9d02e7830adb6d2ff7670b8588cf645fd1a39863dbc0c8abba270becd52` | 37,505,816 |
| B | `0252a7a7873113c21cb22c81c186a3583dd0064d16912a400532e27b4c0a7ca9` | 37,487,832 |

The two builds of [astral-experiments/ohm-rust](https://github.com/astral-experiments/ohm-rust) used the same optimized stage1 configuration and differed in the single rustc_driver file. The experiment used the same #294 Cargo and stock Wild on four AMD EPYC Milan CPUs and private RAM-backed workspaces. It measures repeated returns to these two historical source versions. The figures above characterize the source-built kits on this machine.

The acquisition checked process completion at approximately 12 ms intervals. Each elapsed observation includes this exit-detection granularity, including the shorter unchanged commands. CPU uses the operating system’s child process resource accounting. Every nanosecond, user/system CPU value, incremental allocation histogram and normalized native process/CGU record is in observations.json.gz. statistics.json includes the full paired values, order strata, each discrete interval and each exact P value. REPRODUCE.md gives the offline verification and independent local replay commands. The authenticated input manifests and prior two-pair screen have separate identities. The source-built toolchain metadata and exact Git trees are in materials.json.

## Space after each ordinary command

The original recordings include two distinct physical storage boundaries. The incremental column below counts each inode once across target and shared, using actual allocated blocks. The whole private filesystem also includes Git, checkout files, mutable registry data, Cargo state and temporary files. Its after-Cargo value precedes behavior validation. The read-only SDK and registry lower live outside that filesystem. We did not separately census every nonincremental target/shared file in this cohort. Individual native executable sizes are listed above.

| Phase | Physical incremental P → Q (MiB) | Paired incremental increase (MiB) | Whole private filesystem P → Q (MiB) | Paired whole-filesystem increase (MiB) |
| --- | ---: | ---: | ---: | ---: |
| empty-A | 298.77 → 298.77 | +0.00 | 863.97 → 863.97 | +0.00 |
| first-B | 326.98 → 539.20 | +212.20 | 892.14 → 1104.37 | +212.21 |
| return-A | 353.70 → 542.63 | +188.92 | 918.92 → 1107.88 | +188.95 |
| return-B | 299.57 → 545.38 | +245.81 | 864.73 → 1110.57 | +245.85 |
| unchanged-B | 299.57 → 545.38 | +245.81 | 864.73 → 1110.57 | +245.85 |

disk-scope.json contains every before/after value for the 24 ordinary installations, the apparent and allocated incremental bytes, medians, paired differences and ratios. Only the preregistered latency endpoints enter the 2× decision.

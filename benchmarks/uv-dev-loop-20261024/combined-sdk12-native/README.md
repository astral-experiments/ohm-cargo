# Combined SDK12 native dev-loop result

Neither endpoint met its predeclared native speedup gate. Both first blocks were valid; both failed statistically, so neither inverse block ran. These results do not establish a speedup, equivalence, or absence of regression.

The candidate combines [Cargo #231](https://github.com/astral-sh/ohm-cargo/pull/231), [Cargo #232](https://github.com/astral-sh/ohm-cargo/pull/232), and [Rust #218](https://github.com/astral-sh/ohm-rust/pull/218). Each command includes Cargo and all selected compiler/linker children on pinned uv, apart from the fixed equal-length comment edit. These are matched optimized developer binaries; no uv tests execute.

| Endpoint, valid first block | Baseline median | Candidate median | Geometric time reduction | 99% interval | Wins | Exact sign p | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `cargo check` | 2039.245 ms | 2003.873 ms | +12.749518% | [-5.286769%, +29.110224%] | 15/24 | 0.307456255 | Fail |
| `cargo test --no-run` | 5853.166 ms | 7354.318 ms | -6.660323% | [-38.918937%, +17.901672%] | 14/24 | 0.541256189 | Fail |

Positive reduction favors the candidate; negative reduction means a slower candidate point estimate. Test-build's point estimate is 6.66% slower. Both intervals span improvement and slowdown. The median comparison is descriptive and is not the paired geometric statistic.

Each endpoint prescribed two separate balanced 24-pair blocks. Each block required a positive 99% bootstrap lower bound, exact two-sided sign p < 0.01, and speedup in both AB/BA order strata. A valid failure stops that endpoint. The first-block seeds were 2026102391 (check) and 2026102393 (test-build); the unused inverse seeds and every fixed order remain in [protocol.json](protocol.json). No pooling, extension, filtering or valid-result retry occurred.

[pairs.csv](pairs.csv) contains all 48 valid pairs as original integer nanoseconds. [results.json](results.json) includes complete statistics and order strata. From this directory, reproduce the saved-data analysis with the exact retained statistics functions:

```sh
sha256sum -c CHECKSUMS.sha256
python3 -I -B replay.py
```

[METHOD.md](METHOD.md) describes the commands, state lifecycle, build settings, output admission and limitations. [identities.json](identities.json), the two exact patches, and [runtime-members.json](runtime-members.json) bind the source and binary comparison. [validation.json](validation.json) summarizes the authenticated 247-file private collection for each valid block, raw validity gates, restored freshness and independent replay. No raw environment, private filesystem paths or host process arguments are published.

Host5 was retired after operational/occupancy failures, including one invalid cohort with 11 saved observations. Its effects were never opened, and it contributed no durations. Both published endpoints ran entirely on the subsequently selected perf1022 host; the infrastructure decision preceded comparative effects. Invalid host5 data remains separate and excluded.

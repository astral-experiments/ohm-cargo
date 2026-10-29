# Two lockfile collision guards on Ohm Cargo 1.99.0-18

Both guards bypass the `EncodeResolve` collision check when package name/version pairs prove that serialised package IDs are distinct. The hash-set guard accepts unique pairs in any order. The ordered guard accepts strictly increasing pairs without allocation. Either declines ambiguous input and calls the same existing diagnostic. uv has 728 locked packages, 27 names with multiple versions and zero exact name/version collisions.

Each row compares one guard with the same unmodified version of the earlier stack, using matched non-PGO release-style drivers. The baseline includes the five Cargo changes and Rust standard-library path guard linked into Cargo. These observations count the Cargo process on an ordinary, warmed `cargo check --locked --offline -j8`. Initial observations used DynamoRIO and independent repeats used Cachegrind. No compiler or linker work is included. Fractions are medians of paired reductions. The rank intervals have 96.14% coverage at 12 pairs and 99.22% at 8 pairs.

| Guard | Cohort | Pairs | Base median | Guard median | Saved | Rank interval | Sign p | Order p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hash | initial | 12 | 907,777,916.0 | 906,415,438.0 | 0.1453% | [0.1418, 0.1597]% | 0.000488 | 0.002165 |
| hash | repeat | 8 | 906,165,793.0 | 904,830,073.0 | 0.1503% | [0.1335, 0.1560]% | 0.007812 | 0.028571 |
| ordered | initial | 12 | 908,270,435.5 | 906,851,350.0 | 0.1565% | [0.1472, 0.1672]% | 0.000488 | 0.002165 |
| ordered | repeat | 8 | 906,393,795.0 | 904,897,446.0 | 0.1659% | [0.1322, 0.1834]% | 0.007812 | 0.028571 |

All four cohorts passed their own registered gates. The earlier hash-set screen's counter setup failed before its first observation. Its original log, three successful base-only setup admissions and the narrow certificate-environment recovery are included. Independent schedules and a common comparator do not establish a significant difference between the guards. Native edited-command timings are a separately registered study.

Each guard passed nine Cargo CLI cases and forty direct diagnostic comparisons for lockfile formats v1–v5. The Ohm-only census covered 55 published releases, 285 branch heads and 229 pull request heads (143 open), including both source layouts. Among 304 Cargo-source commits, five file versions retained the same unconditional operation. The two function forms differed only in spelling the empty `HashMap` constructor. Thirteen other commits were benchmark-only. The near matches, source-blob proofs and separate review of [Ohm Cargo #275](https://github.com/astral-sh/ohm-cargo/pull/275) accompany the report. The census timestamp and all refs are in `ohm-source-census/`.

Run these commands at the extracted archive root to check every file and reconstruct both score receipts from raw observations and fixed schedules.

```sh
sha256sum -c SHA256SUMS
python3 -I -B work/round18-cargo/lockfile-collision/verify.py --recovery
python3 -I -B work/round18-cargo/lockfile-collision-ordered/verify.py
python3 -I -B work/round18-cargo/lockfile-collision/render-source-census.py
```

`paired-counts.csv` has all 40 pairs. Raw process outputs, per-pair receipts, protocols, sources, patches and case witnesses are under `work/`. `identities.json` records SHA-256 and the packet for each compiled executable omitted from this compact copy. See `work/round18-cargo/RESOLVER-REPLAY.md` for new-machine reproduction with those binaries or freshly built matched drivers.

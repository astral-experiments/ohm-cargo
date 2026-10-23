# Distinct target-source filenames: SDK12 dirty-check evidence

The fast path reduced **Cargo-parent instructions** in both fixed dirty `cargo check` blocks:

| Block | Paired geometric reduction | 99% paired bootstrap interval | Wins |
| --- | ---: | ---: | ---: |
| 1 | 0.751193% | 0.733421–0.773354% | 8/8 |
| 2 | 0.725574% | 0.708082–0.740319% | 8/8 |

Each block separately passes the preset gate: eight wins and a lower 99% reduction bound greater than 0.1%. Each two-sided exact sign p is 0.0078125. The blocks use their original schedules, 200,000 resamples and seeds 2026102381/2026102382. There is no pooled or familywise claim.

This is a Cargo-process instruction result. Compiler and linker children ran natively and are outside the count. It establishes no whole-command wall-time speedup. The separately planned test-build endpoint is outside this check-only package.

## Change and correctness

Distinct source filenames imply distinct source paths. `unique_build_targets` first checks borrowed filenames and returns early when they are unique; a collision or missing filename uses the existing full-path diagnostic map. Manifests with fewer than two targets return immediately.

The exact patch is [candidate.patch](candidate.patch). Measured baseline: `fdd26156be98618e2e01a9e02703edac71b79a35`; candidate tree: `90af39c2cab717940d5b09c1a4add2aaa02734e1`. Published candidate [bca8c107](https://github.com/astral-sh/ohm-cargo/commit/bca8c1077b2b40b4b037edc059333d7d98f91bae) has that identical tree. Both measured builds retained the baseline Git HEAD while changing the staged source; publication commit metadata is separate.

Two focused regression selectors passed, with zero failures or ignored cases. A real duplicate emitted the identical 297-byte warning in both arms. Distinct directories containing the same filename emitted no duplicate warning. Both builds used the same optimized recipe and actual compiler argument vectors; stripping preserved all 31 allocated ELF sections in each arm.

## Collection and limitations

The workload is unchanged uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`, with the existing equal-length comment edit in `crates/uv/src/lib.rs`. Each arm had independently warmed private target, shared-build and package-home banks, activated at the same paths. The SDK12 compiler, rustdoc and linker were common. Every measured check compiled only the uv library, with the same ordered compiler arguments/environment and exact metadata output bytes established by native/profile preflights. Original source, lockfile and active Cargo were restored, and final native freshness was verified.

All 32 profiles are included. Host activity was observational and never used to select samples. Parent polling can depend on native child scheduling. All profiles retain the known Callgrind brk-overflow warning; final totals, disjoint self-cost sums and stderr `Collected` counts agree. Header summaries are recorded separately. Both check cohorts completed without discarded samples. A later test-build collection stopped on an operational guard before analysis; its effects remain unread and it contributes nothing to this package. Excluded setup, correctness and packaging failures remain in the private history and contribute no observations.

The public sanitizer replaces only the command header and pathname definitions. Function names, compressed references, calls, positions, costs, totals and every other record byte remain exact; each profile records the original hashes and the unchanged non-path stream hash. Private environments, host argv, authentication/transport logs and unrelated experiments are absent. The replay verifies the public derivative and numerical result; it does not recreate private collection validation.

Run `python3 reproduce.py --profiles profiles` to authenticate all profiles and recompute both fixed gates. See [REPRODUCE.md](REPRODUCE.md) for building and collecting a fresh workload. [source-identities.json](source-identities.json), [build-recipe.json](build-recipe.json) and [protocol.json](protocol.json) retain the exact source, artifact and prospective statistical settings.

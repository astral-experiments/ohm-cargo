# Batched lockfile graph insertion: SDK12 dirty-check evidence

The change reduced **Cargo-parent instructions** in both fixed dirty `cargo check` blocks:

| Block | Paired geometric reduction | 99% paired bootstrap interval | Wins |
| --- | ---: | ---: | ---: |
| 1 | 1.457136% | 1.209366–1.564978% | 8/8 |
| 2 | 1.498801% | 1.477944–1.521238% | 8/8 |

Each block separately passes the preset gate: eight wins and a lower 99% reduction bound greater than 0.1%. Each two-sided exact sign p is 0.0078125. The original inverse schedules, 200,000 resamples and seeds 2026102385/2026102386 are unchanged. There is no pooled or familywise claim.

This is a Cargo-process instruction result. Compiler and linker children run natively and are outside the count. It establishes no whole-command wall-time speedup. The separately planned test-build endpoint is outside this check-only package.

## Change and correctness

Lockfile decoding used to add every source node, then look it up again in the persistent outer map for each dependency. `Graph::link_many` obtains the source adjacency map once and inserts its successfully resolved dependencies there. Empty source nodes, dependency-lookup order and side effects, duplicate-edge semantics, existing edge values and deterministic ordering are preserved. The original `link` API remains available.

The exact parent-relative patch is [candidate.patch](candidate.patch). Baseline source is published `bca8c1077b2b40b4b037edc059333d7d98f91bae` (tree `90af39c2cab717940d5b09c1a4add2aaa02734e1`); candidate tree is `c688d8d2232d1b8bb776d589a5fdb6218df7af38`. Both measured builds retained common embedded HEAD `fdd26156be98618e2e01a9e02703edac71b79a35` while staging their respective full trees. Published candidate [ddaa93b0](https://github.com/astral-sh/ohm-cargo/commit/ddaa93b0da4f9b432413a26120029462f499eafc) has the same full tree and sole parent bca8c107. Publication commit metadata is separate.

Five graph tests and 24 lockfile-compatibility tests passed, with zero failures or ignored cases. The new tests cover empty nodes, duplicates, self edges, retained nondefault values, child ordering and the absence of implicit child nodes. Both optimized builds used the same recipe and actual compiler argument vectors; stripping preserved all 31 allocated ELF sections in each arm. This is focused Linux validation, not the full Cargo test matrix.

An earlier released-SDK12 diagnostic attributed 22.86 million inclusive instructions to 3,753 `Graph::link` calls in lockfile decoding, plus 744 source insertions. The algorithm reduces those 4,497 outer-map entries to 744. Inner adjacency insertions remain. That prior inclusive cost motivated the experiment; it is not itself a measured saving.

## Collection and limitations

The workload is unchanged uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`, with the existing equal-length comment edit in `crates/uv/src/lib.rs`. Each arm has independently warmed private target, shared-build and package-home banks, activated at the same paths. The SDK12 compiler, rustdoc and linker are common. Every measured check compiles only the uv library, with the same ordered compiler arguments/environment and diagnostics established by native/profile preflights. Original source, lockfile and active Cargo are restored, and final native freshness is verified.

The check metadata has one admitted complete hash per arm. Before measurement, the released SDK12 `rustc -Zls=all` listings matched exactly, and a complete reconstruction accounted for all 56 changed bytes: three two-record swaps, one two-record relocation with relative-offset rebasing, and two associated index-field changes. Runtime guards accept only those finite complete hashes and stop on any unseen hash. No general metadata mask or full private-metadata semantic decoder is claimed. The separate test-build preflight also accounted for the exact observed full Wild output hashes; those secondary outputs contribute no instruction observations here.

All 32 profiles from the two valid fixed check blocks are included. Host activity is observational and never used to select samples. Parent polling can depend on native child scheduling; every observation remains included. Final totals, disjoint self-cost sums and stderr `Collected` counts agree. Header summaries and the known Callgrind brk-overflow warning are retained separately. An excluded initial preflight stopped because the already-configured private TMPDIR had not been created; it was created before a fresh unchanged preflight and before either measured cohort. That failed setup's effects remain unread and contribute no observations. No valid block is retried or extended.

The public sanitizer replaces only the command header and pathname definitions. Function names, compressed references, calls, positions, costs, totals and every other record byte remain exact; each profile records original hashes and the unchanged non-path stream hash. Private environments, host argv, authentication/transport logs and unrelated experiments are absent. The replay verifies the public derivative and numerical result; it does not recreate private collection validation.

Run `python3 reproduce.py --profiles profiles` to authenticate all profiles and recompute both fixed gates. See [REPRODUCE.md](REPRODUCE.md) for building and collecting a fresh workload. [source-identities.json](source-identities.json), [build-recipe.json](build-recipe.json) and [protocol.json](protocol.json) retain exact source, artifact and prospective statistical settings.

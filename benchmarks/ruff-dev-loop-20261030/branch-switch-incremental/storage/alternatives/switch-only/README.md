# Compress a branch history on checkout switches

On Unix, the opt-in compiler compresses the dependency graph and query cache of a newly published session when the newest finalized session at the start of the compile came from another checkout. The first dirty edit after a return can read compressed tables and publish raw files. Subsequent edits to that branch use ordinary tables. Concurrent sessions can finish in an order different from their creation timestamps. A same-checkout or unidentified session tied for newest keeps the new files raw. Rustc still selects the same source for incremental compilation and uses its normal dependency validation. [Policy delta](source/source.patch) · [Native compiler, tests and matched SDK](compiler.json)

The compiler passed all eight incremental unit tests, ten compiler calls in the compressed-cache regression, seven covering flag changes and twelve covering native assembly. Two successive same-branch edits retained the previous branch’s immutable data and produced correct new executables. A separate enumerated test compared both selectors across 279,620 histories. [Source tests and comparison](source/source.json)

## Ruff parser branch returns

These measurements switch between the original parent and feature commits for Ruff’s AST layout change. Both conditions use the same fixed physical compiler, Cargo and Wild. The default uses one session. The opt-in condition retains and compresses a second checkout’s tables. Four independent clean builds supply the native references for both branches and settings. The first pair also introduces a type error and verifies recovery in both settings. The storage figures include both complete target and Cargo build directories after the command, with hard links counted once. [Original workload](../../..)

### 2 fresh pairs on ext4

The ranges show the two individual return ratios.

| Measure | Default median | Opt-in median | Paired speedup | Return range or interval | Whole storage, default → opt-in |
| --- | ---: | ---: | ---: | ---: | ---: |
| First feature visit | 8.61 s | 9.28 s | 0.93× | — | 273 → 323 MiB |
| Return to parent | 8.80 s | 2.88 s | 3.06× | 2.91–3.21× | 288 → 279 MiB |
| Return to feature | 8.86 s | 3.56 s | 2.49× | 2.44–2.54× | 258 → 281 MiB |
| First feature visit plus return | 17.41 s | 12.16 s | 1.43× | — | — |

[Complete pairs](sample-ext4-2-pairs-202610300735.json.gz) · [Native verdicts and physical disk readback](native-ext4-2-pairs-202610300735.json.gz) · [Paired calculations](summary-ext4-2-pairs-202610300735.json)

### 12 fresh pairs on tmpfs

Each order ran six times. The return intervals give simultaneous 95% coverage over the two directions. The independent ext4 pilot used separate installations.

| Measure | Default median | Opt-in median | Paired speedup | Return range or interval | Whole storage, default → opt-in |
| --- | ---: | ---: | ---: | ---: | ---: |
| First feature visit | 8.67 s | 8.97 s | 0.96× | — | 271 → 321 MiB |
| Return to parent | 8.70 s | 2.77 s | 3.22× | 2.94–3.29× | 286 → 277 MiB |
| Return to feature | 8.87 s | 3.35 s | 2.65× | 2.49–2.73× | 255 → 278 MiB |
| First feature visit plus return | 17.37 s | 11.73 s | 1.48× | — | — |

[Complete pairs](sample-tmpfs-12-pairs-202610300751.json.gz) · [Native verdicts and physical disk readback](native-tmpfs-12-pairs-202610300751.json.gz) · [Paired calculations](summary-tmpfs-12-pairs-202610300751.json)

Across the same twelve pairs, the median ratio of total child CPU time was 7.22× on return to the parent and 5.93× on return to the feature. This sums user and system CPU for Cargo and its completed children.

## Check and test builds

These additional runs held the complete compiler installation fixed. A two-pair range shows its two observations. For twelve pairs the ranges give simultaneous 95% coverage over both returns. The check replay requires the correct AST size and an E0308 for the contradictory size. Test builds must reproduce the clean executable, its 245-test inventory and three representative native verdicts. Those checks run outside the timer.

| Command | Pairs | Return to parent | Return to feature | Whole storage on parent / feature | First feature visit plus next return |
| --- | ---: | ---: | ---: | --- | ---: |
| `cargo check` | 2 | 3.08× (3.00–3.16×) | 2.96× (2.90–3.02×) | 182 → 171 MiB / 171 → 172 MiB | 1.48× |
| `cargo test --lib --no-run` | 2 | 2.86× (2.73–2.99×) | 2.33× (2.31–2.35×) | 419 → 404 MiB / 385 → 406 MiB | 1.39× |

For `cargo check` (2 pairs), the first visit to the feature took 7.11 → 7.29 s and used 176 → 203 MiB. Median paired child CPU ratios on the two returns were 3.23× and 3.03×. The registration seed was `202610300800`. [Native/type readbacks](verb-check-2-pairs-202610300800-verified.json.gz) · [All observations](verb-check-2-pairs-202610300800-sample.json.gz) · [Paired calculations](verb-check-2-pairs-202610300800-summary.json)

For `cargo test --lib --no-run` (2 pairs), the first visit to the feature took 11.08 → 12.23 s and used 402 → 454 MiB. Median paired child CPU ratios on the two returns were 7.06× and 5.70×. The registration seed was `202610300801`. [Native/type readbacks](verb-test-no-run-2-pairs-202610300801-verified.json.gz) · [All observations](verb-test-no-run-2-pairs-202610300801-sample.json.gz) · [Paired calculations](verb-test-no-run-2-pairs-202610300801-summary.json)

## Complete compiler instructions

These two pairs ran both returning compilers under Callgrind. Every count was reopened from the complete instruction profile, reconciled with its own independent log, and tied to the actual Cargo compiler invocation. The counts include the codec and exclude Cargo and the later native reader.

| Pair | Return | Default instructions | Opt-in instructions | Ratio |
| ---: | --- | ---: | ---: | ---: |
| 1 | parent | 62,187,151,911 | 12,907,775,642 | 4.818× |
| 1 | feature | 62,422,491,336 | 16,412,453,528 | 3.803× |
| 2 | parent | 62,167,172,937 | 12,903,650,998 | 4.818× |
| 2 | feature | 62,450,749,213 | 16,415,193,152 | 3.804× |

[Per-crate counts](sample-tmpfs-2-pairs-instructions-202610300810.json.gz) · [Independent profile and argv reconciliation](counter-tmpfs-2-pairs-instructions-202610300810.json)

## Full Ruff CLI storage

On the same draft source, the full CLI used 2,305.9 → 2,570.7 MiB after the final unchanged build (+11.49%). The first feature visit added 495.6 MiB and the return to the parent added 49.4 MiB. The largest sampled allocation across each history grew by 10.09%. Current branch returns matched clean whole executables within each setting. Across settings, the reader and executable sections matched on both branches. [Complete measured history, object files by crate, native comparisons and replay](full-ruff-cli)

## Working on one branch

This separate experiment compares two enabled branch caches. One compiler keeps uncompressed tables. The other compresses on checkout switches. Each block measured four changes to Ruff’s unary-pattern grammar, with both branches already built. The first dirty edit averaged 2.620 → 2.665 s. The next three averaged 2.636 → 2.640 s. The two blocks are too few to establish a small timing difference. After editing, the settled complete directories measured 376.35 → 288.09 MiB. The previously measured policy that compressed on every dirty edit added 0.38 s per edit in its own two-pair experiment. [Earlier compact policy](../native-compact)

Separate kernel traces showed the genuine parser compiler read two packed tables on its first edit and created zero. The six later dirty compiles across both blocks performed zero packed-table operations. All 68 linked reader executables matched their clean builds and all 104 native object multisets matched. The incremental metadata and complete `.rlib` archives differed from the independent empty builds. The dirty library builds invoked one parser compiler. The separate reader linked and exercised the resulting libraries. [Full ordinary-edit records and verifier](grammar-edits)

Eight complete parser instruction profiles were collected for ordinary grammar edits. The preregistered equality check rejected the comparison because Cargo selected different build namespaces for the two compiler versions. A separately registered readback found five of sixteen named Rust metadata inputs differed in each block. No paired CPU effect is reported from those profiles. [All eight counts, both failed checks and physical input identities](grammar-edits/instructions)

## Reproduce

Start from Ohm Rust `c9119d267c9843f0fb5dcbc1cc05653eac6051e3`. Apply the first compiler patch in `../native-compact/compiler.patch`, then `source/source.patch`. The complete resulting tree is `8852d19f44a404cb5f049f28bb8e9f3a127f142c`. Build the compiler using the matched toolchain setup in the main study. From the branch-switch benchmark directory, the two-pair ext4 replay is

```sh
python3 -IB opt-in/run.py --parent-sdk "$SDK" --candidate-sdk "$SDK" \
  --same-sdk --enable-retention --workflow build --pairs 2 --jobs 4 \
  --order-seed 202610300735 --offline --pack "$RUFF_PACK" --out "$NEW_OUTPUT"
```

For the twelve-pair confirmation, use `--pairs 12 --order-seed 202610300751` on a fresh private tmpfs. `python3 -IB verify.py` in this directory recomputes the recorded pairs. `python3 -IB grammar-edits/verify.py` rechecks the ordinary edits and real native table operations.

The ordinary grammar edit has its own reviewer command. It takes a Ruff checkout, two compiler SDKs, an offline Cargo registry and a fresh output directory. [Run the same-branch edit replay](grammar-edits/replay)

A separate end-to-end run exercised that public command on fresh directories. All 42 ordinary Cargo builds and 42 independently linked readers produced the expected native verdict and clean-matching binary. The six empty references covered both branches and the local grammar edit on both compilers. [Reviewer command validation](grammar-edits/replay/qualification)

The draft subsequently added the packed-cache, branch-cache flag and incremental crate tests to its native CI job. The only changed path in that commit was `.github/workflows/ci.yml`. The measurements use its parent’s compiler. [Tracked trees and CI change](ci-coverage.json) · [Git comparison](https://github.com/astral-experiments/ohm-rust/compare/08d49cba6aacb0cac27a96eea335ed1c7439f483...b676a640c76193a0e241d2517a64e37e156659b9)

On Apple Silicon, the native job passed all 8 incremental unit tests and all 4 selected integration tests, including cache corruption and switching the option off. [macOS job](https://github.com/astral-experiments/ohm-rust/actions/runs/41027951230/job/123970482094)

## Full Ruff CLI timing protocol

A separately registered comparison uses the same physical compiler to build the complete Ruff executable with the option off and on. Two fresh pilot pairs must exceed 2× on all four branch returns before twelve new pairs can start. The protocol reports first-visit cost, child CPU and complete storage for every installation. [Frozen schedule, admission rules, verifier and rerun instructions](full-cli-timing/registration)

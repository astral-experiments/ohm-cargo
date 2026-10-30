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

## Working on one branch

This separate experiment compares two enabled branch caches. One compiler keeps uncompressed tables. The other compresses on checkout switches. Each block measured four changes to Ruff’s unary-pattern grammar, with both branches already built. The first dirty edit averaged 2.620 → 2.665 s. The next three averaged 2.636 → 2.640 s. The two blocks are too few to establish a small timing difference. After editing, the settled complete directories measured 376.35 → 288.09 MiB. The previously measured policy that compressed on every dirty edit added 0.38 s per edit in its own two-pair experiment. [Earlier compact policy](../native-compact)

Separate kernel traces showed the genuine parser compiler read two packed tables on its first edit and created zero. The six later dirty compiles across both blocks performed zero packed-table operations. All 68 linked reader executables matched their clean builds and all 104 native object multisets matched. The incremental metadata and complete `.rlib` archives differed from the independent empty builds. The dirty library builds invoked one parser compiler. The separate reader linked and exercised the resulting libraries. [Full ordinary-edit records and verifier](grammar-edits)

## Reproduce

Start from Ohm Rust `c9119d267c9843f0fb5dcbc1cc05653eac6051e3`. Apply the first compiler patch in `../native-compact/compiler.patch`, then `source/source.patch`. The complete resulting tree is `8852d19f44a404cb5f049f28bb8e9f3a127f142c`. Build the compiler using the matched toolchain setup in the main study. From the branch-switch benchmark directory, the two-pair ext4 replay is

```sh
python3 -IB opt-in/run.py --parent-sdk "$SDK" --candidate-sdk "$SDK" \
  --same-sdk --enable-retention --workflow build --pairs 2 --jobs 4 \
  --order-seed 202610300735 --offline --pack "$RUFF_PACK" --out "$NEW_OUTPUT"
```

For the twelve-pair confirmation, use `--pairs 12 --order-seed 202610300751` on a fresh private tmpfs. `python3 -IB verify.py` in this directory recomputes the recorded pairs. `python3 -IB grammar-edits/verify.py` rechecks the ordinary edits and real native table operations.

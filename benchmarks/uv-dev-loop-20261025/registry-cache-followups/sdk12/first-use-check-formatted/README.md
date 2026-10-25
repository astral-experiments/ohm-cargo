# Formatted #239: parse registry manifests once on a cache miss

This is the fresh confirmation of public head `a90c95c5741c77c291a13a6c8eacc8385ceb70c6`, tree `2f4563a9e1311f214f8031c611346e4758134548`. Against the cache-enabled R1 implementation in Cargo #237, it reduced first-use **Cargo-parent instructions** on both independently prepared VMs. Compiler, linker and build-script children were not instrumented. These are instruction counts, not native elapsed times.

| Independent block | Paired geometric reduction | Paired 99% interval | Wins | Exact two-sided sign p |
| --- | ---: | ---: | ---: | ---: |
| 1 | 7.249018% | 7.222735–7.273604% | 8/8 | 0.0078125 |
| 2 | 7.291046% | 7.230422–7.427657% | 8/8 | 0.0078125 |

Each fixed block required eight wins, p < .01 and a lower 99% reduction bound > 1%, using 200,000 paired bootstrap resamples. Balanced inverse orders and seeds 20261025341/20261025342 were committed before execution. Both complete raw/restoration gates preceded all 32 final/self/stderr reconciliations, and every reconciliation preceded either estimate. Root independently replayed all 14,914 retained leaves and both summaries. No pooling, retry, replacement or extension occurred. The original-head results remain separate.

## Source, build and correctness

The CI correction wraps one production closure and adds an optional trailing comma. Later source positions move one line. Its stripped executable differs, so the old randomized result was not transferred: the formatted executable received these two fresh blocks.

Both builds embed the same historical commit `fd7a25d7bed7503d628c90879ba265e173343b28`. Baseline tree is `5fbb37f329d5c185e95511832854596937899019`; the published formatted tree is separate from the embedded version. The rebuilt R1 binary is byte-identical to the original: SHA `863d60cec75d0caac6428458a1867809aa4682dcb94ac13805f5f5bc5ee8eada`, 43,452,656 bytes. Formatted Y is SHA `71242e4ad228aa9824021d8e9e4c51d011fdaee3314c9e30b2c727c584666e10`, 43,452,784 bytes: 128 bytes larger than R1 and 304 bytes smaller than original Y.

The matched stock Rust 1.99 producer, compiler/linker paths, flags and all four complete lib/bin rustc argument vectors match the original recipe. The current Git executable is explicitly rebound; the sole build-script Git command consumed the same full commit, short commit and date. Original raw Git stdout was not retained; its three consumed fields are authenticated by the original build/version receipts, and current raw stdout is retained in the recipe.

All 25 formatted-candidate focused tests passed, including both actual GlobalContext regressions for complete typed/syntax diagnostics and ignored-key/metadata behavior. The 23 baseline passes transfer by complete executable equality. The earlier semantic-source witness compared 470 real manifests twice, 940 full cache bodies, 24 synthetic cases and nine complete errors; its minimal context stub remains disclosed. All 31 allocated sections are preserved by debug stripping in each arm. The build owner stopped in its final index-byte restoration check after all build/test commands succeeded; a separately authenticated bounded restoration restored the exact original index.

## Mechanism and first-use controls

R1 typed-parses an uncached registry manifest, then reparses it to create its cached TOML value. Y parses TOML 1.1.2's DeTable once, clones the parsed tree for typed deserialization, and consumes the original tree for the cached value. Original typed errors retain input and spans. The warm hit path, unsupported-value fallback, key/payload format, security checks and atomic persistence remain unchanged.

Every current full profile has exactly 1,034 outer `toml::de::parser::parse_document` calls in R1 and 564 in Y: 470 removed. Mean direct incoming outer-parser Ir falls by 108,237,747.750 and 108,260,628.250 per block. Net parent Ir falls by 97,611,425.000 and 98,224,230.125; all other work changes by 10,626,322.750 and 10,036,398.125. Nested parser costs are contained in the outer edge and are never added to it. The remainder is not attributed entirely to cloning.

The command is `cargo -Zohm-defaults=yes check --locked --offline -j 8` on uv `3d82a6ad5a7eab8c68236553b7846517767c4b61`. The deterministic ordinary-comment edit has equal-length before/after forms; Rust tokens and existing source positions remain unchanged. Only the parsed-document cache is cold. Independent per-arm compilation banks and package sources are warm, and no compiled uv state crossed arms or hosts. The workload uses the separate fixed SDK12 f93 Rust compiler and Wild.

Every call starts with the document cache absent and ends with the same 445 slots and 803,161 bytes. All 32 complete-file and payload-hash inventories are identical, using R1's original `key[:3]` slot policy. `cache-controls.json` includes the complete shared inventory and all 32 per-call custody joins. The raw observer validates ownership, single-link files, bounded sizes and JSON shape; it does not independently recompute keyed BLAKE3. Complete cached payloads remain in authenticated private collections. Final committed bytes are not total writes, hits or physical I/O. The separate two-choice collision change is absent.

Native/profile child argv, ordered environment, diagnostics, exact per-arm output hashes, freshness and restoration passed. Only the existing jobserver-descriptor comparison omission applies. Both hosts' cross-arm rmeta differences are exactly 239 bytes representing eight generated OpaqueLifetime index permutations. All 1,135 stable-key definitions, fingerprints and both spans per definition match; all remaining bytes match. The same reader and 34 fresh negative/listing cases passed independent review. Numbered calls keep one exact output hash per arm; there is no general metadata mask.

## Portable replay

```sh
python3 -I -B /path/to/this/folder/verify_package.py
```

The Python-standard-library replay authenticates the complete public file set, decompresses all 32 full profiles, reconciles final/self/stderr Ir, reproduces both fixed 200,000-resample summaries and gates, recomputes the parser edges and checks all public cache-inventory joins. `counts.json` retains every paired integer count and order. Each profile manifest row binds original raw/gzip/stderr hashes and the unchanged nonpath instruction/call stream. Raw private environment, transport, host and cache-payload records are omitted; their custody digests remain explicit.

`source/` includes full-index patches, all three complete changed files against the common parent, Cargo.lock, Git identities and normalized matched recipe/tool hashes. In a fresh disposable Cargo clone at `fd7a25d7bed7503d628c90879ba265e173343b28`, apply `baseline-full.patch` or `candidate-full.patch` with `git apply --index`, then require `git write-tree` to match its recorded tree while HEAD stays fixed. Use the same physical source/target paths sequentially and the recorded stock toolchain, locked dependencies, ThinLTO, one codegen unit, opt-level 3, debug 1, no incremental/PGO/BOLT and `all-static,ohm-defaults`. Preserve full binaries and strip measured copies with `objcopy --strip-debug`. Private prefixes are parameterized; a rebuild elsewhere need not reproduce binary bytes.

Four excluded setup profiles never enter these results. Two zero-work cohort-file staging refusals and their narrow successor are retained, as is a pre-launch correction to two outer collection labels. No numbered guard or result was retried. This is formatted Y versus R1, not cache-disabled or shipped Cargo. It makes no additive cross-study, new warm-path or whole-command elapsed claim. R1's separate native A/A safeguard failed; no native candidate comparison ran there, and Y's elapsed effect remains unknown.

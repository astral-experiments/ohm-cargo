# Parse registry manifests once on a cache miss

Against the cache-enabled R1 implementation in Cargo #237, this change reduced first-use **Cargo-parent instructions** by 7.228% and 7.245% on two independent VMs. Each prospectively fixed block had eight pairs and eight wins. Compiler, linker and build-script children were not instrumented. This is not a native elapsed-time result.

| Independent block | Paired geometric reduction | Paired 99% interval | Wins | Exact two-sided sign p |
| --- | ---: | ---: | ---: | ---: |
| 1 | 7.227597% | 7.203107–7.245159% | 8/8 | 0.0078125 |
| 2 | 7.244900% | 7.232339–7.260953% | 8/8 | 0.0078125 |

Each block independently required eight wins, p < .01, and a lower 99% reduction bound > 1%, using 200,000 paired bootstrap resamples. Orders were balanced and inverse; seeds were 20261025301 and 20261025302. Both complete raw/restoration gates preceded all 32 final/self/stderr reconciliations, and every reconciliation preceded either estimate. There was no pooling, extension, replacement, or result-selected filtering.

## Change and mechanism

R1 parses an uncached registry manifest into its typed representation, then parses the source again to construct the cached TOML value. Y parses the pinned TOML 1.1.2 `DeTable` once, clones that parsed tree for typed deserialization, and consumes the original tree to construct the cache value. Typed errors retain their original input and spans. The hit path, unsupported-value fallback, key and payload format, security checks and atomic write path remain unchanged.

The full profiles show exactly 1,034 outer `toml::de::parser::parse_document` calls in every R1 sample and 564 in every Y sample: 470 calls removed. Mean direct incoming outer-parser Ir falls by 108,257,082.25 and 108,243,064.125 per block. Net parent Ir falls by 97,308,109.875 and 97,550,457.125; the remaining work increases by 10,948,972.375 and 10,692,607. Nested parser costs are contained in the outer edge, never added to it. The remainder is not attributed entirely to cloning.

## Workload and output contract

The command is `cargo -Zohm-defaults=yes check --locked --offline -j 8` on uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61`. The deterministic ordinary-comment dirty edit has equal-length before/after forms; Rust tokens and existing source positions are unchanged. Only the registry parsed-document cache is cold. Independent per-arm compilation banks and package sources are already warm. Each counted call starts with the cache absent and ends populated; retired records are retained rather than deleted.

All 32 post-cache entry inventories are identical across both arms and hosts: 445 slots, 803,161 bytes, including matching complete-file and payload hashes. These final committed bytes are not a total-write, syscall, or physical-I/O measurement. Both arms use R1's original single-slot rule; the separate collision experiment is absent.

Actual native/profile child argv, environment, diagnostics, per-arm output hashes, freshness and restoration passed. The only environment omission is the existing jobserver-descriptor comparison rule. Cross-arm metadata differed by decoded generated `OpaqueLifetime` index permutations: 56 bytes/two definitions on block 1's host and 238 bytes/eight definitions on block 2's host. All 1,135 stable-key definitions, fingerprints and both spans per definition matched; all remaining bytes matched. Twenty-eight negative/listing controls and independent root replay passed. Numbered samples retained one exact admitted output hash per arm; no general metadata mask was introduced.

The stock producer compiler is Rust 1.99.0 (`b940084d7…`, LLVM 23.1.1). The uv workload uses the separate pinned SDK12 compiler (`f93a752e…`) and Wild. Both Cargo arms embed the identical historical commit `fd7a25d7…`; their source trees are `5fbb37f3…` and `30b4f1fb…`. This matters because the cache codec key includes the embedded Cargo commit. A later publication commit is not the measured embedded version.

The production build passed all 48 focused tests, including two actual `GlobalContext` regressions. The earlier lightweight module witness compared all 470 real manifests in cold and repeat passes, all 940 complete cache bodies, 24 synthetic cases and nine complete errors; its minimal context stub is explicitly disclosed. The candidate binary is 432 bytes larger. All 31 allocated sections survive debug stripping unchanged in each arm.

## Portable replay

Run from any directory with Python 3 and its standard library:

```sh
python3 -I -B /path/to/this/folder/verify_package.py
```

This authenticates the complete public file set, decompresses all 32 full profiles, reconciles the final Ir footer with self costs and the retained stderr counter line, reproduces both exact 200,000-resample summaries and gates, and independently recomputes the direct parser edges. `counts.json` retains every paired integer count and order. `profiles/PROFILE-MANIFEST.json` joins the original raw/gzip/stderr hashes and proves the unchanged nonpath instruction/call stream. `replay_parse_edges.py` reports the mechanism without changing the statistical endpoint.

`source/` contains the exact full-index patches, all three changed complete files against the common parent, the lockfile, Git blob/tree identities, normalized matched recipe and tool hashes. For a source rebuild, use a fresh disposable clone of `astral-sh/ohm-cargo` checked out at `fd7a25d7bed7503d628c90879ba265e173343b28`; apply `baseline-full.patch` or `candidate-full.patch` with `git apply --index`. Require `git write-tree` to match the corresponding recorded tree while HEAD remains fixed. Build both sequentially at the same physical source/target paths with the recorded stock toolchain, locked dependencies, ThinLTO, one codegen unit, opt-level 3, debug 1, no incremental/PGO/BOLT and features `all-static,ohm-defaults`. Preserve each full binary and use `objcopy --strip-debug` for the measured copy. The exact command/environment and focused test selectors are in the JSON recipe; private prefixes are parameterized, so an elsewhere rebuild need not be byte-identical.

## Scope and exclusions

Four excluded setup profiles are retained privately and never enter these counts. No measured attempt failed or was replaced. Early setup/schema stops and a local export-parent correction are preserved privately; none contributed samples. Full private context/host/output/cache/restoration records remain authenticated by the custody digests in `admission-and-restoration.json`; this public packet does not expose their raw environments or private paths. Public profiles preserve every instruction/call record, replacing only command/path fields.

This comparison is Y versus R1, not Y versus cache-disabled Cargo. It does not subtract or add percentages from R1's earlier +18% first-use study, establish a new warm-path effect, or establish whole-command elapsed performance. R1's native A/A safeguard failed and no native candidate comparison ran there; Y's native elapsed effect also remains unknown.

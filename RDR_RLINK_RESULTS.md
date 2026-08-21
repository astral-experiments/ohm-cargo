# Cached `.rlink` prototype results

This branch adds `cargo -Zrelink-only`. It preserves the final test unit's
`.rlink` plan and codegen objects, then uses rustc's `-Zlink-only` mode after a
private dependency edit instead of recompiling the test crate.

## Optimized Cargo and profile combination

The final comparison used an optimized build of this Cargo branch, the Rust
1.97.1 RDR toolchain, eight jobs, warmed target directories, and the canonical
`uv-normalize` edit plus exact `uv` library test.

| Profile      | Median edit to test |     MAD | No-change |
| ------------ | ------------------: | ------: | --------: |
| `no-debug`   |             1.102 s | 0.031 s |   0.287 s |
| `fast-build` |         **0.841 s** | 0.015 s |   0.318 s |

`fast-build` reduced the cached-relink median by another 23.7%. Its initial
cold build took 125.0 seconds, so this is an inner-loop optimization with a
larger one-time setup cost.

Relative to the earlier measurements on the same uv commit and workload, the
combined result is:

| Configuration                                  |     Median |   Speedup |
| ---------------------------------------------- | ---------: | --------: |
| Stock Rust 1.97.1                              |    16.52 s |      1.0x |
| Public-hash RDR                                |     6.14 s |      2.7x |
| Cached `.rlink`, debug Cargo                   |     2.11 s |      7.8x |
| Cached `.rlink`, optimized Cargo, `no-debug`   |     1.10 s |     15.0x |
| Cached `.rlink`, optimized Cargo, `fast-build` | **0.84 s** | **19.6x** |

All optimized-Cargo edit runs passed the exact test. The final `fast-build`
result is the median of 10 warmed edit cycles. The benchmark restored
`uv-normalize` to SHA-256
`42e39b6f0118f6a1ff210d17bfe04e63221c87b14dcf7ea338f2b1190404205a`.

Raw results:

- `no-debug`:
  `/private/tmp/rdr-results-rlink-release/20260731T030816Z/results.json`
- `fast-build`:
  `/private/tmp/rdr-results-rlink-fast-build/20260731T031629Z/results.json`

## Cache bounds and fallback

The prototype validates the `.rlink`, executable, and referenced object files;
rejects unsupported dependency kinds and LTO; and regenerates codegen on
missing, corrupt, stale, or mismatched cache state. It deletes obsolete object
generations and bitcode after the initial link. The measured uv cache retained
257 current objects totaling 81 MB plus a 304 KB `.rlink`.

The main remaining work is making the cache key fully adversarial rather than
path/size/mtime based, retrying compilation in the same invocation if a cached
link itself fails, and validating Windows and non-Apple targets.

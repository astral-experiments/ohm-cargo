# Dependency source remapping: dirty check

This packet contains 32 complete sanitized Cargo-parent Callgrind profiles for the dependency source-remapping change, measured on the R1 registry-cache baseline. Both fixed, independently prepared eight-pair blocks qualify.

| Machine | Fewer Cargo-parent instructions | 99% interval | Wins |
| --- | ---: | ---: | ---: |
| Host 1 | 0.5878772134% | 0.5097037162% to 0.7705442641% | 8/8 |
| Host 2 | 0.6384184130% | 0.5077332869% to 0.8238655524% | 8/8 |

Each two-sided exact sign-test p value is 0.0078125. The separate 200,000-draw paired bootstraps use the prospectively fixed seeds 20261025341 and 20261025342. Both lower bounds exceed 0.25%. Results are unpooled. A preceding, excluded single AB eligibility screen showed 0.5131901371% fewer instructions, exceeding its fixed 0.5% threshold; that screen contributes no confirmation observations. The other machine's excluded setup profiles were never opened for effects.

Run from this directory (Python 3.12.13 was used for the two identical public replays):

```sh
python3 -I -S -B reproduce.py
```

The replay authenticates every numerical-core file, independently sums raw instruction records, and checks final, self-cost, stderr-derived, arm/order and original statistical summaries. All four statistical functions and the final-count reader are byte-exact copies of the registered implementations. Every non-path profile byte remains unchanged; only command/path labels are sanitized. Call edges and instruction records remain available for attribution. CORE-MANIFEST.json covers the numerical core; the enclosing publication manifest also covers source/build documentation.

The metric is the complete Cargo parent including all its threads. Rust compiler, native linker, build-script and other child instructions are outside its scope. This is not a whole-command wall-time result. No test body executes, and no test-build claim is made.

The workload is uv 3d82a6ad5a7eab8c68236553b7846517767c4b61 with the registered equal-length five-byte ordinary-comment change. The command is `cargo -Zohm-defaults=yes check --locked --offline -j 8`. Both arms have independently source-built banks, identical active absolute paths and pinned SDK12 Rust/Wild. Native/profile compiler argv and ordered environments, diagnostics, outputs, source restoration and zero-work freshness were admitted before numbering. Host 1's cross-arm metadata differences were fully attributed to the eight generated lifetime-index cells; host 2's metadata was byte-identical. Every numbered run still required its own arm's exact output bytes.

Both arms already contain R1's registry cache. All 64 numbered before/after cache inventories match their own preflight and one another: 445 committed slots and 803,161 payload bytes. This is a content-inventory observation, not a cache-hit counter or physical-I/O measurement.

source-and-build.json and BUILD-AND-SAMPLE.md identify the exact measured trees, stock producer recipe and artifacts. The change avoids cloning the shared manifest payload when only name/source identity changes. The outer Dependency grows from 8 to 32 bytes on x86-64; its shared payload shrinks by 24 bytes. Peak memory is unmeasured. The candidate passed 24 focused cases; the baseline passed the 23 applicable existing cases, with no failed or ignored cases.

The source publication is separately gated on verification of a test-only formatting successor. This immutable numerical packet always identifies the original measured candidate tree b33fbfb6. No claim about a successor binary is inferred from source similarity alone.

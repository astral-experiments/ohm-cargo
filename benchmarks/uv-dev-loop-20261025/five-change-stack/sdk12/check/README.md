# Cargo check on the five-change stack

This reproduction packet records the combined published Cargo #231 through #235 changes against SDK12 Cargo fdd26156. It contains 32 complete sanitized Cargo-parent Callgrind profiles from two independently prepared machines. This is cumulative evidence, not a separate optimization PR.

| Machine | Fewer Cargo-parent instructions | 99% interval | Wins |
| --- | ---: | ---: | ---: |
| Host 1 | 3.9131654293% | 3.8313786816% to 4.0902500925% | 8/8 |
| Host 2 | 3.9769289640% | 3.8155950248% to 4.2274612640% | 8/8 |

Each two-sided exact sign-test p value is 0.0078125. The fixed, separate 200,000-draw paired bootstrap uses the original seeds 20261025261 and 20261025262. Both lower bounds clear the registered 1% gate. Results are unpooled and are not a sum of the individual changes' gains.

Run from this directory:

```sh
python3 -I -S -B reproduce.py
```

The replay authenticates the portable files and rechecks final instruction counts, self costs, stderr-derived counts, paired schedules and both original statistical summaries. Every non-path profile byte is preserved. Only command/path labels are sanitized; call edges and instruction records remain available for attribution. CORE-MANIFEST.json describes the original numerical core; the enclosing private handoff authenticates this core plus the source and build documentation.

The metric covers the complete Cargo parent and all its threads. Rust compiler, linker, build-script and other child processes are not instrumented. It is not whole-command wall time. No test body executes. This packet supports only the dirty-check endpoint; the independent test-build study is separate.

The workload is uv 3d82a6ad5a7eab8c68236553b7846517767c4b61, with the registered equal-length five-byte ordinary-comment change. Both arms use their own source-built native cache bank, the same absolute active paths, SDK12 Rust/Wild, live jobserver, eight workload CPUs and original ordered compiler context. Each arm's native, profiled and restored outputs were checked before numbering. Cross-arm check metadata differences were exhaustively attributed to generated lifetime-index permutations, with all other bytes, stable definitions and fingerprints preserved. The numbered runs continued to require each arm's own exact output hashes.

source-and-build.json records exact source trees, binaries, stock producer toolchain and optimization settings. combined.patch applies to fdd26156 and yields tree 8cc5186eeb53e806108ace30c0be7f4c061bfb76. Both builds retain the same embedded fdd26156 version. Production builds use stock Rust 1.99, ThinLTO, optimization level 3, one codegen unit, debug level 1, no incremental compilation and no PGO/BOLT. The SDK12 compiler executing uv is a separate pinned tool.

protocol.sanitized.json preserves the prospectively frozen protocol, replacing only host names and the benchmark root. It describes the fresh-capture contract but does not authorize a new run. The portable replay is self-contained; a new capture additionally needs independently prepared native banks and the complete input/output, host and tool admission controls. Private operational records are retained separately and are not included here.

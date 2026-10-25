Eight-change cumulative Cargo stack: separate warm test-build confirmation

This private portable packet compares a matched rebuild of SDK12 Cargo source fdd26156 with the eight-change tree 8a4b0c3cb9bafb6a04510366bbaf011502122418: Cargo #231–235, #237, the two-choice registry cache and the formatted single-parse change. Both binaries embed fdd26156. The baseline is source-matched and is not the literal shipped SDK12 Cargo executable.

| Machine | Fewer Cargo-parent instructions | 99% interval | Wins |
| --- | ---: | ---: | ---: |
| Host 1 | 18.0504395736% | 17.9353610029% to 18.1045834893% | 8/8 |
| Host 2 | 18.1137655766% | 18.0640052361% to 18.2087791486% | 8/8 |

The two fixed eight-pair schedules are balanced inverses, with seeds 20261025327/328 and 200,000 paired bootstrap draws per machine. Each exact two-sided sign p value is 0.0078125; both lower 99% bounds exceed the registered 1% gate. Results are unpooled, and they are not a sum of earlier PR gains.

```sh
python3 -I -S -B reproduce.py
```

The standalone reader authenticates all 32 complete sanitized profiles and independently reconciles final Ir, self costs, stderr counts, raw/gzip identities, pair orders and statistics. Every non-path profile byte is retained. Only the command spelling and path labels are parameterized; function names and full call edges remain available. CORE-MANIFEST.json seals the numerical core; the enclosing publication-file-manifest.json additionally seals all provenance and method files.

This measures the complete Cargo parent and all its threads during the normal dirty `cargo test --no-run --locked --offline -j 8` invocation with SDK12 defaults enabled. Rustc, linker and other child instructions are excluded. It is not a whole-command wall-time result. The primary warm-check packet remains separate and unchanged. No first-use or break-even result is claimed here.

The source is uv 3d82a6ad5a7eab8c68236553b7846517767c4b61 and the same prespecified equal-length five-byte ordinary-comment edit. Both arms use independent source-built native banks. Both original check and test-build commands were warmed and freshly verified, including both-command restoration. No test body runs. The baseline registry document cache stays absent; the candidate stays populated with the exact two-choice policy and all trust/JSON/size guards.

Six complete compiler roles are preserved as a multiset with multiplicity, each with its ordered argv and usable environment. Seven outputs per arm are validated. The original secondary cohort was operationally ineligible at one unadmitted ELF form, and its counts remain permanently unread. Before this new cohort, the sole output amendment was independently proved and frozen: each of five ELF paths has exactly two complete admissible hashes derived from the 0/8 .rodata section-entry-size field and its recomputed 32-byte GNU BLAKE3 build ID. All other bytes and program headers are exact. This is visible section metadata and build-ID variation; no claim of universal unobservability is made. The rlib, rmeta, path, mode and size rules remain unchanged. See OUTPUT-METHOD.md and finite-output-proof.sanitized.json.

The original native/profile parity remains bound, with four fresh excluded native functional transitions and four freshness checks per arm. Both numbered hosts completed and restored, and all raw checks plus all 32 metric joins passed before either outcome was estimated. No extension, pooling or additional replacement is allowed.

combined.patch reconstructs the nine changed source files on fdd26156. The matched stock Rust 1.99 producer uses identical full Cargo compiler vectors, ThinLTO, opt-level 3, one codegen unit, debug level 1, no incremental compilation and no PGO/BOLT. The pinned SDK12 Rust/Wild used for uv is separate. Correctness includes 16/41 focused tests, the same 50 integration cases on each arm (12 real i686 nightly cases), and four byte-equal paired production diagnostics. Exact identities and recipe are retained in source-and-build.json and build-recipe.sanitized.json.

Private host, environment, output binaries and original raw records remain outside this portable packet. Sanitized protocol and finite-output proof use reversible task, home and host placeholders. A new capture requires fresh actual context/output admission and separate execution authority. This cumulative benchmark creates no additional source PR.

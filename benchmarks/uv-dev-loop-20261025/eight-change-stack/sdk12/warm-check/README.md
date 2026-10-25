Eight-change cumulative Cargo stack: warm dirty check

This private portable packet compares a matched rebuild of SDK12 Cargo source fdd26156 with one combined tree containing Cargo #231–235, #237, the two-choice registry-cache policy and the formatted single-parse change. The baseline is source-matched; it is not the literal shipped SDK12 Cargo executable. Both builds embed fdd26156. The exact combined tree is 8a4b0c3cb9bafb6a04510366bbaf011502122418.

| Machine | Fewer Cargo-parent instructions | 99% interval | Wins |
| --- | ---: | ---: | ---: |
| Host 1 | 11.1925191106% | 11.0202212882% to 11.2756097012% | 8/8 |
| Host 2 | 11.2742756692% | 11.2583952188% to 11.2958619107% | 8/8 |

Each two-sided exact sign-test p value is 0.0078125. The two fixed balanced eight-pair orders are inverses, with bootstrap seeds 20261025321 and 20261025322 and 200,000 paired draws per machine. Both lower bounds exceed the registered 1% gate. The results are unpooled and are not a sum of earlier PR gains.

Run the standalone numerical replay from this directory:

```sh
python3 -I -S -B reproduce.py
```

It authenticates all 32 complete sanitized profiles and reconciles final instructions, self costs, stderr-derived counts, gzip/raw identities, orders and the exact statistical summaries. Every non-path profile byte is preserved. Only command and path labels are replaced; call edges and instruction records remain available for attribution. CORE-MANIFEST.json authenticates the numerical core; the enclosing private manifest also authenticates the provenance files.

The metric is instructions in the complete Cargo parent and all its threads. Rust compiler, linker, build-script and other children are uninstrumented. This is not whole-command elapsed time. The separate test-build and first-use endpoints have no results in this packet, and no break-even claim is made yet.

The workload is uv 3d82a6ad5a7eab8c68236553b7846517767c4b61 with the prospectively fixed equal-length five-byte ordinary-comment edit. Both arms have independent source-built native banks. Both original check and test --no-run commands were warmed and proved fresh; restoration repeated both original commands in both arms. No test body executes. The baseline document cache stays absent; the candidate cache stays populated and is fully validated under the exact two-choice placement policy.

Native and instrumented compiler contexts were exact, including all 1,249 ordered argv words and 40 ordered environment rows per captured compiler. Within each arm all admitted metadata bytes were exact. Cross-arm differences were exhaustively localized to generated OpaqueLifetime index permutations: 128 bytes on host 1 and 56 on host 2. Typed decoding checked 87 DefIndex tables, five exact other tables, all 1,135 stable keys, per-item fingerprints, spans and private/public/global hashes. All other bytes were exact; 34 negative controls passed. Each numbered arm still required its single exact output hash.

combined.patch applies to fdd26156 and reconstructs the stated nine-file tree. source-and-build.json and build-recipe.sanitized.json bind the actual matched stock Rust 1.99 producer, identical complete Cargo compiler arguments, ThinLTO, opt-level 3, one codegen unit, debug level 1, no incremental compilation, and no PGO/BOLT. The SDK12 Rust/Wild executing uv is separate and pinned. Actual correctness included 16/41 focused baseline/candidate tests, the same 50 integration cases on each arm including 12 real i686 nightly cases, and four byte-equal paired production diagnostics.

Protocol and recipe redaction only substitutes task paths, home/user and host labels with reversible placeholders. Private raw host/process/environment records are retained outside this packet. A fresh capture additionally requires independent banks, fresh native/profile/output admission and explicit execution authority. This cumulative benchmark does not create another source PR.

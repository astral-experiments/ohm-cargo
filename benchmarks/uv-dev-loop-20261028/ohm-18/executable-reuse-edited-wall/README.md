# Cargo executable reuse on two edited uv checkouts

Both Cargo drivers started from independent copies of the same warm library in each checkout. They built and restored a real uvx edit before timing. The candidate extends the unused package-library check to binaries. Both drivers used the same Wild jobserver build, released rustc and target standard library. The first checkout changed a Homebrew predicate, the second changed its upgrade instructions.

The candidate removed one rustc and one Wild invocation from each build and two of each from test compilation. Neither command qualified on both edits. The original independently seeded attempt stopped before timing because the library metadata differed. The shared-cache study retained all 192 commands. Its first supervisor rejected 297 already-exited children after both postflights. The packet preserves that rejection, the verified return of both scratch targets, and the original timings.

We withdrew the candidate after a separate native-link fixture reproduced a stale ordinary binary and test harness. Changing the native function from 1 to 2 left the candidate returning 1, while control Cargo and clean candidate builds returned 2. This happened both with a compiler wrapper and with ordinary Cargo using a transitive build-script search path and Rust `#[link]`. In all 12 captured uvx compilations, `zstd-sys`, `aws-lc-sys` and `tikv-jemalloc-sys` supplied native search paths. [All 16 driver comparisons and the uvx search paths](native-link-correctness.json)

| Checkout | Command | Control | Paired median saving | Median interval | Wins | Sign / order p |
|---|---|---|---:|---|---:|---:|
| Initial | `cargo build` | Matched rebuild | -0.25% | -4.82% to +6.37% (97.73%) | 12/24 | 1.0000 / 1.0000 |
| Initial | `cargo test --no-run` | Matched rebuild | -2.60% | -6.74% to +2.00% (97.73%) | 9/24 | 0.3075 / 0.4136 |
| Replica | `cargo build` | Matched rebuild | -1.46% | -15.91% to +6.55% (97.73%) | 11/24 | 0.8388 / 1.0000 |
| Replica | `cargo test --no-run` | Matched rebuild | -1.56% | -7.63% to +4.04% (97.73%) | 9/24 | 0.3075 / 0.3707 |

A file-name lookup overlapped two initial-build commands in blocks 18 and 19. The table retains all samples. Dropping both affected blocks gives a paired median saving of 0.47%.

Every timed test-compilation command prepared the same 72 test executables. No uv tests ran.

[192 wall times](samples.csv) · [Paired comparisons](numeric-results.json) · [Process and artifact checks](audit.json) · [Original receipts, assignments and standalone scorer](observations.zip)

To repeat the numerical and product audit from a fresh directory, run

```sh
unzip observations.zip
python3 -I -B protocol/rescore-edited-native.py . r18-proof-common-seed
```

# Preserve unset loader paths: uv native-build → first-check evidence

Preserving an absent loader-path variable lets Ohm reuse native dependencies when a developer runs `cargo check` after `cargo test --no-run`. On the pinned, unchanged uv workspace, the independent production-settings confirmation used **38.54% less wall time** (99% paired-bootstrap CI **36.33%–40.72%**). Median time fell from **36.073 s to 22.219 s**. All 12 pairs improved; exact two-sided sign-test p = **0.00048828125**. This measures the first check after building tests, with the test executables never run.

The source change preserves an unset loader path instead of injecting an empty value. It retains explicit empty values, generated proc-macro search paths, Cargo environment precedence, and conservative driver-shadow rejection. The exact three-file patch is [loader-path-v2-final.patch](build/loader-path-v2-final.patch), applied to [PR175 commit efc8b515](https://github.com/astral-sh/ohm-cargo/commit/efc8b51502f8a8d1fe76997dc984481edde2740e). The published [code commit 64343228](https://github.com/astral-sh/ohm-cargo/commit/64343228c0ab13c89e0c6a78e1c11ed2e7c60b6d) has resulting source tree `fce366b238ace1b2021808769d857aa56eadcd56`; [publication verification](code-publication.json) binds its exact parent, patch and three-file scope.

| Recorded result | Baseline | Candidate |
| --- | ---: | ---: |
| Median first-check wall time | 36.073 s | 22.219 s |
| Median child user + system CPU time | 248.469 s | 136.126 s |
| Crate rustc invocations, every sample | 500 | 174 |
| Metadata-only rustc invocations, every sample | 499 | 173 |
| Actual build-script invocations, every sample | 1 | 1 |
| Fresh compiler artifacts, every sample | 149 | 479 |
| Native producer provenance entries | 432 | 432 |
| Producer `loader_injected` | `true` | `false` |
| Producer `compiler_search_directories` | `[""]` | `[]` |

Child CPU time fell **45.16%** (99% CI **43.84%–46.58%**). Exactly **326 crate compiler invocations were avoided in every pair**. Cargo's 54 `build-script-executed` JSON records per sample include cached output; the verbose command audit establishes that only one build script actually ran. [Analysis](confirmation/analysis.json), [mechanism counts](confirmation/loader-mechanism.json), and [all samples](confirmation/samples.csv) preserve those distinctions.

The design was frozen before production seeding: 12 balanced randomized pairs, six of each order, no measurement warmups, one check per variant per pair, seed `2026102126`. Each command began from an exact restoration of its variant's naturally generated native-only seed, at the same canonical executable, target, shared-cache, and package-home paths. Copying, checksum verification, and restoration were outside timing. All 24 commands and all 24 verified rsync restorations succeeded; no full-copy fallback, exclusions, interim effect inspection, or optional extension occurred. Both order groups improved (AB 1.6053×, BA 1.6491×). [Frozen protocol](protocol/loader-production-confirmation-protocol.json), [fixture config](fixture/paired.json), [journal](fixture/journal.jsonl), and [seed review](fixture/loader-production-seeds-reviewed.json) provide the audit trail.

These were matched **production-settings, non-PGO** Cargo builds: `all-static,ohm-defaults`, ThinLTO, one codegen unit, dev channel, debug information stripped with allocated ELF sections verified unchanged. They used stock Rust 1.99.0 to build Cargo, rather than the release bootstrap stage1 compiler. The `all-static` feature still leaves libc, libm, libgcc_s and the loader dynamically linked; their hashes and the CA bundle hash were frozen. [Build records](build/) contain exact flags, compiler identities, source trees, full/stripped binary hashes, source patches, and build logs. Neither binary nor the large native artifact trees is stored in Git.

| Immutable input | Identity |
| --- | --- |
| uv commit | `3d82a6ad5a7eab8c68236553b7846517767c4b61` |
| Cargo embedded base commit, both measured binaries | `5e5d271d763d7beb38b48755e22bd59e93f02b97` |
| Baseline source tree, with PR175 applied | `3d67bfb965bc0b6452ab78205045c5154db0acf7` |
| Candidate source tree | `fce366b238ace1b2021808769d857aa56eadcd56` |
| Baseline stripped binary SHA256 | `63495905e7b0b11ad99fa4c2c2674e43657b9902a2e3142ef735fd83efa44cf8` |
| Candidate stripped binary SHA256 | `12b7f73177fcfbe5704d5237fb8b0ce79d868c002f5954012aa272ea56fc9869` |
| Ohm rustc commit | `6d4a7ee3200c5311112d433cb9d1da4a2630a66f` |
| Ohm rustc executable SHA256 | `6109cff145371a50c4f62b61908d2ffbf6d259b180c8effde07baa426aab682a` |
| Ohm rustc driver SHA256 | `a3a5d8cc86af464504170220d142c4ea1129434e2d5e741755feec6f9f35a436` |

The host was Linux x86_64/glibc 2.39 on an AMD EPYC-Milan VM, 32 logical CPUs and approximately 98 GiB RAM. Commands were pinned to CPUs 0–7 with eight Cargo jobs. The [run manifest](confirmation/manifest.json) records the full host, environment, runtime input hashes, balanced order, and unchanged before/after hashes. The batch ran from 04:05:45 to 04:34:37 UTC on 2026-10-21.

The final Cargo build-directory suite reported [96 passed, 0 failed, 4 ignored](correctness/loader-v2-final-build-dir-tests.log). The restoration helper's [31 focused Python checks passed](correctness/loader-delta-tests.log), covering snapshot immutability, stale check removal, content/mode/ns-mtime/link verification, external hardlinks, symlink/mount escapes, corruption, and runlist validation. The frozen [helper and tests](tools/) are included.

The measured effect is conditional on **one fresh native seed per variant**, replayed across 12 timing pairs; it is not 12 independent native builds. The full checksum pass warms artifact pages. Package-download bookkeeping persists while target/shared compiler state is restored. These results therefore characterize a warm-artifact native-build → first-check workflow on this host. They do not establish a cold-storage result, a test-build speedup, a universal cross-platform gain, or the effect of a PGO-built release.

The earlier normal-build one-pair diagnostic is retained in [a separate archive](archives/normal-build-n1-diagnostic.tar.gz) and [summary records](diagnostic-only/). It used different Cargo build settings, original full-copy restoration, and the opposite producer order. Its observed 34.04% wall-time reduction was mechanism screening only; it was never pooled into the 12-pair confirmation or treated as statistically significant. The production run used fresh native seeds in candidate-then-baseline order.

[REPRODUCE.md](REPRODUCE.md) explains verification, analysis replay, matched builds, and a new fixture. [archives.json](archives.json) maps both complete byte-preserving archives to external per-file manifests and the original seals. The production archive contains all 156 originally sealed files (250,231,697 bytes), plus its original seal; the diagnostic archive contains all 57 originally sealed files (91,952,595 bytes), plus its original seal. This includes raw native/timed logs, full runlists, native inventories, per-sample restore evidence, configuration, provenance, and analysis. Browsable copies retain their original bytes. The historical protocol's “pending assets” wording records when the design was frozen; [initialization](fixture/loader-production-initialized.json) and [seed review](fixture/loader-production-seeds-reviewed.json) record their subsequent binding and verification before timing.

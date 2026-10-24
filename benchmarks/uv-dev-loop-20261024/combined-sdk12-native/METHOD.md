# Method and reproduction

The metric is elapsed integer nanoseconds around the complete native Cargo process, including its selected compiler and linker children. No profiler, syscall tracer, compiler wrapper, test execution, external artifact validation, bank copying, or statistical analysis runs inside that interval. Cargo and compiler work remains inside the clock. The commands are:

```sh
cargo -Zohm-defaults=yes check --locked --offline -j 8
cargo -Zohm-defaults=yes test --no-run --locked --offline -j 8
```

The fixture is uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61`. Each pair uses the same equal-length, semantically inert comment edit in `crates/uv/src/lib.rs` for both arms. Baseline and candidate have independent warmed runtime, target, shared-cache and package-home banks. A bank is activated at the same physical paths for its turn. Each arm first compiles the BEFORE comment outside the clock, then compiles the AFTER comment inside the clock. Diagnostics and outputs are checked afterward. Original source restoration and convergence of both original commands occur at the end of the block, followed by traced proofs that both commands are fresh in both banks. There is no original-source convergence command inserted between arms.

Each endpoint has two prospectively specified 24-pair blocks, with 12 AB and 12 BA pairs in each. The second block reverses the first block's orders. `protocol.json` retains every order and seed. Each block must separately have a strictly positive 99% bootstrap lower bound for time reduction, exact two-sided sign-test p < 0.01, and geometric speedup > 1 in both order strata. A valid failed block closes its endpoint. There is no pooling, additional sampling, outlier removal, or retry of a valid failure. Check and test-build are separate endpoints: a failed check block does not suppress the prespecified first test-build block.

The paired statistic is the geometric mean of baseline/candidate time ratios. Its reduction form is `1 - 1 / geometric_speedup`. The percentile interval uses 200,000 resamples of the paired log ratios, with the fixed seed for that block. Median times are descriptive; the gate does not test the ratio of the two medians. `paired_stats.py` retains the exact three relevant functions from the frozen analysis helper. `replay.py` converts the original integer nanoseconds to seconds in exactly the same way as the original analyzer and verifies all published statistics and stop decisions:

```sh
sha256sum -c CHECKSUMS.sha256
python3 -I -B replay.py
```

This is saved-data analysis reproduction. Re-measuring requires fresh task-owned source, runtime and bank paths, pinned build inputs, and new preflight/output bindings established before collecting effects. Historical namespace and output hashes are fixture-specific, not portable acceptance criteria. The private collection retains the complete command streams, row records, host observations and restoration evidence; the public CSV retains every valid paired duration without rounding or filtering.

`identities.json` identifies both measured Cargo binaries and compiler trees. The candidate combines Cargo #231 and #232 with Rust #218; it does not contain Cargo #233. `combined-cargo.patch` applies to Cargo `fdd26156be98618e2e01a9e02703edac71b79a35`; `rust-lazy-worker-caches.patch` applies to Rust `f93a752e3de7404107ea5908d65c8832aee5625a`. Their full trees and patch hashes are retained. These are matched optimized developer builds, not a comparison against the shipped compiler distribution. The compiler build uses the included parameterized bootstrap configuration and recipe, matching std for each arm, and the same physical source/build paths.

The Cargo producer used the official SDK12 toolchain, with these actual profile settings (replace task-specific paths yourself):

```sh
export CARGO_PROFILE_RELEASE_OPT_LEVEL=3
export CARGO_PROFILE_RELEASE_LTO=thin
export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
export CARGO_PROFILE_RELEASE_DEBUG=1
export CARGO_PROFILE_RELEASE_STRIP=none
export CARGO_PROFILE_RELEASE_INCREMENTAL=false
export CARGO_INCREMENTAL=0
export LIBZ_SYS_STATIC=1
export CFG_RELEASE_CHANNEL=dev
cargo -Zohm-defaults=no build --release --locked --offline --bin cargo \
  --features all-static,ohm-defaults -j 24 --message-format=json-render-diagnostics -v
```

Both Cargo arms used the same producer configuration and common embedded base commit; section-preserving stripping retained all 31 allocated ELF sections. Source-tree identities distinguish the candidate despite common embedded version metadata. The Rust runtimes have 74 recorded files per arm, with 73 byte-identical shared files and only the compiler driver differing. Runtime and source identities are checked before timing; no build or transfer overlaps a native block.

Admission checks the selected host, kernel, task-owned paths, immutable binaries, controls, original source, lockfile and source mode. Workload affinity is CPUs 0–7, with eight Cargo jobs; the controller is on CPU 8. Entry requires three one-second intervals with aggregate CPU busy fraction at most 10%, plus no detected competing named build/profiling process intersecting CPUs 0–7. The process check also runs immediately before and after every timed call. These finite observations are not continuous system-wide interference monitoring.

Excluded per-PID traces establish matching compiler roles and each ordered argument/environment vector across arms, with only the declared namespace substitution and dead `CARGO_MAKEFLAGS` omission. Check has one selected compiler role and two retained outputs per arm; test-build has six roles and eight outputs, including all five ELF executables. Every timed command must retain its admitted diagnostics and output identities. Native payload checks and finite per-arm whole-file ELF hashes are retained; arbitrary unseen hashes are rejected. This does not claim a complete cross-arm Rust-metadata equivalence proof.

Native dep-info contains the checksum of the deliberately edited source. The guard independently hashes the actual source through a pinned stdin-only BLAKE3 helper, and validates the reference checksum against a reconstructed authenticated preflight source. It derives the expected dep-info by replacing only the exact 64 lowercase hexadecimal checksum characters. Source length, path, mode, all remaining dep-info bytes and output hashes remain checked. No broad metadata or ELF mask is used.

Host5 was retired before any valid block existed. Earlier setup/quiet-entry failures and a later cohort rejected by the post-command competing-job guard remain invalid; the latter retained 11 observations whose effects were never opened. Both banks were restored. No host5 duration enters this package, either endpoint, or a pooled estimate. Perf1022 was chosen for both endpoints on infrastructure availability before learning effects; host5 received no subsequent timing attempt.

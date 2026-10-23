# Reproduction and audit

This package supports two distinct activities: recomputing published raw-profile arithmetic, and reconstructing the source/build/workload method for a new, separately admitted study. Private environment/process records are omitted. Public arithmetic alone cannot replay the original operational admission checks, and a new run does not inherit the original qualification.

[The portable worked example](reproduction/WORKED-EXAMPLE.md) gives actual rebuild commands and a one-arm invocation using the existing fixture, atomic installer, and command runner. It identifies the fresh-fixture prerequisites and does not require the old private seal chain.

## Verify the published arithmetic

After the final package is frozen, run from its root:

```sh
sha256sum -c SHA256SUMS
python3 reproduction/recompute.py
```

The verifier checks each compressed file identity, the full decompressed identity, a terminated single-part Ir profile, final/header counts, and the sum of self costs with inclusive call costs excluded. It recomputes only bound accepted stages. Null stage slots stay pending. Retained stderr equality and the operational gates are authenticated outcomes from the original review; raw stderr and private context records are not inputs to this public verifier.

The four statistical function bodies in `reproduction/paired_statistics.py` are exact extractions from the pre-existing frozen helper with SHA256 `50d0cb2d4f595ccfa72d463fedb3ff4dadf9dfc1446c749d482d9ede8418c7cf`. Confirmation analysis calls `paired_count_statistics` with the fixed 99% interval, 200,000 resamples, and per-block seed. Discovery uses only its two-pair advance rule. Native sanity uses only its fixed slowdown/loss blocker, not a positive wall-speedup test.

The gzip files contain complete, unchanged raw profile bytes, including their intrinsic command/source/object paths. `discovery/results.json` records both compressed and uncompressed hashes, final counts, header differences, and known allocator fallback warnings.

## Reconstruct source and build identity

The source candidate is a single-parent change from cfd, with the exact tree/patch hashes in [source/identities.json](source/identities.json). To reconstruct the production source layout, use an isolated Ohm Cargo checkout with Git HEAD fixed at embedded commit `5e5d271d763d7beb38b48755e22bd59e93f02b97`. Apply `source/baseline-from-embedded-head.patch` for the baseline. Apply `source/candidate.diff` on top for the candidate. This preserves the common embedded build metadata while reproducing the two recorded source trees; do not build directly from two different Git HEADs and assume the resulting metadata matches.

Use an existing stock Rust 1.99.0 toolchain and the recorded static native tools. `Cargo.toml` does not supply the measured release profile. With `EVIDENCE_BUILD` and `EVIDENCE_STOCK` set to the task-owned build root and existing stock toolchain, the retained producer settings are explicit:

```sh
env CARGO_HOME="$EVIDENCE_BUILD/cargo-home" CARGO_TARGET_DIR="$EVIDENCE_BUILD/target" \
  RUSTC="$EVIDENCE_STOCK/bin/rustc" RUSTDOC="$EVIDENCE_STOCK/bin/rustdoc" \
  PATH="$EVIDENCE_STOCK/bin:/usr/bin:/bin" TMPDIR="$EVIDENCE_BUILD/tmp" \
  CARGO_BUILD_JOBS=8 CARGO_INCREMENTAL=0 CARGO_TERM_COLOR=never \
  CARGO_PROFILE_RELEASE_OPT_LEVEL=3 CARGO_PROFILE_RELEASE_LTO=thin \
  CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 CARGO_PROFILE_RELEASE_DEBUG=1 \
  CARGO_PROFILE_RELEASE_INCREMENTAL=false CARGO_PROFILE_RELEASE_STRIP=none \
  CFG_RELEASE_CHANNEL=dev LIBZ_SYS_STATIC=1 \
  SSL_CERT_DIR=/usr/lib/ssl/certs SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
  "$EVIDENCE_STOCK/bin/cargo" build --release --locked --bin cargo \
  --features all-static,ohm-defaults -j 8 -v
```

The release profile is opt-level 3, ThinLTO, one codegen unit, debug level 1, no PGO, no incremental, and no build-time stripping. The release-channel value is `dev`, and zlib is static. These are producer settings, not a request to disable uv's runtime incremental compilation. The measured pair used the same physical source, target, and task-owned Cargo home; the candidate reused dependency artifacts. The baseline producer used CPUs 0–31 and candidate producer CPUs 8–23. The baseline binary was preserved, not rebuilt for this pair.

The complete build identities and nineteen static inputs are in [build/identities.json](build/identities.json). Compiler-relevant settings matched the retained baseline revalidation, except declared noncompiler transport/tool-call metadata; historical full raw environment equality is unavailable. A portable recipe does not promise byte-identical output on another host.

The measured binaries were made with `objcopy --strip-debug FULL STRIPPED`. The full and stripped SHA256/size pairs and the retained allocated-section identity vectors are included. Verify all allocated sections are unchanged; do not substitute a different stripping mode or an installed Cargo binary.

## Reconstruct the workload method

Use a task-owned copy of uv `3d82a6ad5a7eab8c68236553b7846517767c4b61` and the already-installed pinned Ohm `1.99.0-6` compiler/linker. Keep one physical target/cache and active Cargo path for both variants. No tool upgrades, global configuration changes, ownership changes, or trust/cache-policy relaxations are part of the method. Tool hashes are in [runtime-identities.json](runtime-identities.json).

The existing frozen `reproduction/dirty_fixture.py` appends a deterministic non-doc comment with before/after states of equal length. Its before-side preparation command must complete outside the scored interval. Its after-side source edit then induces the measured build. Restore original source bytes and active Cargo bytes after each sample. Run the original command for convergence **once at stage end**, not after each sample; extra convergence commands would change cache history. The eight-pair native stage has 37 command records: four excluded preflight/preparation calls, sixteen sample preparations, sixteen timed calls, and one final original-command convergence.

The uninstrumented workload command is:

```sh
taskset -c 0-7 ACTIVE_CARGO -Zohm-defaults=yes test --no-run --locked --offline -j 8
```

The accepted compiler-argv preflight uses the existing execve-only trace parser and confirms two source compilations plus four link-only invocations per variant. It is not a timed/profiled observation. Four cached-relink output identities are guarded; the precise two-hash exception in [PROTOCOL.md](PROTOCOL.md) is capture-specific and must not be generalized. The ordinary library-test executable is outside these four output guards.

For Ir, the existing Callgrind 3.22.0 invocation inserts the profiler after `taskset`:

```text
taskset -c 0-7 VALGRIND_BIN --tool=callgrind --trace-children=no \
  --extra-debuginfo-path=PINNED_VALGRIND_DEBUG \
  --callgrind-out-file=OWNED_PROFILE ACTIVE_CARGO \
  -Zohm-defaults=yes test --no-run --locked --offline -j 8
```

The controller passes the pinned `VALGRIND_LIB`, preload normalizer, and `OHM_BENCH_NORMALIZE_VALGRIND_ENV=1` through the existing controlled profile context. The exact normalizer source is retained as `reproduction/ohm-valgrind-env.c`; its source/binary hashes are pinned. This prevents profiler-only environment changes from changing child compilation identities. Ordinary workload context, source, tools, arguments, and namespace/rustc-info guards remain fixed. No compiler/linker child is instrumented.

Follow the complete fixed stage orders and fresh-cohort gates in [protocol.json](protocol.json). Instruction cohorts retain all host observations under the prospective amendment; native timed calls retain strict quiet checks and no profiler. Do not pool discarded attempts or discovery into confirmation, extend a cohort, tune source after seeing effects, or infer whole-build wall time from Cargo-only instructions.

Numerical replay needs Python 3 and the files in this folder:

```sh
python3 -I -S -B reproduce.py
```

The reader authenticates the core manifest and all 32 compressed/full profiles, requires one complete final Ir record, sums every self-cost record, joins the retained stderr counter, rejects brk-overflow warnings and reproduces both independently seeded 200,000-draw paired percentile bootstraps. Five numerical/reader function bodies and the raw sanitizer are byte-identical to the accepted predecessor. The full function/call/cost stream is retained; path labels are deterministic SHA-256 substitutions. A profile's header summary is retained separately from its authoritative final total.

The exact source baseline is `astral-sh/ohm-cargo` commit `fd7a25d7bed7503d628c90879ba265e173343b28`, tree `ca7507690099e7523754432ae09abb07b969c962`. Applying `candidate.patch` with `git apply --index` produces tree `5fbb37f329d5c185e95511832854596937899019`. `source-and-recipe.json` binds the patch and all three changed blobs. Keep HEAD at the baseline while building both arms so their embedded commit/version remains identical. Do not stack unrelated changes.

In a clean checkout, provide `STOCK_BIN` for the recorded stock Rust 1.99.0 compiler and a new absolute `BUILD_ROOT` containing a checksum-verified offline Cargo home, then run:

```sh
bash /path/to/this/folder/build-cargo.sh
```

The helper uses one physical source/target directory, `all-static,ohm-defaults`, ThinLTO, one codegen unit, opt-level 3, debug 1, no incremental/PGO/BOLT and 16 jobs on CPUs 0–15. It preserves full binaries and removes only debug data for the measured copies. The actual experiment independently authenticated all allocated sections before/after stripping, unchanged tools/dynamic libraries, matching embedded versions and the compiler argument vectors. Different absolute build paths or system tool versions can change binary bytes; the recorded binary hashes identify the actual measured pair. `correctness.json` contains all seven focused invocations, 40 passes with zero ignored, and the separate 470-manifest typed/metadata/ignored-key corpus proof. The corpus files can be reconstructed from the official locked crates and SHA-256 rows in `corpus-02-index.json`.

The workload compiler is the published SDK12 bundle pinned in `source-and-recipe.json`, not the stock producer compiler. Keep its rustc, driver, rustdoc and Wild bytes fixed. Use uv commit `3d82a6ad5a7eab8c68236553b7846517767c4b61`, its exact Cargo.lock and offline packages. Create independent source-only target/shared/package-home banks per arm and VM; do not import compiled state or candidate cache records. Use the same canonical active paths and rename activation. Check every applicable Cargo configuration and preserve the original live jobserver.

The ordinary command is:

```sh
cargo -Zohm-defaults=yes check --locked --offline -j 8
```

`dirty_fixture.py` creates the exact equal-length non-doc comment transition from `state=before` to `state=after_`, changing five bytes without changing Rust tokens or source positions. Warm and freshly trace the original command twice per arm, then collect separate excluded native and profiled dirty references. The admitted compiler vectors and usable environment must match the native command; only dead jobserver descriptor values receive the already-declared treatment. Keep every warning and each arm's exact rmeta output hash. Native/profiling child equivalence and freshness are required; `one-profile.sh` is only the parameterized invocation core, not a replacement for these controls.

Use the recorded Ubuntu Valgrind 3.22 source package and its sole Linux brk-reservation change in `profiler/large-brk.patch` (8 MiB to 512 MiB). Apply the distribution packaging first; configure/build the same core with and without that patch. `source-and-recipe.json` pins both cores, the actual ELF launcher and adapter. The held-out `profiler/ir.S` control yielded 51,035 and 51,089 Ir with the expected delta 54; `profiler/brk.S` checked the documented reservation boundary. Build `ohm-valgrind-env.c` as the same preload adapter and authenticate its recorded binary. The adapter removes instrumentation settings before the native children; `--trace-children=no` includes only Cargo and its threads. Every brk overflow warning is disqualifying.

Each endpoint fixes two independent eight-pair blocks, inverse orders, with the schedules/seeds in `source-and-recipe.json`. Warm seeds are 20261025241/20261025242; cold seeds are 20261025243/20261025244. Both complete/restored raw gates precede all 32 metric joins and either estimate. Warm requires 8/8 wins, exact two-sided p < .01 and lower 99% reduction > 1% on each machine. Cold accepts either sign descriptively. There is no pooling, extra sample, replacement or valid-result retry.

For warm commands, baseline cache absence and actual candidate committed contents are checked before and after. For cold commands, retire only the candidate document cache after the untimed before-build, retain it, prove absence, run the same endpoint, then retain the new committed inventory. Do not clear compiler target/shared state. Report first-use costs and per-host amortization together with the warm result. Committed-byte counts are not total-write counts.

This private packet does not authorize new workloads or publication. Native elapsed checks are a separate endpoint with their own A/A noise admission, complete child completion and frozen paired rules. A replicated whole-command regression blocks a PR even if parent instructions improve.

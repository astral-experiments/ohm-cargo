Replay the published numerical evidence with Python 3:

```sh
python3 -I -S -B reproduce.py
```

The parser, sanitizer and statistical function bodies match the accepted predecessor. It authenticates every compressed and decompressed profile, joins final Ir with the sum of self costs and stderr, rejects incomplete parts and brk warnings, and recalculates both fixed 200,000-draw intervals. Header summaries remain separate from final totals.

For matched source builds, use a clean `astral-sh/ohm-cargo` checkout at `fd7a25d7bed7503d628c90879ba265e173343b28`. `baseline.patch` produces the #237 production tree `5fbb37f329d5c185e95511832854596937899019`; `candidate.patch` then produces `eba53f95bcf93818dc07490b5b8867d75a683cfd`. Keep HEAD fixed so both embedded versions match. Set absolute `STOCK_BIN` and fresh `BUILD_ROOT` paths, seed its `cargo-home` with verified locked archives/indexes, then run:

```sh
bash /path/to/evidence/build-cargo.sh
```

The recipe uses stock Rust 1.99.0, one physical source/target directory, `all-static,ohm-defaults`, opt-level 3, ThinLTO, one codegen unit, debug 1, no incremental/PGO/BOLT, and 16 jobs on CPUs 0–15. It keeps full and debug-stripped artifacts. All 31 allocated ELF sections per arm were unchanged by stripping. Other paths or tool versions can change rebuilt hashes; `source-and-recipe.json` identifies the actual measured binaries. The eight focused invocations passed 22 baseline and 30 candidate cases, with no failures or ignored tests.

The workload uses uv `3d82a6ad5a7eab8c68236553b7846517767c4b61` and the published SDK12 bundle pinned in `source-and-recipe.json`. Keep the SDK rustc, driver and Wild bytes fixed. Create independent source-only source/target/shared/package-home state for each arm and each VM; do not import compiled state. Use matching canonical active paths with rename activation and preserve writable Cargo-home coverage. Both arms enable their own registry cache.

The ordinary command is:

```sh
cargo -Zohm-defaults=yes check --locked --offline -j 8
```

`dirty_fixture.py` appends the established ordinary comment and prepares the equal-length `state=before` to `state=after_` transition. It changes five bytes and no Rust tokens or positions. Warm the original command, require traced fresh checks with zero compilers, and collect one excluded native and one profiled dirty reference per arm. Require exact ordered rustc argv/environment and diagnostics, with only dynamic jobserver descriptor values treated as declared. Keep each arm's full rmeta identity. Restore source and compiler state after every sample; the next sample converges the same original state. `one-profile.sh` is the parameterized invocation core, not a substitute for these admission/restoration gates.

The profiler is pinned Valgrind 3.22 with the documented Linux brk reservation changed from 8 MiB to 512 MiB. Apply the distribution package and `profiler/large-brk.patch`; all other profiler files and aliases stay fixed. The shipped `profiler/ir.S` and `profiler/brk.S` controls qualified exact instruction totals and both heap boundaries independently on each VM. Build the recorded `ohm-valgrind-env.c` preload adapter. It removes instrumentation settings before native children. `--trace-children=no` counts the Cargo parent and all its threads. A brk warning invalidates the observation.

Prespecify the two mirrored eight-pair schedules and seeds in `source-and-recipe.json`. Authenticate both complete restored blocks before decoding metrics, validate all 32 profiles before either estimate, and apply each machine's 8/8, p < .01, lower-99%-bound >1% gates independently. Preserve every attempt; do not retry or extend a block. The two loader pilot profiles are eligibility data only; the two replica preflight profiles remain unread. No cold-cache performance or native elapsed result is inferred from these profiles.

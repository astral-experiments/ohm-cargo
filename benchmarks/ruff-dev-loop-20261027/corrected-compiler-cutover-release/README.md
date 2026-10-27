# Foreign crate metadata on a retained bridge

These are compiler correctness controls for Ohm Rust #233 on x86-64 Linux. Every stale-bridge case uses a physical copy of the prior bridge rlib. New and retained callers are compiled from identical Rust source. The final confirmation uses the same crate name, paths and compiler arguments in both directions, retires its private Cargo build state, and requires Cargo to report every successful caller compilation as dirty. A native return of zero must print `7`.

The exact source and compiler selection are in `scripts` and `drivers`. `source` in each summary row identifies its original fixture directory. The `raw` directory contains Cargo JSON, compiler stderr, independent rustc hygiene dumps, producer metadata headers and the actual invocation list. Compiler diagnostics and failed cases are retained. No test binary or external dependency is distributed here.

## Independent controls

- On matched stage-2 compilers, adding a private struct and changing an unreachable private iterator item from `u8` to `i8` makes #232 reject the ordinary bridge with E0460. The original #233 accepts the same stale indices and reports a spurious sizedness cycle. Rebuilding the bridge succeeds for both.
- Enabling a private macro that expands to zero tokens can move `make!` from expansion 2 to 3 without changing the public hash. A clean reconstruction of the producer exposes the released rustc ICE. Building the producer in its existing incremental directory can retain the old self-consistent metadata and mask the issue.
- A nonempty private macro can occupy the old index. The original and regenerated programs both print `7`, yet a stale v5 legacy bridge identifies the public expansion as `noise!`. The raw expansion dump records the distinction.
- The procedure tests a real procedural macro that stamps each generated token with `Span::mixed_site`. Original, stale and regenerated function output have to match independently.

## Reproduce

Run `python3 -B verify.py` from any directory with Python 3.11 or later to verify the per-file hashes and recompute the stored assertions. To repeat the compiler invocations, use a release-compatible Cargo and two matching compiler installations. `make-arm.py` can select stage drivers without copying or hardlinking a toolchain. It records actual dynamic-loader resolution and the driver SHA-256.

```sh
python3 -B scripts/make-arm.py /tmp/old-home OLD_SYSROOT OLD_DRIVER_DIR OHM_CARGO
python3 -B scripts/make-arm.py /tmp/new-home NEW_SYSROOT NEW_DRIVER_DIR OHM_CARGO
python3 -B scripts/matrix.py new-run /tmp/old-home /tmp/new-home
python3 -B scripts/path-probes.py /tmp/new-sdk-run /tmp/old-home /tmp/new-home
```

The matrix allocates CPU lanes 4–5 and 6–7. Set those lists to reserved cores when reproducing elsewhere. The runner creates a new directory beside its script, needs an empty writable cache, and uses the selected rustup homes through ordinary `cargo +ohm` or `cargo +ohm -Zohm-defaults=no`. Absolute paths, timestamps and rlib bytes can change across clean recreations. The oracle checks within-run public hashes, explicit stale-binding diagnostics, runtime output and macro identity.

## Supplemental compiler controls

Four ordinary writer cases reorder source declarations, side modules, included files, and two macro-generated includes. In each the actual public definition index moves, the full crate hash changes, and the stale bridge is rejected with E0460. Regenerated bridges compile in all four cases. The `order` directory includes both compiler HIR dumps, ordinary metadata headers, compile commands and diagnostics.

Two procedurally generated native programs load their compiler's own macro library and print `7`. The old reader rejects the current user macro dylib with E0514, and the current reader rejects the old user macro dylib with E0514. The macro token uses a real mixed-site span; the `proc-abi` directory includes sources, compiler diagnostics and both native stdout files.

## v7a-stage2 outcome

The current metadata writer preserves the foreign expansion identity across zero-token edits and real mixed-site procedural macros. Rebuilding a stale ordinary bridge resolves its private DefId change. All generated old user metadata is rejected with E0514. The old compiler's retained all-ordinary crash remains in the controls.

The selected sysroot directory is a trusted installation. A physically present old ordinary library and a coherent old dependency graph load. An outside symlink resolving inside also loads. A library in a directory with the same prefix, a symlink resolving outside, and an old SDK bridge with an external old dependency get E0514. A current ordinary library has the same full and public crate hash as the old original and works directly. The old SDK bridge still rejects it with E0463 in either the physical SDK directory or an external directory. These synthetic membership checks use an isolated selected sysroot and preserve the real installed toolchain.

The optimized driver `3e4b168966e111b52ad1a942d364ec1335cf1cfa994f4208b0909ca215b589d2` contains the compiler tree `9e52c043880793c40fedf3eb137a231479d9adba` shared by fix `3a9e8ee19f74e4d0860da3ed60f9bb663332ec19` and PR head `66815c41574c8c597fa06af78a38c4c40ca30a84`. The old stage-2 baseline is original #233 (55e123a9). The separate #232 comparison (051b9d3f) isolates the private DefId regression.

Four additional fixed-path ordinary compilations alternate the selected old and current compilers on the same source and incremental directory. All three incremental file families have the version sequence 0, 1, 1, 0. The emitted `lib.rmeta` member for each epoch reproduces byte for byte on return to that compiler. The full rlibs differ across reproductions, so the archive records their hashes separately from the verified metadata members.

# Ohm Cargo

An experimental fork of [Cargo](https://github.com/rust-lang/cargo), Rust's package manager and
build tool, for [Ohm](https://github.com/astral-sh/ohm): a Rust toolchain designed for fast, highly
parallel local development.

**Warning:** Ohm includes backported and experimental optimizations that may be unsound. All Ohm
code changes, PR summaries, and additional documentation were authored entirely by GPT-6 Astra in
Codex.

Use Ohm only for local development, and at your own risk. Never use it for production builds or
releases, and always verify your work with the official Rust toolchain.

Ohm defaults enable native ThinLTO object caching for supported Linux builds. Cargo manages
`<build-dir>/.ohm-thinlto-cache`, pruning it after builds to 2 GiB or 100,000 objects and expiring
entries unused for 30 days. Concurrent builds can temporarily exceed these limits. Compiler
wrappers, unsupported compilers, and unsupported backend configurations retain normal compilation.
Optimization settings, including the selected LTO mode, are preserved.

Use `cargo +ohm -Zohm-thinlto-cache=no build --release` to disable automatic caching, or
`-Zohm-defaults=no` to disable all Ohm defaults. `[unstable] ohm-thinlto-cache = false` provides the
same targeted opt-out in Cargo configuration. An explicit rustc `-Zthinlto-cache=PATH` keeps its own
directory and eviction policy.

## Shared frontend stages

Ohm defaults enable frontend query reuse for compatible debug checks and builds
with a supporting compiler:

```sh
cargo +ohm check
cargo +ohm build
```

Cargo preserves separate checked and built artifacts while giving compatible
units the same compiler identity and incremental directory. Source, feature,
profile, dependency, and build-script inputs remain tracked. Reuse excludes release and test targets, procedural macros, build scripts,
explicit codegen backends, and workspace compiler wrappers. It falls back to
ordinary compilation when the compiler does not support the experiment.

Use `-Zohm-shared-stages=no` on both commands to opt out, or set
`[unstable] ohm-shared-stages = false` in Cargo configuration. `-Zohm-defaults=no`
also disables automatic stage sharing; an explicit `-Zohm-shared-stages` enables
it independently of the other Ohm defaults.

The first native build can reuse frontend results from a preceding check. Once a
native build exists, subsequent builds restore its saved graph and query cache;
checks restore their own saved state and retain the native work products. Both
paths apply normal incremental validation to changed inputs. Each incremental
session retains at most one checkpoint per stage, removed with the normal build
cache. This uses additional cache space.

## License

Cargo is primarily distributed under the terms of both the MIT license
and the Apache License (Version 2.0).

See [LICENSE-APACHE](LICENSE-APACHE) and [LICENSE-MIT](LICENSE-MIT) for details.

### Third party software

This product includes software developed by the OpenSSL Project
for use in the OpenSSL Toolkit (https://www.openssl.org/).

In binary form, this product includes software that is licensed under the
terms of the GNU General Public License, version 2, with a linking exception,
which can be obtained from the [upstream repository][1].

See [LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY) for details.

[1]: https://github.com/libgit2/libgit2


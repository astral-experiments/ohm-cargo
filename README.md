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

